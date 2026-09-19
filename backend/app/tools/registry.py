import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Union

from pydantic import BaseModel

from app.schemas.case import NormalisedCase
from app.schemas.tools import (
    EntityDomainCheckInput,
    EntityDomainCheckResult,
    PatternMatchInput,
    PatternMatchResult,
    QrDecodeInput,
    QrDecodeResult,
    SignalScanInput,
    SignalScanResult,
    ToolRejection,
    UpiAnalysisResult,
    UpiAnalyzeInput,
    UrlInspectInput,
    UrlInspectResult,
)
from app.tools.entity_domain_check import entity_domain_check
from app.tools.pattern_match import pattern_match
from app.tools.qr_decode import qr_decode
from app.tools.signal_scan import signal_scan
from app.tools.upi_analyze import upi_analyze
from app.tools.url_inspect import url_inspect


def canonical_json(obj: Any) -> str:
    """Deterministic, sorted-key JSON serialization for argument hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_arg_hash(tool_name: str, args: Dict[str, Any]) -> str:
    """Computes sha256(tool_name + canonical_json(args))."""
    payload = f"{tool_name}:{canonical_json(args)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ToolDefinition:
    name: str
    callable: Callable[..., Any]
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    description: str


class ToolRegistry:
    """Central registry for PayGuard tools with arg-hash caching and provenance checks.

    Decoupled from any agent framework (Strands, LangChain, custom loop).
    Runtimes wrap this registry to provide model tool-calling.
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._cache: Dict[str, BaseModel] = {}
        self._execution_counts: Dict[str, int] = defaultdict(int)
        self.cache_hits: int = 0
        self.cache_misses: int = 0

    def register(self, tool_def: ToolDefinition) -> None:
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def clear_cache(self) -> None:
        self._cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0

    def get_execution_count(self, tool_name: str) -> int:
        return self._execution_counts.get(tool_name, 0)

    def _check_provenance(
        self,
        tool_name: str,
        args: Dict[str, Any],
        case: Optional[NormalisedCase] = None,
        provenance_context: Optional[Union[Set[str], List[str]]] = None,
    ) -> Optional[ToolRejection]:
        """Validates that tool arguments are grounded in the case data or prior results."""
        if case is None and not provenance_context:
            return None

        # Build set of all known valid case tokens / URLs / domains
        known_sources: Set[str] = set()
        if provenance_context:
            for item in provenance_context:
                known_sources.add(str(item).strip().lower())

        if case:
            if case.text:
                known_sources.add(case.text.strip().lower())
                # Extract any raw URLs or domains from text
                urls_in_text = re.findall(
                    r"https?://[^\s<>\"']+|www\.[^\s<>\"']+",
                    case.text,
                )
                for u in urls_in_text:
                    known_sources.add(u.strip().lower())
            for u in case.urls:
                known_sources.add(u.strip().lower())
            for q in case.qr_payloads:
                known_sources.add(q.strip().lower())

        # 1. url_inspect provenance check
        if tool_name == "url_inspect":
            target_url = str(args.get("url", "")).strip().lower()
            if not target_url:
                return ToolRejection(
                    tool=tool_name,
                    reason="Missing URL argument for url_inspect.",
                    correction="Provide a valid 'url' present in the case.",
                    rejected_arg="url",
                )

            # Check exact match or substring in known sources
            clean_url = target_url.replace("https://", "").replace("http://", "").rstrip("/")
            found = any(
                target_url in src or clean_url in src for src in known_sources
            )
            if not found:
                available = case.urls if case else list(known_sources)
                return ToolRejection(
                    tool=tool_name,
                    reason=(
                        f"URL '{args.get('url')}' was not found in the case message "
                        "or extracted URLs."
                    ),
                    correction=(
                        f"Only call url_inspect on URLs originating from the case. "
                        f"Available case URLs: {available}."
                    ),
                    rejected_arg="url",
                )

        # 2. entity_domain_check provenance check
        if tool_name == "entity_domain_check":
            domains = args.get("domains", [])
            for d in domains:
                d_str = (
                    str(d)
                    .strip()
                    .lower()
                    .replace("https://", "")
                    .replace("http://", "")
                    .rstrip("/")
                )
                found = any(d_str in src for src in known_sources)
                if not found:
                    return ToolRejection(
                        tool=tool_name,
                        reason=f"Domain '{d}' was not found in the case message or extracted URLs.",
                        correction="Only verify domains that exist in the analyzed case.",
                        rejected_arg="domains",
                    )

        # 3. signal_scan provenance check
        if tool_name == "signal_scan":
            scan_text = str(args.get("text", "")).strip()
            if not scan_text:
                return ToolRejection(
                    tool=tool_name,
                    reason="Empty text argument for signal_scan.",
                    correction="Provide non-empty text from the case message to scan.",
                    rejected_arg="text",
                )
            if case and case.text:
                if scan_text.lower() not in case.text.lower():
                    return ToolRejection(
                        tool=tool_name,
                        reason="Scanned text is not present in the case message.",
                        correction="Only scan text extracts originating from the case message.",
                        rejected_arg="text",
                    )

        # 4. qr_decode provenance check
        if tool_name == "qr_decode" and case and case.image_ref:
            target = str(args.get("image_ref", "")).strip()
            if target != case.image_ref:
                return ToolRejection(
                    tool=tool_name,
                    reason=f"image_ref '{target}' does not match the case's uploaded image.",
                    correction=f"Call qr_decode with image_ref='{case.image_ref}'.",
                    rejected_arg="image_ref",
                )

        return None

    def dispatch(
        self,
        name: str,
        args: Dict[str, Any],
        case: Optional[NormalisedCase] = None,
        provenance_context: Optional[Union[Set[str], List[str]]] = None,
    ) -> Union[BaseModel, ToolRejection]:
        """Dispatches a tool call with arg-hash caching and argument provenance checks.

        Contract:
          in:  tool name + args dict
          out: validated output model, or a structured ToolRejection
        """
        tool_def = self.get(name)
        if not tool_def:
            return ToolRejection(
                tool=name,
                reason=f"Unknown tool '{name}'.",
                correction=f"Available tools: {list(self._tools.keys())}.",
            )

        # 1. Validate Input Schema
        try:
            validated_input = tool_def.input_schema(**args)
        except Exception as exc:
            return ToolRejection(
                tool=name,
                reason=f"Invalid arguments for tool '{name}': {exc}",
                correction="Ensure arguments match the tool input schema.",
            )

        input_dict = validated_input.model_dump()

        # 2. Check Arg-Hash Cache
        cache_key = compute_arg_hash(name, input_dict)
        if cache_key in self._cache:
            self.cache_hits += 1
            return self._cache[cache_key]

        self.cache_misses += 1

        # 3. Argument Provenance Check
        rejection = self._check_provenance(name, input_dict, case, provenance_context)
        if rejection:
            return rejection

        # 4. Execute Underlying Callable
        self._execution_counts[name] += 1
        try:
            raw_result = tool_def.callable(**input_dict)
        except Exception as exc:
            return ToolRejection(
                tool=name,
                reason=f"Tool '{name}' execution failed: {exc}",
                correction="Check underlying tool parameters and dependencies.",
            )

        # 5. Validate Output Model
        if isinstance(raw_result, tool_def.output_schema):
            result_model = raw_result
        elif isinstance(raw_result, dict):
            result_model = tool_def.output_schema(**raw_result)
        elif isinstance(raw_result, BaseModel):
            result_model = tool_def.output_schema(**raw_result.model_dump())
        else:
            result_model = raw_result

        # 6. Store in Cache
        self._cache[cache_key] = result_model
        return result_model


