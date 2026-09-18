"""Risk engine tests driven from tests/unit/test_risk.csv.

Each row declares a signal set, per-evidence strengths and directions,
and the expected risk level.  The engine evaluates a synthetic ledger
and the test asserts the level matches.
"""
import csv
import uuid
from pathlib import Path

import pytest

from app.risk.engine import RiskLevel, evaluate
from app.schemas.evidence import Evidence, EvidenceLedger, Signal


def _build_ledger(signals_str, strengths_str, directions_str):
    ledger = EvidenceLedger()
    if not signals_str:
        return ledger

    signals = [s.strip() for s in signals_str.split(",") if s.strip()]
    strengths = [s.strip() for s in strengths_str.split(",") if s.strip()]
    directions = [s.strip() for s in directions_str.split(",") if s.strip()]

    for i, sig in enumerate(signals):
        strength = strengths[i] if i < len(strengths) else "MEDIUM"
        direction = directions[i] if i < len(directions) else "risk"
        signal_enum = Signal(sig)

        needs_grounding = strength == "HIGH"
        evidence = Evidence(
            id=f"E{i+1}_{uuid.uuid4().hex[:4]}",
            tool="test_harness",
            signal=signal_enum,
            observed=f"Test observed {sig}",
            interpretation=f"Test interpretation for {sig}",
            direction=direction,
            strength=strength,
            confidence=0.9,
            quote=f"test quote for {sig}" if needs_grounding else None,
            span=(0, 10) if needs_grounding else None,
            kb_ref="kb:test@abc" if (needs_grounding and direction == "risk") else None,
        )
        ledger.add(evidence)
    return ledger


def _load_csv_cases():
    csv_path = Path(__file__).resolve().parent / "test_risk.csv"
    cases = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cases.append(row)
    return cases


CSV_CASES = _load_csv_cases()


@pytest.mark.parametrize(
    "case",
    CSV_CASES,
    ids=[c["test_name"] for c in CSV_CASES],
)
def test_risk_csv(case):
    ledger = _build_ledger(
        case["signals"], case["strengths"], case["directions"]
    )
    result = evaluate(ledger)
    expected = RiskLevel(case["expected_level"])
    assert result.level == expected, (
        f"Test '{case['test_name']}': "
        f"expected {expected}, got {result.level}, "
        f"score={result.score}, rules={result.rules_fired}"
    )


# --- explicit named tests for the three contract cases ---

def test_fake_kyc_is_high_risk_via_gate():
    ledger = _build_ledger(
        "impersonation_claim,urgency_language,credential_request,"
        "external_link_present,domain_mismatch",
        "MEDIUM,MEDIUM,HIGH,MEDIUM,HIGH",
        "risk,risk,risk,risk,risk",
    )
    result = evaluate(ledger)
    assert result.level == RiskLevel.HIGH_RISK
    gate_rules = [r for r in result.rules_fired if r.startswith("gate:")]
    assert len(gate_rules) > 0, "Should fire at least one gate"


def test_lone_urgency_is_low_concern():
    ledger = _build_ledger("urgency_language", "MEDIUM", "risk")
    result = evaluate(ledger)
    assert result.level == RiskLevel.LOW_CONCERN
    assert result.score == 10


def test_verified_official_plus_urgency_capped_low():
    """Contract: domain_verified_official + urgency_language → LOW_CONCERN.

    The negative weight of domain_verified_official (-35) keeps the score
    at 0, which is already LOW_CONCERN.  The FP guard is a second layer
    of protection — either mechanism suffices to satisfy the contract.
    """
    ledger = _build_ledger(
        "domain_verified_official,urgency_language",
        "MEDIUM,MEDIUM",
        "benign,risk",
    )
    result = evaluate(ledger)
    assert result.level == RiskLevel.LOW_CONCERN


def test_fp_guard_caps_caution_down():
    """Signals that would score CAUTION get capped to LOW_CONCERN
    by the informational_only FP guard."""
    ledger = _build_ledger(
        "no_actionable_request,urgency_language,threat_of_consequence,"
        "impersonation_claim",
        "MEDIUM,MEDIUM,MEDIUM,MEDIUM",
        "benign,risk,risk,risk",
    )
    evaluate(ledger)  # score=12, LOW_CONCERN already
    # urgency(10)+threat(12)+impersonation(15)+no_actionable(-25) = 12
    # Without FP guard this would be LOW_CONCERN by score too.
    # Verify the guard fires when we feed enough to hit CAUTION:
    ledger2 = _build_ledger(
        "no_actionable_request,urgency_language,threat_of_consequence,"
        "impersonation_claim,lookalike_domain",
        "MEDIUM,MEDIUM,MEDIUM,MEDIUM,HIGH",
        "benign,risk,risk,risk,risk",
    )
    result2 = evaluate(ledger2)
    # lookalike(30)+urgency(10)+threat(12)+impersonation(15)+no_act(-25)=42
    # 42 >= 25 => CAUTION, but informational_only guard has
    # none_of: [external_link_present, payment_request, credential_request]
    # which passes, so it caps to LOW_CONCERN
    assert result2.level == RiskLevel.LOW_CONCERN
    fp_rules = [r for r in result2.rules_fired if "fp_guard" in r]
    assert len(fp_rules) > 0, (
        f"FP guard should fire; rules_fired={result2.rules_fired}"
    )



def test_policy_version_in_result():
    ledger = EvidenceLedger()
    result = evaluate(ledger)
    assert result.policy_version == "risk_policy_v1"
