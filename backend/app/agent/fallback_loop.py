"""PayGuard Fallback Investigator — hand-rolled tool loop.

Uses the raw OpenAI-compatible chat completions API (works with NIM,
Bedrock OpenAI-compat, and standard OpenAI).  ~120 lines of loop logic
that replaces Strands when tool-calling misbehaves on a given endpoint.

Contract:
  in:  NormalisedCase
  out: InvestigationResult(ledger, trace, tool_calls, open_questions)
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional

from openai import OpenAI

from app.agent.investigator import (
    InvestigationResult,
    TraceStep,
    _add_entity_domain_evidence,
    _add_pattern_match_evidence,
    _add_signal_scan_evidence,
    _add_upi_analyze_evidence,
    _add_url_inspect_evidence,
    _extract_urls,
)
from app.agent.prompts import INVESTIGATOR_CASE_TEMPLATE, INVESTIGATOR_SYSTEM_PROMPT
from app.config import settings
from app.schemas.case import NormalisedCase
from app.schemas.evidence import EvidenceLedger
from app.schemas.tools import ToolRejection
from app.tools.registry import ToolRegistry, default_registry

# OpenAI-format tool definitions for the chat completions API
TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "signal_scan",
            "description": (
                "Scan message text for urgency, threats, credential "
                "requests, and informational patterns using regex lexicons."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The message text to scan.",
                    }
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "url_inspect",
            "description": (
                "Inspect a URL's structure offline for IP hosts, punycode, "
                "shorteners, brand token misuse, and lookalike domains."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to inspect.",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "entity_domain_check",
            "description": (
                "Check if domains match official verified domains for a "
                "claimed entity using the knowledge base."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "claimed_entity": {
                        "type": "string",
                        "description": "Name of the claimed institution.",
                    },
                    "domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Domains to verify against KB.",
                    },
                },
                "required": ["claimed_entity", "domains"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pattern_match",
            "description": (
                "Match collected signals against known fraud pattern "
                "signatures from the knowledge base."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "signals": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Signal names collected so far.",
                    }
                },
                "required": ["signals"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "qr_decode",
            "description": (
                "Decode a QR code from an uploaded image and classify its "
                "payload as a UPI payment link, a URL, or plain text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "image_ref": {
                        "type": "string",
                        "description": "Path to the case's uploaded image.",
                    }
                },
                "required": ["image_ref"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upi_analyze",
            "description": (
                "Analyze UPI fields decoded from a QR against the stated "
                "payment context for amount and payee mismatches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "upi_fields": {
                        "type": "object",
                        "description": "The upi_fields object returned by qr_decode.",
                    },
                    "payment_context": {
                        "type": "string",
                        "description": "What the sender was told this payment is for.",
                    },
                },
                "required": ["upi_fields"],
            },
        },
    },
]


# Evidence adders keyed by tool name
_EVIDENCE_ADDERS = {
    "signal_scan": lambda ledger, result, args: _add_signal_scan_evidence(
        ledger, result
    ),
    "url_inspect": lambda ledger, result, args: _add_url_inspect_evidence(
        ledger, result, args.get("url", "")
    ),
    "entity_domain_check": lambda ledger, result, args: _add_entity_domain_evidence(
        ledger, result, args.get("claimed_entity", "")
    ),
    "pattern_match": lambda ledger, result, args: _add_pattern_match_evidence(
        ledger, result
    ),
    "upi_analyze": lambda ledger, result, args: _add_upi_analyze_evidence(
        ledger, result
    ),
}


def investigate_fallback(
    case: NormalisedCase,
    max_tool_calls: int = 6,
    registry: Optional[ToolRegistry] = None,
    on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> InvestigationResult:
    """Hand-rolled tool loop against the OpenAI-compatible API.

    on_event, if given, is called synchronously as ("tool_start" | "tool_result",
    payload) at each tool dispatch — the hook the SSE endpoint (D19) uses to
    stream progress live instead of replaying the trace after the fact.
    """
    if registry is None:
        registry = default_registry
    emit = on_event or (lambda *_a, **_kw: None)

    client = OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_s,
        max_retries=2,
    )

    provenance_urls: set[str] = set()
    if case.text:
        provenance_urls.update(_extract_urls(case.text))
    provenance_urls.update(case.urls)

    ledger = EvidenceLedger()
    trace: List[TraceStep] = []
    call_count = 0

    system_prompt = INVESTIGATOR_SYSTEM_PROMPT.format(budget=max_tool_calls)
    case_message = INVESTIGATOR_CASE_TEMPLATE.format(
        case_id=case.case_id,
        input_types=case.input_types,
        text=case.text or "(no text)",
        urls=case.urls or "(none)",
        qr_payloads=case.qr_payloads or "(none)",
        payment_context=case.payment_context or "(none)",
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": case_message},
    ]

    registry.clear_cache()

    for _loop_iter in range(max_tool_calls + 2):
        # Call the LLM
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                tools=TOOL_DEFS,
                tool_choice="auto",
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        except Exception as exc:
            trace.append(TraceStep(
                tool="llm_call", args={},
                result_type="error", elapsed_ms=0,
                result_summary=str(exc)[:200],
            ))
            break

        choice = response.choices[0]
        assistant_msg = choice.message

        # Append the assistant message to conversation history
        msg_dict: Dict[str, Any] = {
            "role": "assistant",
            "content": assistant_msg.content or "",
        }
        if assistant_msg.tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_msg.tool_calls
            ]
        messages.append(msg_dict)

        # If no tool calls, model has decided to stop
        if not assistant_msg.tool_calls:
            break

        # Process each tool call
        for tc in assistant_msg.tool_calls:
            tool_name = re.sub(r"<\|.*?\|>.*", "", tc.function.name).strip()
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}

            if call_count >= max_tool_calls:
                tool_result_str = json.dumps({
                    "error": "Budget exhausted. No more tool calls allowed.",
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result_str,
                })
                trace.append(TraceStep(
                    tool=tool_name,
                    args=args,
                    result_type="rejected",
                    result_summary="Budget exhausted",
                ))
                continue

            call_count += 1
            t0 = time.perf_counter()
            emit("tool_start", {"tool": tool_name, "args": args})

            # Dispatch through registry (cache + provenance)
            result = registry.dispatch(
                tool_name,
                args,
                case=case,
                provenance_context=provenance_urls,
            )
            elapsed_ms = int((time.perf_counter() - t0) * 1000)

            if isinstance(result, ToolRejection):
                trace.append(TraceStep(
                    tool=tool_name, args=args,
                    result_type="rejected", elapsed_ms=elapsed_ms,
                    result_summary=result.reason[:100],
                ))
                tool_result_str = json.dumps(result.model_dump())
                emit("tool_result", {
                    "tool": tool_name, "result_type": "rejected",
                    "elapsed_ms": elapsed_ms, "summary": result.reason[:100],
                    "raw": result.model_dump(),
                })
            else:
                # Add evidence to ledger
                adder = _EVIDENCE_ADDERS.get(tool_name)
                if adder:
                    adder(ledger, result, args)

                result_dict = result.model_dump()
                tool_result_str = json.dumps(result_dict, default=str)
                summary = ""
                if tool_name == "signal_scan":
                    summary = f"{len(result.signals)} signals"
                elif tool_name == "url_inspect":
                    summary = f"{len(result.signals)} signals"
                elif tool_name == "entity_domain_check":
                    summary = f"match={result.match}"
                elif tool_name == "pattern_match":
                    n = len(result.matched_patterns)
                    summary = f"{n} patterns"
                elif tool_name == "qr_decode":
                    summary = f"decoded={result.decoded} type={result.payload_type}"
                    if result.payload_type == "url" and result.url:
                        # Chaining (T4): a URL found inside a QR becomes a
                        # legitimate url_inspect target even though it never
                        # appeared in the case text.
                        provenance_urls.add(result.url)
                elif tool_name == "upi_analyze":
                    summary = f"{len(result.signals)} signals"

                trace.append(TraceStep(
                    tool=tool_name, args=args,
                    result_type="ok", elapsed_ms=elapsed_ms,
                    result_summary=summary,
                ))
                emit("tool_result", {
                    "tool": tool_name, "result_type": "ok",
                    "elapsed_ms": elapsed_ms, "summary": summary,
                    "raw": result_dict,
                })

            # Feed result back to conversation
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result_str,
            })

        # If budget exhausted, break loop
        if call_count >= max_tool_calls:
            break

    # Deterministic Coverage Gap Checker (enforces evidence floor)
    if settings.enable_gap_checker and call_count < max_tool_calls:
        from app.agent.gap_checker import ForcedToolCall, check_gaps, execute_forced_call

        gap = check_gaps(case, ledger)
        if gap != "PASS" and isinstance(gap, ForcedToolCall):
            emit("tool_start", {"tool": gap.tool, "args": gap.args})
            t0 = time.perf_counter()
            execute_forced_call(gap, case, ledger, registry=registry)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            summary = f"Forced by gap checker: {gap.reason}"
            trace.append(
                TraceStep(
                    tool=gap.tool,
                    args=gap.args,
                    result_type="ok",
                    elapsed_ms=elapsed_ms,
                    result_summary=summary,
                )
            )
            emit("tool_result", {
                "tool": gap.tool, "result_type": "ok",
                "elapsed_ms": elapsed_ms, "summary": summary,
            })
            call_count += 1

    # Extract open_questions from final assistant message
    open_questions: List[str] = []
    try:
        last_content = messages[-1].get("content", "")
        if "conclude" in str(last_content):
            m = re.search(
                r'\{[^{}]*"action"\s*:\s*"conclude"[^{}]*\}',
                str(last_content),
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
