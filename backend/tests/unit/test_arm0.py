from eval.arms.arm0_deterministic import run_arm0

from app.schemas.case import NormalisedCase


def test_arm0_fake_kyc():
    case = NormalisedCase(
        case_id="case_fake_kyc_01",
        input_types=["text"],
        text="Dear Customer, your HDFC account will be blocked today. Complete KYC immediately: https://hdfc-secure-kyc.in/verify",
        text_source="user",
    )
    report = run_arm0(case)

    assert report.risk_level == "HIGH_RISK"
    assert len(report.evidence) >= 4
    assert len(report.recommended_actions) > 0
    assert "Do not open the link in the message." in report.recommended_actions

    # Check citations in why claims
    evidence_ids = {e.id for e in report.evidence}
    for claim in report.why:
        assert len(claim.evidence_ids) > 0
        for eid in claim.evidence_ids:
            assert eid in evidence_ids


def test_arm0_clean_transaction():
    case = NormalisedCase(
        case_id="case_clean_01",
        input_types=["text"],
        text=(
            "INR 500.00 debited from A/c XX1234 on 18-09-2026. "
            "Avail Bal: INR 12,450.00. Info: UPI/P2A/Ref 12345."
        ),
        text_source="user",
    )
    report = run_arm0(case)

    assert report.risk_level == "LOW_CONCERN"
    assert report.risk_score < 25
