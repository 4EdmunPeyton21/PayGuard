import pytest
from pydantic import ValidationError

from app.schemas.case import NormalisedCase
from app.schemas.evidence import Evidence, EvidenceLedger, Signal


def test_valid_evidence_constructs():
    """A valid Evidence with quote constructs properly."""
    ev = Evidence(
        id="E1",
        tool="signal_scan",
        signal=Signal.URGENCY_LANGUAGE,
        observed="Message contains 'will be blocked today'",
        interpretation="Creates artificial time pressure",
        span=(10, 31),
        quote="will be blocked today",
        direction="risk",
        strength="HIGH",
        confidence=0.9,
    )
    assert ev.id == "E1"
    assert ev.signal == Signal.URGENCY_LANGUAGE
    assert ev.strength == "HIGH"
    assert ev.quote == "will be blocked today"


def test_valid_evidence_with_kb_ref():
    """A valid Evidence with kb_ref and strength HIGH constructs properly."""
    ev = Evidence(
        id="E2",
        tool="entity_domain_check",
        signal=Signal.DOMAIN_MISMATCH,
        observed="Supplied domain does not match official domains",
        interpretation="Domain does not belong to HDFC Bank",
        direction="risk",
        strength="HIGH",
        confidence=1.0,
        kb_ref="entities.yaml#hdfc_bank@v3",
    )
    assert ev.id == "E2"
    assert ev.kb_ref == "entities.yaml#hdfc_bank@v3"
    assert ev.strength == "HIGH"


def test_unknown_signal_string_raises():
    """An unknown signal string outside the closed Signal enum raises ValidationError."""
    with pytest.raises(ValidationError):
        Evidence(
            id="E3",
            tool="signal_scan",
            signal="completely_fabricated_signal",
            observed="some text",
            interpretation="some interpretation",
            direction="risk",
            strength="LOW",
            confidence=0.5,
        )


def test_strength_high_without_quote_or_kb_ref_raises():
    """Evidence with strength='HIGH' but neither quote nor kb_ref raises ValidationError."""
    with pytest.raises(ValidationError, match="may not emit strength: HIGH"):
        Evidence(
            id="E4",
            tool="url_inspect",
            signal=Signal.LOOKALIKE_DOMAIN,
            observed="Domain lookalike detected",
            interpretation="Suspicious lookalike",
            direction="risk",
            strength="HIGH",
            confidence=0.8,
            quote=None,
            kb_ref=None,
        )


def test_strength_medium_low_without_quote_or_kb_ref_allowed():
    """Evidence with strength 'MEDIUM' or 'LOW' is permitted without quote or kb_ref."""
    ev = Evidence(
        id="E5",
        tool="url_inspect",
        signal=Signal.LINK_SHORTENER,
        observed="Uses bit.ly shortener",
        interpretation="Hides destination URL",
        direction="risk",
        strength="MEDIUM",
        confidence=0.7,
    )
    assert ev.strength == "MEDIUM"


def test_evidence_ledger():
    """EvidenceLedger holds items, allows appending, indexing, and lookup by ID."""
    ledger = EvidenceLedger()
    ev1 = Evidence(
        id="E1",
        tool="signal_scan",
        signal=Signal.URGENCY_LANGUAGE,
        observed="urgent",
        interpretation="rush",
        quote="urgent",
        direction="risk",
        strength="HIGH",
        confidence=0.9,
    )
    ev2 = Evidence(
        id="E2",
        tool="signal_scan",
        signal=Signal.NO_ACTIONABLE_REQUEST,
        observed="clean",
        interpretation="benign",
        direction="benign",
        strength="LOW",
        confidence=0.8,
    )
    ledger.add(ev1)
    ledger.add(ev2)

    assert len(ledger) == 2
    assert ledger[0].id == "E1"
    assert ledger.get("E2") is not None
    assert ledger.get("E99") is None
    assert [e.id for e in ledger] == ["E1", "E2"]


def test_normalised_case_constructs():
    """NormalisedCase constructs properly with default list fields."""
    case = NormalisedCase(
        case_id="case_001",
        input_types=["text", "url"],
        text="Dear customer your account is blocked",
        text_source="user",
        urls=["https://fake-bank.in"],
    )
    assert case.case_id == "case_001"
    assert len(case.urls) == 1
    assert case.qr_payloads == []