# ---- Default Global Registry ----

default_registry = ToolRegistry()

default_registry.register(
    ToolDefinition(
        name="signal_scan",
        callable=signal_scan,
        input_schema=SignalScanInput,
        output_schema=SignalScanResult,
        description=(
            "Scan message text using regex lexicons for urgency, threats, "
            "credential requests, and benign transaction patterns."
        ),
    )
)

default_registry.register(
    ToolDefinition(
        name="url_inspect",
        callable=url_inspect,
        input_schema=UrlInspectInput,
        output_schema=UrlInspectResult,
        description=(
            "Inspect URL structure offline for IP hosts, punycode, shorteners, "
            "brand tokens outside domain, and lookalike candidates."
        ),
    )
)

default_registry.register(
    ToolDefinition(
        name="entity_domain_check",
        callable=entity_domain_check,
        input_schema=EntityDomainCheckInput,
        output_schema=EntityDomainCheckResult,
        description=(
            "Check if supplied domains match official verified domains for "
            "a claimed institution strictly via YAML KB."
        ),
    )
)

default_registry.register(
    ToolDefinition(
        name="pattern_match",
        callable=pattern_match,
        input_schema=PatternMatchInput,
        output_schema=PatternMatchResult,
        description=(
            "Match collected signals against known fraud pattern signatures "
            "defined in YAML KB."
        ),
    )
)

default_registry.register(
    ToolDefinition(
        name="qr_decode",
        callable=qr_decode,
        input_schema=QrDecodeInput,
        output_schema=QrDecodeResult,
        description=(
            "Decode a QR code from an uploaded image and classify its payload "
            "as a UPI payment link, a URL, or plain text."
        ),
    )
)

default_registry.register(
    ToolDefinition(
        name="upi_analyze",
        callable=upi_analyze,
        input_schema=UpiAnalyzeInput,
        output_schema=UpiAnalysisResult,
        description=(
            "Analyze decoded UPI payment fields against the stated payment "
            "context for amount and payee mismatches."
        ),
    )
)


def dispatch(
    name: str,
    args: Dict[str, Any],
    case: Optional[NormalisedCase] = None,
    provenance_context: Optional[Union[Set[str], List[str]]] = None,
) -> Union[BaseModel, ToolRejection]:
    """Convenience module-level dispatch delegating to default_registry."""
    return default_registry.dispatch(
        name=name,
        args=args,
        case=case,
        provenance_context=provenance_context,
    )
