from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from app.kb.loader import kb
from app.risk.engine import RiskLevel, RiskResult
from app.schemas.case import NormalisedCase
from app.schemas.evidence import EvidenceLedger, Signal
from app.schemas.report import ReportClaim, SafetyReport
from app.schemas.tools import PatternMatchItem


@lru_cache(maxsize=1)
def load_advice() -> dict:
    advice_path = Path(__file__).resolve().parent.parent / "kb" / "advice.yaml"
    if not advice_path.exists():
        return {}
    with open(advice_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_recommended_actions(
    signals: List[Signal],
    matched_patterns: Optional[List[PatternMatchItem]] = None,
) -> List[str]:
    advice_db = load_advice()
    actions_map: Dict[str, str] = advice_db.get("actions", {})
    signal_defaults: Dict[str, List[str]] = advice_db.get("signal_defaults", {})

    action_keys: List[str] = []

    # 1. Gather advice keys from matched patterns
    if matched_patterns:
        for p in matched_patterns:
            action_keys.extend(p.advice_keys)

    # 2. Gather advice keys from signals
    for sig in signals:
        sig_val = sig.value if hasattr(sig, "value") else str(sig)
        if sig_val in signal_defaults:
            action_keys.extend(signal_defaults[sig_val])

    # 3. Always include verify card/official channel for high risk
    high_risk_triggers = [
        Signal.DOMAIN_MISMATCH,
        Signal.LOOKALIKE_DOMAIN,
        Signal.CREDENTIAL_REQUEST,
    ]
    if any(s in high_risk_triggers for s in signals):
        action_keys.append("verify_using_card_number")

    # Deduplicate while preserving order
    seen = set()
    result: List[str] = []
    for k in action_keys:
        if k not in seen and k in actions_map:
            seen.add(k)
            result.append(actions_map[k])

    if not result:
        result.append(
            "No immediate action required. Continue to monitor your account statements regularly."
        )

    return result


def render_template_report(
    case: NormalisedCase,
    ledger: EvidenceLedger,
    risk_result: RiskResult,
    matched_patterns: Optional[List[PatternMatchItem]] = None,
    tool_calls: int = 0,
    latency_ms: int = 0,
    claimed_entity: Optional[str] = None,
) -> SafetyReport:
    """Deterministic fallback/Arm 0 report generator.

    Generates a structured SafetyReport citing exact evidence IDs and
    retrieving actions strictly from advice.yaml.
    """
    signals = [e.signal for e in ledger.items]
    actions = get_recommended_actions(signals, matched_patterns)

    # 1. Build Headline
    entity_name = claimed_entity or "the claimed organization"
    has_mismatch = any(e.signal == Signal.DOMAIN_MISMATCH for e in ledger.items)

    if risk_result.level == RiskLevel.HIGH_RISK:
        if has_mismatch and claimed_entity:
            headline = (
                f"This message asks you to act on a link that does not belong to {entity_name}."
            )
        elif matched_patterns:
            headline = f"This message matches a known {matched_patterns[0].name} scam pattern."
        else:
            headline = (
                "This message exhibits critical risk indicators commonly associated with fraud."
            )
    elif risk_result.level == RiskLevel.CAUTION:
        headline = (
            "This message contains suspicious indicators. Exercise caution before proceeding."
        )
    else:
        headline = (
            "This message appears to be standard communication with low risk indicators."
        )

    # 2. Build Why Claims with Grounded Evidence IDs
    why_claims: List[ReportClaim] = []

    # Social engineering / urgency group
    urgency_signals = [
        Signal.URGENCY_LANGUAGE,
        Signal.THREAT_OF_CONSEQUENCE,
        Signal.IMPERSONATION_CLAIM,
    ]
    urgency_ev = [e.id for e in ledger.items if e.signal in urgency_signals]
    if urgency_ev:
        why_claims.append(
            ReportClaim(
                text=(
                    f"The message claims to be from {entity_name} and uses urgency "
                    "language to pressure you."
                ),
                evidence_ids=urgency_ev,
            )
        )

    # Link / domain mismatch group
    domain_signals = [
        Signal.EXTERNAL_LINK_PRESENT,
        Signal.DOMAIN_MISMATCH,
        Signal.LOOKALIKE_DOMAIN,
        Signal.BRAND_TOKEN_OUTSIDE_DOMAIN,
        Signal.LINK_SHORTENER,
    ]
    domain_ev = [e.id for e in ledger.items if e.signal in domain_signals]
    if domain_ev:
        if has_mismatch:
            why_claims.append(
                ReportClaim(
                    text=(
                        f"The link's domain does not match any domain PayGuard has on "
                        f"record for {entity_name}."
                    ),
                    evidence_ids=domain_ev,
                )
            )
        else:
            why_claims.append(
                ReportClaim(
                    text=(
                        "External links or suspicious domain patterns were detected in the message."
                    ),
                    evidence_ids=domain_ev,
                )
            )

    # Pattern match group
    pattern_ev = [e.id for e in ledger.items if e.signal == Signal.PATTERN_MATCH]
    if pattern_ev and matched_patterns:
        why_claims.append(
            ReportClaim(
                text=(
                    f"The combination of signals matches the signature of known "
                    f"{matched_patterns[0].name}."
                ),
                evidence_ids=pattern_ev,
            )
        )

    # If no grouped claims, provide claim for each evidence item
    if not why_claims and ledger.items:
        for e in ledger.items:
            why_claims.append(ReportClaim(text=e.interpretation, evidence_ids=[e.id]))

    unverified = ["PayGuard could not confirm who actually sent this message."]

    return SafetyReport(
        case_id=case.case_id,
        risk_level=risk_result.level.value,
        risk_score=float(risk_result.score),
        headline=headline,
        why=why_claims,
        evidence=list(ledger.items),
        recommended_actions=actions,
        unverified=unverified,
        rules_fired=risk_result.rules_fired,
        policy_version=risk_result.policy_version,
        kb_version=kb.version,
        model="deterministic",
        tool_calls=tool_calls,
        latency_ms=latency_ms,
    )
