"""PayGuard Narrator — LLM-based narration with citation + lint validators.

Contract:
  in:  (ledger: EvidenceLedger, level: str)  — NO raw message text
  out: validated NarrationOutput(headline, why[])

Anti-hallucination layering:
  1. The narrator prompt receives ONLY the ledger and the computed risk level.
     It never sees the raw message.  That is the whole point.
  2. Citation enforcement: every evidence_id in every claim must resolve to a
     real ledger item.  Phantom IDs → rejection.
  3. Certainty lint: banned phrases ("definitely", "this is a scam", etc.)
     cause rejection.
  4. On failure: retry up to NARRATOR_MAX_RETRIES, then fall back to the
     deterministic template renderer already in render_template_report().

The template fallback lives in this file (template_narrate) so that the
template path is always available even if imports fail in tests.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from openai import OpenAI

from app.config import settings
from app.kb.loader import kb
from app.risk.engine import RiskResult
from app.schemas.evidence import EvidenceLedger, Signal
from app.schemas.report import ReportClaim, SafetyReport
from app.schemas.tools import PatternMatchItem
from app.validate.citations import CitationResult, check_citations
from app.validate.lint import LintResult, lint_narration

# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


@dataclass
class NarrationOutput:
    headline: str
    why: List[ReportClaim] = field(default_factory=list)
    via_fallback: bool = False
    rejection_reasons: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Advice / recommended-actions helpers (unchanged from Arm 0 narrator)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_advice() -> dict:
    advice_path = Path(__file__).resolve().parent.parent / "kb" / "advice.yaml"
    if not advice_path.exists():
        return {}
    with open(advice_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_recommended_actions(
    signals: List[Signal],
    matched_patterns: Optional[List[PatternMatchItem]] = None,
) -> List[str]:
    advice_db = _load_advice()
    actions_map: Dict[str, str] = advice_db.get("actions", {})
    signal_defaults: Dict[str, List[str]] = advice_db.get("signal_defaults", {})

    action_keys: List[str] = []
    if matched_patterns:
        for p in matched_patterns:
            action_keys.extend(p.advice_keys)
    for sig in signals:
        sig_val = sig.value if hasattr(sig, "value") else str(sig)
        if sig_val in signal_defaults:
            action_keys.extend(signal_defaults[sig_val])

    high_risk_triggers = [
        Signal.DOMAIN_MISMATCH,
        Signal.LOOKALIKE_DOMAIN,
        Signal.CREDENTIAL_REQUEST,
    ]
    if any(s in high_risk_triggers for s in signals):
        action_keys.append("verify_using_card_number")

    seen: set = set()
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


# ---------------------------------------------------------------------------
# Template narration (deterministic fallback — never calls LLM)
# ---------------------------------------------------------------------------


def template_narrate(
    ledger: EvidenceLedger,
    level: str,
    claimed_entity: Optional[str] = None,
    matched_patterns: Optional[List[PatternMatchItem]] = None,
) -> NarrationOutput:
    """Pure-deterministic template renderer.  Used as fallback and in Arm 0.

    Does NOT call the LLM.  Does NOT receive the raw message text.
    Reads only the ledger and the risk level.
    """
    entity_name = claimed_entity or "the claimed organization"
    has_mismatch = any(e.signal == Signal.DOMAIN_MISMATCH for e in ledger.items)

    if level == "HIGH_RISK":
        if has_mismatch and claimed_entity:
            headline = (
                f"The link in this message does not match any domain PayGuard "
                f"has on record for {entity_name}."
            )
        elif matched_patterns:
            headline = (
                f"The indicators in this message are consistent with a known "
                f"{matched_patterns[0].name} pattern."
            )
        else:
            headline = (
                "This message exhibits indicators that are consistent with "
                "high-risk fraud patterns."
            )
    elif level == "CAUTION":
        headline = (
            "This message contains indicators that could not be fully verified. "
            "Exercise caution before proceeding."
        )
    else:
        headline = (
            "The indicators checked in this message did not match any known "
            "risk patterns."
        )

    why_claims: List[ReportClaim] = []

    # Social-engineering group
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
                    "The message uses urgency language and pressure tactics "
                    "consistent with social engineering."
                ),
                evidence_ids=urgency_ev,
            )
        )

    # Credential / sensitive request
    cred_signals = [Signal.CREDENTIAL_REQUEST, Signal.OTP_REQUEST, Signal.PIN_REQUEST]
    cred_ev = [e.id for e in ledger.items if e.signal in cred_signals]
    if cred_ev:
        why_claims.append(
            ReportClaim(
                text=(
                    "The message requests sensitive information that legitimate "
                    "institutions do not ask for via SMS."
                ),
                evidence_ids=cred_ev,
            )
        )

    # Domain / link group
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
            domain_text = (
                f"The link's domain does not match any domain PayGuard has on "
                f"record for {entity_name}."
            )
        else:
            domain_text = (
                "The message contains external links with structural indicators "
                "that could not be verified as official."
            )
        why_claims.append(ReportClaim(text=domain_text, evidence_ids=domain_ev))

    # Pattern-match group
    pattern_ev = [e.id for e in ledger.items if e.signal == Signal.PATTERN_MATCH]
    if pattern_ev and matched_patterns:
        why_claims.append(
            ReportClaim(
                text=(
                    f"The combination of signals is consistent with the signature "
                    f"of known {matched_patterns[0].name}."
                ),
                evidence_ids=pattern_ev,
            )
        )

    # Benign / clean sweep
    benign_signals = [Signal.NO_ACTIONABLE_REQUEST, Signal.SENDER_VERIFIED_CHANNEL]
    benign_ev = [e.id for e in ledger.items if e.signal in benign_signals]
    if benign_ev and not urgency_ev and not cred_ev and not domain_ev:
        why_claims.append(
            ReportClaim(
                text=(
                    "The message appears informational with no requests that could not be verified."
                ),
                evidence_ids=benign_ev,
            )
        )

    # If still empty, cite every evidence item individually
    if not why_claims and ledger.items:
        for e in ledger.items:
            why_claims.append(
                ReportClaim(text=e.interpretation or e.observed, evidence_ids=[e.id])
            )

    # Fallback if truly empty ledger
    if not why_claims:
        why_claims.append(
            ReportClaim(
                text="No evidence was collected. The message was not analysed.",
                evidence_ids=[],
            )
        )

    return NarrationOutput(
        headline=headline,
        why=why_claims,
        via_fallback=True,
    )


# ---------------------------------------------------------------------------
# LLM Narration helpers
# ---------------------------------------------------------------------------

_NARRATOR_SYSTEM = """\
You write PayGuard's explanation of a risk verdict.
You are given: a risk level already decided by the risk engine, and an evidence ledger.

