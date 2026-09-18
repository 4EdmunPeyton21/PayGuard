from app.schemas.case import NormalisedCase
from app.schemas.tools import (
    SignalScanResult,
    ToolRejection,
    UrlInspectResult,
)
from app.tools.registry import ToolRegistry, default_registry, dispatch


def test_registry_has_core_tools():
    tools = default_registry.list_tools()
    tool_names = {t.name for t in tools}
    assert "signal_scan" in tool_names
    assert "url_inspect" in tool_names
    assert "entity_domain_check" in tool_names
    assert "pattern_match" in tool_names


def test_arg_hash_cache_single_execution():
    """Done when: identical args hit cache (assert 1 execution)."""
    registry = ToolRegistry()
    for t in default_registry.list_tools():
        registry.register(t)

    args = {"text": "URGENT: Your account will be blocked today. Complete KYC immediately."}

    # 1st call: cache miss, executes underlying function
    res1 = registry.dispatch("signal_scan", args)
    assert isinstance(res1, SignalScanResult)
    assert registry.get_execution_count("signal_scan") == 1
    assert registry.cache_misses == 1
    assert registry.cache_hits == 0

    # 2nd call: cache hit, underlying function NOT executed again
    res2 = registry.dispatch("signal_scan", args)
    assert isinstance(res2, SignalScanResult)
    assert registry.get_execution_count("signal_scan") == 1  # Still 1!
    assert registry.cache_misses == 1
    assert registry.cache_hits == 1

    # Verify identical output
    assert res1.model_dump() == res2.model_dump()


def test_arg_hash_cache_canonical_key_ordering():
    """Different dictionary key order still results in a cache hit."""
    registry = ToolRegistry()
    for t in default_registry.list_tools():
        registry.register(t)

    # Call with key order A
    res1 = registry.dispatch("url_inspect", {"url": "https://hdfcbank.com", "claimed_entity": None})
    assert isinstance(res1, UrlInspectResult)
    assert registry.get_execution_count("url_inspect") == 1

    # Call with key order B
    res2 = registry.dispatch("url_inspect", {"claimed_entity": None, "url": "https://hdfcbank.com"})
    assert isinstance(res2, UrlInspectResult)
    assert registry.get_execution_count("url_inspect") == 1  # Cache hit, count unchanged
    assert registry.cache_hits == 1


def test_url_inspect_provenance_rejection():
    """Done when: calling url_inspect with URL not present in case is rejected with correction."""
    case = NormalisedCase(
        case_id="case_prov_test_01",
        input_types=["text"],
        text="Dear Customer, your electricity bill is overdue. Pay at our Mumbai branch.",
        urls=[],
    )

    unrelated_url = "https://phishing-site.ru/steal"
    result = dispatch("url_inspect", {"url": unrelated_url}, case=case)

    # Must return a structured ToolRejection
    assert isinstance(result, ToolRejection)
    assert result.status == "rejected"
    assert result.tool == "url_inspect"
    assert "was not found" in result.reason or "not present" in result.reason
    assert "Only call url_inspect on URLs originating from the case" in result.correction
    assert result.rejected_arg == "url"


def test_url_inspect_provenance_allowed_when_present():
    """Valid URL present in the case proceeds to execution."""
    url = "https://hdfc-secure-kyc.in/verify"
    case = NormalisedCase(
        case_id="case_prov_test_02",
        input_types=["text"],
        text=f"Update KYC here: {url}",
        urls=[url],
    )

    result = dispatch("url_inspect", {"url": url}, case=case)
    assert isinstance(result, UrlInspectResult)
    assert result.registered_domain == "hdfc-secure-kyc.in"


def test_entity_domain_check_provenance_rejection():
    """entity_domain_check rejects domains not present in the case."""
    case = NormalisedCase(
        case_id="case_prov_test_03",
        input_types=["text"],
        text="Call our helpline at 1800-1234.",
        urls=[],
    )

    result = dispatch(
        "entity_domain_check",
        {"claimed_entity": "HDFC Bank", "domains": ["evil-domain.com"]},
        case=case,
    )
    assert isinstance(result, ToolRejection)
    assert result.status == "rejected"
    assert "evil-domain.com" in result.reason


def test_unknown_tool_rejection():
    """Dispatching an unknown tool returns a structured ToolRejection."""
    result = dispatch("non_existent_tool", {"foo": "bar"})
    assert isinstance(result, ToolRejection)
    assert result.status == "rejected"
    assert "Unknown tool" in result.reason


def test_invalid_arguments_schema_rejection():
    """Calling a tool with invalid arguments schema returns a structured rejection."""
    # signal_scan requires 'text' string argument
    result = dispatch("signal_scan", {})
    assert isinstance(result, ToolRejection)
    assert result.status == "rejected"
    assert "Invalid arguments" in result.reason
