from app.schemas.evidence import Signal
from app.tools.signal_scan import signal_scan


def test_signal_scan_fake_kyc_demo():
    """Demo string returns urgency_language, threat_of_consequence, credential_request,
    and every quote matches text[span[0]:span[1]]."""
    text = (
        "Dear Customer, your HDFC account will be blocked today. "
        "Complete KYC immediately: https://hdfc-secure-kyc.in/verify"
    )

    res = signal_scan(text)
    signal_names = {s.signal for s in res.signals}

    assert Signal.URGENCY_LANGUAGE in signal_names
    assert Signal.THREAT_OF_CONSEQUENCE in signal_names
    assert Signal.CREDENTIAL_REQUEST in signal_names
    assert Signal.NO_ACTIONABLE_REQUEST not in signal_names
    assert res.has_link is True

    # Assert exact character grounding invariant
    for s in res.signals:
        assert text[s.span[0]:s.span[1]] == s.quote
        assert len(s.quote) > 0


def test_signal_scan_real_transaction_alert():
    """Real bank transaction alert returns only no_actionable_request."""
    text = "Your A/C 9876 debited by Rs 500.00 on 18-Sep-2026. Available balance is Rs 15,200.00."

    res = signal_scan(text)
    assert len(res.signals) == 1
    assert res.signals[0].signal == Signal.NO_ACTIONABLE_REQUEST
    assert res.has_link is False

    # Grounding check
    s = res.signals[0]
    assert text[s.span[0]:s.span[1]] == s.quote


def test_signal_scan_hinglish():
    """Detects Hinglish scam phrases and ensures grounding."""
    text = "Apka account block ho jayega, turant KYC update karein jaldi."

    res = signal_scan(text)
    signal_names = {s.signal for s in res.signals}

    assert Signal.THREAT_OF_CONSEQUENCE in signal_names  # block ho jayega
    assert Signal.CREDENTIAL_REQUEST in signal_names      # KYC update karein
    assert res.language == "hi-Latn"

    for s in res.signals:
        assert text[s.span[0]:s.span[1]] == s.quote
