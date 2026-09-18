from app.schemas.evidence import Signal
from app.tools.pattern_match import pattern_match


def test_fake_kyc_matches_only_fake_kyc():
    fake_kyc_signals = [
        "impersonation_claim",
        "urgency_language",
        "credential_request",
        "external_link_present",
        "domain_mismatch",
    ]
    res = pattern_match(fake_kyc_signals)
    assert len(res.matched_patterns) == 1
    assert len(res) == 1
    assert res.matched_patterns[0].pattern_id == "fake_kyc"
    assert Signal.PATTERN_MATCH in res.signals

    # Verify fired and missing signals
    p = res.matched_patterns[0]
    assert "impersonation_claim" in p.fired_signals
    assert "credential_request" in p.fired_signals
    assert "urgency_language" in p.fired_signals
    assert "domain_mismatch" in p.fired_signals
    assert "threat_of_consequence" in p.missing_signals
    assert "threat_of_consequence" not in p.fired_signals


def test_empty_signals_matches_nothing():
    res = pattern_match([])
    assert len(res.matched_patterns) == 0
    assert len(res) == 0
    assert len(res.signals) == 0


def test_otp_harvesting_pattern():
    signals = ["otp_request", "impersonation_claim", "threat_of_consequence"]
    res = pattern_match(signals)
    pattern_ids = [p.pattern_id for p in res.matched_patterns]
    assert "otp_harvesting" in pattern_ids
    assert "fake_kyc" not in pattern_ids


def test_signal_enum_inputs():
    signals = [
        Signal.IMPERSONATION_CLAIM,
        Signal.CREDENTIAL_REQUEST,
        Signal.URGENCY_LANGUAGE,
        Signal.DOMAIN_MISMATCH,
    ]
    res = pattern_match(signals)
    assert len(res.matched_patterns) == 1
    assert res.matched_patterns[0].pattern_id == "fake_kyc"


def test_all_six_patterns_defined():
    from app.tools.pattern_match import load_patterns
    patterns = load_patterns()
    pattern_ids = {p["id"] for p in patterns}
    expected_ids = {
        "fake_kyc",
        "otp_harvesting",
        "fake_refund",
        "fake_delivery_fee",
        "qr_manipulation",
        "job_fee",
    }
    assert expected_ids.issubset(pattern_ids)
