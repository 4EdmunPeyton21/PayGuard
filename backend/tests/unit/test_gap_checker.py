from app.agent.gap_checker import ForcedToolCall, check_gaps, execute_forced_call
from app.schemas.case import NormalisedCase
from app.schemas.evidence import Evidence, EvidenceLedger, Signal


def test_gap_checker_forces_url_inspect_when_uninspected():
    """Done when: a case with a URL that was never inspected gets one forced url_inspect call,

    and the test asserts the ledger gains that evidence.
    """
    case = NormalisedCase(
        case_id="case_gap_01",
        input_types=["text"],
        text="Your account is blocked. Verify at https://hdfc-secure-kyc.in/login immediately.",
        urls=["https://hdfc-secure-kyc.in/login"],
    )

    # Initial ledger only has signal_scan evidence (agent stopped early!)
    ledger = EvidenceLedger()
    ledger.add(
        Evidence(
            id="E1",
            tool="signal_scan",
            signal=Signal.URGENCY_LANGUAGE,
            observed="Text contains immediately",
            interpretation="Urgency language detected",
            quote="immediately",
            span=(74, 85),
            direction="risk",
            strength="HIGH",
            confidence=0.9,
        )
    )

    # Assert no url_inspect evidence initially
    assert not any(e.tool == "url_inspect" for e in ledger.items)
    initial_count = len(ledger)

    # 1. Run gap checker -> must return forced tool call for url_inspect
    result = check_gaps(case, ledger)
    assert result != "PASS"
    assert isinstance(result, ForcedToolCall)
    assert result.tool == "url_inspect"
    assert result.args["url"] == "https://hdfc-secure-kyc.in/login"

    # 2. Execute the forced tool call
    execute_forced_call(result, case, ledger)

    # 3. Assert the ledger gained the url_inspect evidence
    assert len(ledger) > initial_count
    url_evidence = [e for e in ledger.items if e.tool == "url_inspect"]
    assert len(url_evidence) >= 1
    assert Signal.EXTERNAL_LINK_PRESENT in ledger.signals

    # Verify that this URL is now recorded as inspected
    remaining = check_gaps(case, ledger)
    # The URL itself is no longer flagged (though pattern_match or entity_domain may trigger next)
    if remaining != "PASS":
        assert remaining.tool != "url_inspect"


def test_gap_checker_forces_signal_scan_when_text_uninspected():
    """If text exists but signal_scan was never run, signal_scan is forced."""
    case = NormalisedCase(
        case_id="case_gap_02",
        input_types=["text"],
        text="Normal message text",
        urls=[],
    )
    ledger = EvidenceLedger()

    result = check_gaps(case, ledger)
    assert isinstance(result, ForcedToolCall)
    assert result.tool == "signal_scan"
    assert result.args["text"] == "Normal message text"


def test_gap_checker_forces_pattern_match_on_multiple_signals():
    """If 2+ signals exist on the ledger but pattern_match never ran, force pattern_match."""
    case = NormalisedCase(
        case_id="case_gap_03",
        input_types=["text"],
        text="Alert text",
        urls=[],
    )
    ledger = EvidenceLedger()
    ledger.add(
        Evidence(
            id="E1",
            tool="signal_scan",
            signal=Signal.URGENCY_LANGUAGE,
            observed="urgent",
            interpretation="Urgency language found",
            direction="risk",
            strength="HIGH",
            confidence=0.9,
            quote="urgent",
            span=(0, 6),
        )
    )
    ledger.add(
        Evidence(
            id="E2",
            tool="signal_scan",
            signal=Signal.THREAT_OF_CONSEQUENCE,
            observed="blocked",
            interpretation="Threat of consequence found",
            direction="risk",
            strength="HIGH",
            confidence=0.9,
            quote="blocked",
            span=(7, 14),
        )
    )

    result = check_gaps(case, ledger)
    assert isinstance(result, ForcedToolCall)
    assert result.tool == "pattern_match"
    assert "urgency_language" in result.args["signals"]
    assert "threat_of_consequence" in result.args["signals"]


def test_gap_checker_passes_when_fully_covered():
    """When all mandatory artifacts have been evaluated, check_gaps returns 'PASS'."""
    url = "https://legit.com/home"
    case = NormalisedCase(
        case_id="case_gap_04",
        input_types=["text"],
        text="Check updates at https://legit.com/home",
        urls=[url],
    )
    ledger = EvidenceLedger()
    # 1. signal_scan covered
    ledger.add(
        Evidence(
            id="E1",
            tool="signal_scan",
            signal=Signal.NO_ACTIONABLE_REQUEST,
            observed="clean text",
            interpretation="Informational notice with no action requested",
            direction="benign",
            strength="HIGH",
            confidence=0.9,
            quote="clean",
            span=(0, 5),
        )
    )
    # 2. url_inspect covered
    ledger.add(
        Evidence(
            id="E2",
            tool="url_inspect",
            signal=Signal.EXTERNAL_LINK_PRESENT,
            observed=f"URL inspection of {url}: clean",
            interpretation="External link pointing to official domain",
            direction="risk",
            strength="MEDIUM",
            confidence=0.9,
        )
    )
    # 3. pattern_match covered
    ledger.add(
        Evidence(
            id="E3",
            tool="pattern_match",
            signal=Signal.PATTERN_MATCH,
            observed="Pattern check complete",
            interpretation="No threat patterns matched",
            direction="benign",
            strength="MEDIUM",
            confidence=1.0,
        )
    )

    result = check_gaps(case, ledger)
    assert result == "PASS"
