"""D16 contract tests.

Three required tests:
  1. A narration citing E99 (nonexistent) is rejected by the citation validator.
  2. A narration containing "this is definitely a scam" is rejected by the lint validator.
  3. After NARRATOR_MAX_RETRIES the template fallback produces a complete valid report.
"""
from unittest.mock import MagicMock, patch

from app.agent.narrator import narrate, template_narrate
from app.schemas.evidence import Evidence, EvidenceLedger, Signal
from app.schemas.report import ReportClaim
from app.validate.citations import check_citations
from app.validate.lint import lint_narration

# ---------------------------------------------------------------------------
# Shared fixture: a small but real ledger with E1 and E2
# ---------------------------------------------------------------------------


def _make_ledger() -> EvidenceLedger:
    ledger = EvidenceLedger()
    ledger.add(
        Evidence(
            id="E1",
            tool="signal_scan",
            signal=Signal.URGENCY_LANGUAGE,
            observed="Contains 'immediately'",
            interpretation="Urgency language detected",
            direction="risk",
            strength="HIGH",
            confidence=0.9,
            quote="immediately",
            span=(0, 11),
        )
    )
    ledger.add(
        Evidence(
            id="E2",
            tool="url_inspect",
            signal=Signal.LOOKALIKE_DOMAIN,
            observed="URL hdfc-secure-kyc.in: lookalike_domain",
            interpretation="Structural risk indicator: lookalike_domain",
            direction="risk",
            strength="HIGH",
            confidence=0.95,
            kb_ref="kb:domain:hdfcbank.com",
        )
    )
    return ledger


# ---------------------------------------------------------------------------
# Test 1: Citation validator rejects phantom evidence ID
# ---------------------------------------------------------------------------


def test_citation_validator_rejects_phantom_id():
    """A narration citing E99 (nonexistent) must be rejected."""
    ledger = _make_ledger()
    # Claim cites E99 which does not exist in the ledger (only E1 and E2 exist)
    claims = [
        ReportClaim(
            text="The message is consistent with urgency patterns.",
            evidence_ids=["E1", "E99"],  # E99 is phantom
        ),
    ]

    result = check_citations(claims, ledger)

    assert not result.ok, "Citation check should have FAILED for phantom E99"
    assert len(result.errors) == 1
    assert "E99" in result.errors[0].phantom_ids
    # Verify real IDs are not reported as errors
    phantom_ids_flat = [pid for e in result.errors for pid in e.phantom_ids]
    assert "E1" not in phantom_ids_flat


def test_citation_validator_passes_valid_ids():
    """Valid evidence IDs must pass citation check."""
    ledger = _make_ledger()
    claims = [
        ReportClaim(
            text="Urgency language was detected.",
            evidence_ids=["E1"],
        ),
        ReportClaim(
            text="A lookalike domain was found.",
            evidence_ids=["E2"],
        ),
    ]

    result = check_citations(claims, ledger)
    assert result.ok


# ---------------------------------------------------------------------------
# Test 2: Lint validator rejects banned certainty phrase
# ---------------------------------------------------------------------------


def test_lint_rejects_banned_phrase():
    """A narration containing 'this is definitely a scam' must be rejected."""
    headline = "Warning about this message."
    claims = ["This is definitely a scam and you should not click the link."]

    result = lint_narration(headline, claims)

    assert not result.ok, "Lint should have FAILED for 'definitely'"
    assert len(result.violations) >= 1
    phrases = [v.matched_phrase for v in result.violations]
    assert any("definitely" in p.lower() for p in phrases)


def test_lint_rejects_multiple_banned_phrases():
    """Multiple banned phrases each trigger separate violations."""
    headline = "This is certainly fraud."
    claims = [
        "The domain does not match.",
        "This is guaranteed to be a scam.",
    ]

    result = lint_narration(headline, claims)
    assert not result.ok
    matched = {v.matched_phrase for v in result.violations}
    assert "certainly" in matched or "guaranteed" in matched


def test_lint_passes_hedged_language():
    """Properly hedged narrations must pass the lint check."""
    headline = "This message contains indicators that could not be verified."
    claims = [
        "The domain does not match records for the claimed organization.",
        "The indicators are consistent with known phishing patterns.",
        "The link could not be verified as an official channel.",
    ]

    result = lint_narration(headline, claims)
    assert result.ok, f"Lint should pass — violations: {result.violations}"


# ---------------------------------------------------------------------------
# Test 3: After NARRATOR_MAX_RETRIES, template fallback produces a valid report
# ---------------------------------------------------------------------------


def test_template_fallback_after_max_retries():
    """After all LLM retries are exhausted the template fallback must produce
    a complete valid NarrationOutput with headline and at least one why-claim.
    """
    ledger = _make_ledger()

    # Mock the OpenAI client to always raise an exception so every attempt fails
    with patch("app.agent.narrator.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = ConnectionError(
            "Simulated network failure"
        )

        result = narrate(
            ledger=ledger,
            level="HIGH_RISK",
            max_retries=2,
        )

    # Must have fallen back to the template
    assert result.via_fallback is True

    # Must have a non-empty headline
    assert result.headline
    assert len(result.headline) > 10

    # Must have at least one why-claim
    assert len(result.why) >= 1

    # Every evidence_id in every claim must exist in the ledger
    from app.validate.citations import check_citations as cc

    cit = cc(result.why, ledger)
    assert cit.ok, f"Template fallback had citation errors: {cit.errors}"

    # Headline and claims must pass certainty lint
    from app.validate.lint import lint_narration as ln

    lint = ln(result.headline, [c.text for c in result.why])
    assert lint.ok, f"Template fallback had lint violations: {lint.violations}"

    # Rejection reasons must document the failures
    assert len(result.rejection_reasons) >= 1


def test_template_narrate_directly_produces_valid_output():
    """template_narrate() must always produce a valid, citation-clean, lint-clean output."""
    ledger = _make_ledger()

    result = template_narrate(ledger=ledger, level="HIGH_RISK")

    assert result.via_fallback is True
    assert result.headline
    assert len(result.why) >= 1

    from app.validate.citations import check_citations as cc
    from app.validate.lint import lint_narration as ln

    cit = cc(result.why, ledger)
    assert cit.ok, f"Template narration had citation errors: {cit}"

    lint = ln(result.headline, [c.text for c in result.why])
    assert lint.ok, f"Template narration had lint violations: {lint}"
