"""PayGuard Investigator — adaptive agent loop.

Contract:
  in:  NormalisedCase
  out: InvestigationResult(ledger, trace, tool_calls, open_questions)

Two runtime backends:
  - "strands": Strands SDK Agent (requires a backend that handles
    multi-turn tool-calling cleanly; NIM has known issues).
  - "simple": Hand-rolled tool loop against the raw OpenAI-compatible
    chat completions API (works everywhere).

Select via AGENT_RUNTIME env var.  Default is "simple" because the NIM
endpoint trips up the Strands multi-turn flow.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from app.agent.prompts import (
    INVESTIGATOR_CASE_TEMPLATE,
    INVESTIGATOR_SYSTEM_PROMPT,
)
from app.config import settings
from app.schemas.case import NormalisedCase
from app.schemas.evidence import Evidence, EvidenceLedger, Signal
from app.schemas.tools import ToolRejection
from app.tools.registry import ToolRegistry, default_registry

# ---------------------------------------------------------------------------
# Trace dataclass — records every tool interaction for the trace UI
# ---------------------------------------------------------------------------


@dataclass
class TraceStep:
    tool: str
    args: Dict[str, Any]
    result_type: str  # "ok" | "cached" | "rejected" | "error"
    elapsed_ms: int = 0
    result_summary: str = ""


@dataclass
class InvestigationResult:
    ledger: EvidenceLedger
    trace: List[TraceStep] = field(default_factory=list)
    tool_calls: int = 0
    open_questions: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Evidence builders — turn tool outputs into Evidence items on the ledger
# ---------------------------------------------------------------------------


def _add_signal_scan_evidence(
    ledger: EvidenceLedger,
    result: BaseModel,
) -> None:
    _BENIGN_SIGNALS = (Signal.NO_ACTIONABLE_REQUEST, Signal.SENDER_VERIFIED_CHANNEL)
    for sig_item in result.signals:
        direction = "benign" if sig_item.signal in _BENIGN_SIGNALS else "risk"
        strength = "HIGH" if sig_item.confidence >= 0.8 else "MEDIUM"
        ledger.add(
            Evidence(
                id=f"E{len(ledger) + 1}",
                tool="signal_scan",
                signal=sig_item.signal,
                observed=f'Text contains: "{sig_item.quote}"',
                interpretation=(
                    f"Linguistic indicator: {sig_item.signal.value}"
                ),
                span=sig_item.span,
                quote=sig_item.quote,
                direction=direction,
                strength=strength,
                confidence=sig_item.confidence,
            )
        )


def _add_url_inspect_evidence(
    ledger: EvidenceLedger,
    result: BaseModel,
    url: str,
) -> None:
    # Always record the presence of the link
    if not any(
        e.signal == Signal.EXTERNAL_LINK_PRESENT and url in e.observed
        for e in ledger.items
    ):
        domain = getattr(result, "registered_domain", "")
        ledger.add(
            Evidence(
                id=f"E{len(ledger) + 1}",
                tool="url_inspect",
                signal=Signal.EXTERNAL_LINK_PRESENT,
                observed=f"URL inspection of {url}: link present",
                interpretation=f"External link pointing to domain: {domain}",
                direction="risk",
                strength="MEDIUM",
                confidence=0.9,
            )
        )
    for s in result.signals:
        kb_ref = None
        strength = "MEDIUM"
        if result.lookalike_candidates:
            off = result.lookalike_candidates[0].official
            kb_ref = f"kb:domain:{off}"
            strength = "HIGH"
        ledger.add(
            Evidence(
                id=f"E{len(ledger) + 1}",
                tool="url_inspect",
                signal=s,
                observed=f"URL inspection of {url}: {s.value}",
                interpretation=f"Structural risk indicator: {s.value}",
                direction="risk",
                strength=strength,
                confidence=0.95,
                kb_ref=kb_ref,
            )
        )


def _add_entity_domain_evidence(
    ledger: EvidenceLedger,
    result: BaseModel,
    entity: str,
) -> None:
    for s in result.signals:
        direction = (
            "benign" if s == Signal.DOMAIN_VERIFIED_OFFICIAL else "risk"
        )
        strength = "HIGH" if result.kb_ref else "MEDIUM"
        ledger.add(
            Evidence(
                id=f"E{len(ledger) + 1}",
                tool="entity_domain_check",
                signal=s,
                observed=f"Entity domain check for {entity}: {s.value}",
                interpretation=f"Domain alignment: {s.value}",
                direction=direction,
                strength=strength,
                confidence=1.0,
                kb_ref=result.kb_ref,
            )
        )


def _add_upi_analyze_evidence(
    ledger: EvidenceLedger,
    result: BaseModel,
) -> None:
    for sig in result.signals:
        # MEDIUM only: this evidence has neither a text quote nor a kb_ref to
        # ground a HIGH strength claim (Evidence.validate_strength_grounding).
        strength = "MEDIUM"
        if sig == Signal.UPI_AMOUNT_MISMATCH:
            observed = (
                f"UPI request for {result.currency or ''} {result.amount} vs "
                f"stated {result.currency or ''} {result.expected_amount}"
            )
            interpretation = (
                f"Amount ratio {result.amount_ratio:.2f}x — actual request does not "
                "match what the sender was told to expect."
            )
        elif sig == Signal.UPI_PAYEE_MISMATCH:
            observed = (
                f"UPI payee '{result.payee_name}' ({result.payee_vpa}) is not a "
                "merchant-registered VPA"
            )
            interpretation = "A business collecting via a personal VPA is a known scam pattern"
        else:  # UPI_COLLECT_REQUEST
            observed = f"Message implies receiving money via '{result.stated_purpose}'"
            interpretation = (
                "Scanning a UPI QR always creates a pay/collect intent from the "
                "scanner — there is no such thing as a 'receive money' QR."
            )
        ledger.add(
            Evidence(
                id=f"E{len(ledger) + 1}",
                tool="upi_analyze",
                signal=sig,
                observed=observed,
                interpretation=interpretation,
                direction="risk",
                strength=strength,
                confidence=0.95,
            )
        )


def _add_pattern_match_evidence(
    ledger: EvidenceLedger,
    result: BaseModel,
) -> None:
    for p in result.matched_patterns:
        ledger.add(
            Evidence(
                id=f"E{len(ledger) + 1}",
                tool="pattern_match",
                signal=Signal.PATTERN_MATCH,
                observed=f"Pattern matched: {p.name}",
                interpretation=(
                    f"Signals ({', '.join(p.fired_signals)}) match "
                    f"{p.name} pattern"
                ),
                direction="risk",
                strength="HIGH",
                confidence=p.confidence,
                kb_ref=f"kb:pattern:{p.pattern_id}",
            )
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_urls(text: str) -> List[str]:
    return re.findall(r"https?://[^\s<>\"']+", text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def investigate(
    case: NormalisedCase,
    max_tool_calls: int = 6,
    registry: Optional[ToolRegistry] = None,
    on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> InvestigationResult:
    """Run the LLM investigator over a case.

    Dispatches to Strands or the fallback hand-rolled loop based on
    the AGENT_RUNTIME setting. on_event streams tool_start/tool_result
    progress as it happens (D19); only the fallback loop supports it today.
    """
    runtime = settings.agent_runtime

    if runtime == "strands":
        try:
            return _investigate_strands(case, max_tool_calls, registry)
        except Exception:
            # Strands failed — fall through to simple loop
            pass

    # Default: hand-rolled loop (reliable on NIM)
    from app.agent.fallback_loop import investigate_fallback

    return investigate_fallback(case, max_tool_calls, registry, on_event=on_event)


def _investigate_strands(
    case: NormalisedCase,
    max_tool_calls: int = 6,
    registry: Optional[ToolRegistry] = None,
) -> InvestigationResult:
    """Strands SDK agent loop (kept as an option)."""
    if registry is None:
        registry = default_registry

    from strands import Agent
    from strands import tool as strands_tool

    provenance_urls: set[str] = set()
    if case.text:
        provenance_urls.update(_extract_urls(case.text))
    provenance_urls.update(case.urls)

    ledger = EvidenceLedger()
    trace: List[TraceStep] = []
    call_count = 0

    @strands_tool(name="signal_scan")
    def tool_signal_scan(text: str) -> str:
        """Scan message text for urgency, threats, and credential requests."""
        nonlocal call_count
        if call_count >= max_tool_calls:
            return json.dumps({"error": "Budget exhausted"})
        call_count += 1
        t0 = time.perf_counter()
        result = registry.dispatch(
            "signal_scan",
            {"text": text},
            case=case,
            provenance_context=provenance_urls,
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        if isinstance(result, ToolRejection):
            trace.append(
                TraceStep(
                    tool="signal_scan",
                    args={"text": text[:50]},
                    result_type="rejected",
                    elapsed_ms=elapsed,
                    result_summary=result.reason,
                )
            )
            return json.dumps(result.model_dump())
        trace.append(
            TraceStep(
                tool="signal_scan",
                args={"text": text[:50]},
                result_type="ok",
                elapsed_ms=elapsed,
                result_summary=f"{len(result.signals)} signals",
            )
        )
        _add_signal_scan_evidence(ledger, result)
        return json.dumps(result.model_dump(), default=str)

    @strands_tool(name="url_inspect")
    def tool_url_inspect(url: str) -> str:
        """Inspect a URL for structural risk indicators."""
        nonlocal call_count
        if call_count >= max_tool_calls:
            return json.dumps({"error": "Budget exhausted"})
        call_count += 1
        t0 = time.perf_counter()
        result = registry.dispatch(
            "url_inspect",
            {"url": url},
            case=case,
            provenance_context=provenance_urls,
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        if isinstance(result, ToolRejection):
            trace.append(
                TraceStep(
                    tool="url_inspect",
                    args={"url": url},
                    result_type="rejected",
                    elapsed_ms=elapsed,
                    result_summary=result.reason,
                )
            )
            return json.dumps(result.model_dump())
        trace.append(
            TraceStep(
                tool="url_inspect",
                args={"url": url},
                result_type="ok",
                elapsed_ms=elapsed,
                result_summary=f"{len(result.signals)} signals",
            )
        )
        _add_url_inspect_evidence(ledger, result, url)
        return json.dumps(result.model_dump(), default=str)

    @strands_tool(name="entity_domain_check")
    def tool_entity_domain_check(
        claimed_entity: str, domains: list[str]
    ) -> str:
        """Check domains against KB for a claimed entity."""
        nonlocal call_count
        if call_count >= max_tool_calls:
            return json.dumps({"error": "Budget exhausted"})
        call_count += 1
        t0 = time.perf_counter()
        result = registry.dispatch(
            "entity_domain_check",
            {"claimed_entity": claimed_entity, "domains": domains},
            case=case,
            provenance_context=provenance_urls,
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        if isinstance(result, ToolRejection):
            trace.append(
                TraceStep(
                    tool="entity_domain_check",
                    args={"entity": claimed_entity},
                    result_type="rejected",
                    elapsed_ms=elapsed,
                    result_summary=result.reason,
                )
            )
            return json.dumps(result.model_dump())
        trace.append(
            TraceStep(
                tool="entity_domain_check",
                args={"entity": claimed_entity},
                result_type="ok",
                elapsed_ms=elapsed,
                result_summary=f"match={result.match}",
            )
        )
        _add_entity_domain_evidence(ledger, result, claimed_entity)
        return json.dumps(result.model_dump(), default=str)

    @strands_tool(name="pattern_match")
    def tool_pattern_match(signals: list[str]) -> str:
        """Match signals against known fraud patterns."""
        nonlocal call_count
        if call_count >= max_tool_calls:
            return json.dumps({"error": "Budget exhausted"})
        call_count += 1
        t0 = time.perf_counter()
        result = registry.dispatch(
            "pattern_match",
            {"signals": signals},
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        if isinstance(result, ToolRejection):
            trace.append(
                TraceStep(
                    tool="pattern_match",
                    args={"n_signals": len(signals)},
                    result_type="rejected",
                    elapsed_ms=elapsed,
                    result_summary=result.reason,
                )
            )
            return json.dumps(result.model_dump())
        trace.append(
            TraceStep(
                tool="pattern_match",
                args={"signals": signals},
                result_type="ok",
                elapsed_ms=elapsed,
                result_summary=f"{len(result.matched_patterns)} patterns",
            )
        )
        _add_pattern_match_evidence(ledger, result)
        return json.dumps(result.model_dump(), default=str)

    from app.llm.provider import get_model

    model = get_model()
    sys_prompt = INVESTIGATOR_SYSTEM_PROMPT.format(budget=max_tool_calls)
    case_msg = INVESTIGATOR_CASE_TEMPLATE.format(
        case_id=case.case_id,
        input_types=case.input_types,
        text=case.text or "(no text)",
        urls=case.urls or "(none)",
        qr_payloads=case.qr_payloads or "(none)",
        payment_context=case.payment_context or "(none)",
    )

    agent = Agent(
        model=model,
        system_prompt=sys_prompt,
        tools=[
            tool_signal_scan,
            tool_url_inspect,
            tool_entity_domain_check,
            tool_pattern_match,
        ],
        callback_handler=None,
    )
    registry.clear_cache()
    agent_result = agent(case_msg)

    open_questions: List[str] = []
    raw = str(agent_result)
    try:
        if "conclude" in raw:
            m = re.search(
                r'\{[^{}]*"action"\s*:\s*"conclude"[^{}]*\}',
                raw,
                re.DOTALL,
            )
            if m:
                parsed = json.loads(m.group(0))
                open_questions = parsed.get("open_questions", [])
    except Exception:
        pass

    return InvestigationResult(
        ledger=ledger,
        trace=trace,
        tool_calls=call_count,
        open_questions=open_questions,
    )