NEVER see the raw user message — you receive ONLY the ledger and the level.

Write 3–5 SHORT claims explaining the level. Output JSON ONLY:
{"headline": "...", "why": [{"text": "...", "evidence_ids": ["E1", "E4"]}]}

HARD RULES (violations cause your response to be discarded and regenerated):
1. Every claim must cite at least one evidence_id that exists in the provided ledger.
   Do NOT invent evidence IDs.
2. Do not introduce any fact not present in the ledger.
3. Banned phrases — never use:
   "definitely", "certainly", "this is a scam", "fraudulent",
   "guaranteed", "100%", "without doubt", "no doubt",
   "this is fraud", "confirmed scam".
   Instead use: "indicates", "is consistent with", "does not match",
   "could not be verified".
4. Never name a person or organisation as a fraudster.
5. If the level is LOW_CONCERN, explain what was checked and found clean.
   Do not manufacture concern.
"""


def _build_ledger_summary(ledger: EvidenceLedger) -> str:
    """Formats the ledger as text for the narrator.  NO raw message text."""
    lines = [f"RISK LEVEL: {ledger}"]  # placeholder — rebuilt below
    lines = []
    for e in ledger.items:
        line = (
            f"[{e.id}] tool={e.tool} signal={e.signal.value} "
            f"direction={e.direction} strength={e.strength} "
            f"observed={e.observed!r}"
        )
        lines.append(line)
    if not lines:
        lines = ["(No evidence collected — empty ledger)"]
    return "\n".join(lines)


def _parse_llm_narration(raw: str) -> Optional[tuple[str, List[ReportClaim]]]:
    """Extract headline + why from LLM JSON output."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?", "", raw).strip()
    # Find first JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    headline = parsed.get("headline", "").strip()
    why_raw = parsed.get("why", [])
    if not headline or not isinstance(why_raw, list):
        return None

    why: List[ReportClaim] = []
    for item in why_raw:
        if isinstance(item, dict) and "text" in item:
            why.append(
                ReportClaim(
                    text=item["text"],
                    evidence_ids=item.get("evidence_ids", []),
                )
            )
    return headline, why


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def narrate(
    ledger: EvidenceLedger,
    level: str,
    claimed_entity: Optional[str] = None,
    matched_patterns: Optional[List[PatternMatchItem]] = None,
    max_retries: Optional[int] = None,
) -> NarrationOutput:
    """Generate a validated narration from the ledger and risk level.

    Never receives the raw message text — only the ledger.

    Retry loop:
      1. Call the LLM narrator.
      2. Parse JSON output.
      3. Run citation check (all evidence_ids must exist in ledger).
      4. Run certainty lint (no banned phrases).
      5. If either check fails: retry up to max_retries times.
      6. On exhaustion: call template_narrate() (always passes validation).
    """
    retries = max_retries if max_retries is not None else settings.narrator_max_retries
    rejection_reasons: List[str] = []

    ledger_text = _build_ledger_summary(ledger)
    user_msg = (
        f"RISK LEVEL: {level}\n\n"
        f"EVIDENCE LEDGER:\n{ledger_text}\n\n"
        f"Write the narration JSON."
    )

    client = OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_s,
        max_retries=1,
    )

    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": _NARRATOR_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=1024,
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:
            rejection_reasons.append(f"LLM error (attempt {attempt + 1}): {exc}")
            break  # Network errors → skip to fallback immediately

        parsed = _parse_llm_narration(raw)
        if parsed is None:
            rejection_reasons.append(
                f"Attempt {attempt + 1}: could not parse JSON from LLM output"
            )
            continue

        headline, why = parsed

        # 1. Citation enforcement
        cit: CitationResult = check_citations(why, ledger)
        if not cit.ok:
            rejection_reasons.append(
                f"Attempt {attempt + 1}: citation failure — "
                + "; ".join(str(e) for e in cit.errors)
            )
            continue

        # 2. Certainty lint
        lint: LintResult = lint_narration(headline, [c.text for c in why])
        if not lint.ok:
            rejection_reasons.append(
                f"Attempt {attempt + 1}: lint failure — "
                + "; ".join(str(v) for v in lint.violations)
            )
            continue

        # Both checks passed
        return NarrationOutput(
            headline=headline,
            why=why,
            via_fallback=False,
            rejection_reasons=rejection_reasons,
        )

    # All attempts exhausted — use deterministic template fallback
    fallback = template_narrate(
        ledger=ledger,
        level=level,
        claimed_entity=claimed_entity,
        matched_patterns=matched_patterns,
    )
    fallback.rejection_reasons = rejection_reasons
    return fallback


def render_template_report(
    case,
    ledger: EvidenceLedger,
    risk_result: RiskResult,
    matched_patterns: Optional[List[PatternMatchItem]] = None,
    tool_calls: int = 0,
    latency_ms: int = 0,
    claimed_entity: Optional[str] = None,
) -> SafetyReport:
    """Deterministic report renderer used by Arm 0 and as the ultimate fallback.

    Delegates narration to template_narrate (no LLM, no raw text).
    """
    signals = [e.signal for e in ledger.items]
    actions = get_recommended_actions(signals, matched_patterns)
    narration = template_narrate(
        ledger=ledger,
        level=risk_result.level.value,
        claimed_entity=claimed_entity,
        matched_patterns=matched_patterns,
    )

    unverified = ["PayGuard could not confirm who actually sent this message."]

    return SafetyReport(
        case_id=case.case_id,
        risk_level=risk_result.level.value,
        risk_score=float(risk_result.score),
        headline=narration.headline,
        why=narration.why,
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
