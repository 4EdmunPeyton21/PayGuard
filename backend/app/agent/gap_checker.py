import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Union
from urllib.parse import urlparse

from app.schemas.case import NormalisedCase
from app.schemas.evidence import EvidenceLedger, Signal
from app.tools.registry import ToolRegistry, default_registry


@dataclass
class ForcedToolCall:
    tool: str
    args: Dict[str, Any]
    reason: str

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return other == "FORCED"
        if isinstance(other, ForcedToolCall):
            return (self.tool, self.args) == (other.tool, other.args)
        return False


def _extract_all_urls(case: NormalisedCase) -> List[str]:
    """Collects all explicit and inline URLs from case data."""
    urls = list(case.urls)
    if case.text:
        found = re.findall(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", case.text)
        for u in found:
            if u not in urls:
                urls.append(u)
    return urls


def _is_url_inspected(url: str, ledger: EvidenceLedger) -> bool:
    """Checks if a URL has already been inspected by url_inspect."""
    clean_target = (
        url.lower()
        .replace("https://", "")
        .replace("http://", "")
        .rstrip("/")
    )
    for e in ledger.items:
        if e.tool == "url_inspect":
            obs_lower = e.observed.lower()
            if clean_target in obs_lower or url.lower() in obs_lower:
                return True
    return False


def check_gaps(
    case: NormalisedCase,
    ledger: EvidenceLedger,
) -> Union[Literal["PASS"], ForcedToolCall]:
    """Evaluates deterministic coverage floor over a case and evidence ledger.

    Contract:
      in:  (case, ledger)
      out: "PASS" or ForcedToolCall

    5 straightforward deterministic if-statements ensuring minimum coverage.
    """
    # 1. URL Coverage Floor: URL present in case but never inspected
    urls = _extract_all_urls(case)
    for u in urls:
        if not _is_url_inspected(u, ledger):
            return ForcedToolCall(
                tool="url_inspect",
                args={"url": u},
                reason=f"URL '{u}' present in case but never inspected by url_inspect.",
            )

    # 2. Text Scanning Coverage Floor: Message text present but signal_scan never run
    if case.text and not any(e.tool == "signal_scan" for e in ledger.items):
        return ForcedToolCall(
            tool="signal_scan",
            args={"text": case.text},
            reason="Message text present but signal_scan was never run.",
        )

    # 3. Entity Domain Check Coverage Floor: Claimed entity & URLs present but unverified
    claimed_entity = getattr(case, "claimed_entity", None)
    if not claimed_entity:
        for e in ledger.items:
            if e.signal == Signal.IMPERSONATION_CLAIM and e.quote:
                claimed_entity = e.quote
                break

    if (
        claimed_entity
        and urls
        and not any(e.tool == "entity_domain_check" for e in ledger.items)
    ):
        domains = [
            urlparse(u).netloc or u
            for u in urls
            if urlparse(u).netloc or u
        ]
        return ForcedToolCall(
            tool="entity_domain_check",
            args={"claimed_entity": claimed_entity, "domains": domains},
            reason=(
                f"Claimed entity '{claimed_entity}' and URLs present, "
                "but entity_domain_check was never run."
            ),
        )

    # 4. Pattern Match Coverage Floor: 2+ signals collected but pattern_match never run
    if len(ledger.signals) >= 2 and not any(
        e.tool == "pattern_match" for e in ledger.items
    ):
        return ForcedToolCall(
            tool="pattern_match",
            args={"signals": [s.value for s in ledger.signals]},
            reason="Two or more signals collected on ledger but pattern_match was never run.",
        )

    # 5. QR Payload Coverage Floor: QR payload present but never examined
    if case.qr_payloads and not any(
        e.tool in ("qr_decode", "url_inspect", "upi_analyze")
        for e in ledger.items
    ):
        payload = case.qr_payloads[0]
        tool_to_call = (
            "url_inspect"
            if payload.startswith(("http://", "https://"))
            else "qr_decode"
        )
        call_args = (
            {"url": payload}
            if tool_to_call == "url_inspect"
            else {"payload": payload}
        )
        return ForcedToolCall(
            tool=tool_to_call,
            args=call_args,
            reason="QR payload present in case but never examined.",
        )

    return "PASS"


def execute_forced_call(
    forced: ForcedToolCall,
    case: NormalisedCase,
    ledger: EvidenceLedger,
    registry: Optional[ToolRegistry] = None,
) -> None:
    """Dispatches a forced tool call through the registry and adds evidence to the ledger."""
    if registry is None:
        registry = default_registry

    from app.agent.investigator import (
        _add_entity_domain_evidence,
        _add_pattern_match_evidence,
        _add_signal_scan_evidence,
        _add_url_inspect_evidence,
    )

    result = registry.dispatch(forced.tool, forced.args, case=case)

    # Add evidence if tool executed successfully
    if forced.tool == "url_inspect":
        _add_url_inspect_evidence(ledger, result, forced.args.get("url", ""))
    elif forced.tool == "signal_scan":
        _add_signal_scan_evidence(ledger, result)
    elif forced.tool == "entity_domain_check":
        _add_entity_domain_evidence(
            ledger, result, forced.args.get("claimed_entity", "")
        )
    elif forced.tool == "pattern_match":
        _add_pattern_match_evidence(ledger, result)
