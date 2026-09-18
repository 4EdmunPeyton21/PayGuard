import argparse
import re
import sys
import time
import uuid
from pathlib import Path
from typing import List, Optional

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.agent.narrator import render_template_report
from app.kb.loader import kb
from app.risk.engine import evaluate
from app.schemas.case import NormalisedCase
from app.schemas.evidence import Evidence, EvidenceLedger, Signal
from app.schemas.report import SafetyReport
from app.tools.entity_domain_check import entity_domain_check
from app.tools.pattern_match import pattern_match
from app.tools.signal_scan import signal_scan
from app.tools.url_inspect import url_inspect


def _extract_urls(text: str) -> List[str]:
    pattern = r"https?://[^\s<>\"']+|www\.[^\s<>\"']+"
    return re.findall(pattern, text)


def _detect_claimed_entity(text: str) -> Optional[str]:
    """Scan text against KB entity aliases to detect claimed institution."""
    if not text:
        return None
    text_lower = text.lower()
    for entity in kb.entities.values():
        if entity.name.lower() in text_lower:
            return entity.name
        for alias in entity.aliases:
            if alias.lower() in text_lower:
                return entity.name
    return None


def run_arm0(case: NormalisedCase) -> SafetyReport:
    """Contract: in: NormalisedCase -> out: SafetyReport.

    Executes all deterministic tools in a fixed pipeline order:
    1. Entity detection
    2. signal_scan
    3. URL extraction & url_inspect
    4. entity_domain_check
    5. pattern_match
    6. risk engine evaluation
    7. template report generation
    """
    start_time = time.perf_counter()
    ledger = EvidenceLedger()
    tool_calls = 0
    text = case.text or ""

    # 1. Detect Claimed Entity
    claimed_entity = _detect_claimed_entity(text)
    if claimed_entity:
        entity = kb.resolve_entity(claimed_entity)
        version_hash = kb.version.split("@")[-1] if "@" in kb.version else kb.version
        kb_ref = f"kb:entity:{entity.id}@{version_hash}" if entity else None

        # Find matching alias span
        quote = claimed_entity
        span = None
        for alias in (entity.aliases if entity else [claimed_entity]):
            idx = text.lower().find(alias.lower())
            if idx != -1:
                quote = text[idx : idx + len(alias)]
                span = (idx, idx + len(alias))
                break

        ledger.add(
            Evidence(
                id=f"E{len(ledger)+1}",
                tool="entity_resolution",
                signal=Signal.IMPERSONATION_CLAIM,
                observed=f'Message identifies as or claims to represent "{claimed_entity}"',
                interpretation=f"Sender claims institutional identity of {claimed_entity}",
                quote=quote,
                span=span,
                direction="risk",
                strength="HIGH" if quote else "MEDIUM",
                confidence=0.9,
                kb_ref=kb_ref,
            )
        )

    # 2. Tool 1: signal_scan
    if text:
        tool_calls += 1
        scan_res = signal_scan(text)
        for sig_item in scan_res.signals:
            direction = (
                "benign"
                if sig_item.signal == Signal.NO_ACTIONABLE_REQUEST
                else "risk"
            )
            strength = "HIGH" if sig_item.confidence >= 0.8 else "MEDIUM"
            interp_map = {
                Signal.URGENCY_LANGUAGE: (
                    "Creates artificial time pressure to discourage independent verification"
                ),
                Signal.THREAT_OF_CONSEQUENCE: (
                    "Threatens immediate account disruption, closure or penalty"
                ),
                Signal.CREDENTIAL_REQUEST: (
                    "Requests user credentials, KYC update, or account authentication"
                ),
                Signal.NO_ACTIONABLE_REQUEST: (
                    "Informational communication requiring no sensitive user action"
                ),
            }
            interp = interp_map.get(
                sig_item.signal, f"Observed linguistic indicator: {sig_item.signal.value}"
            )
            ledger.add(
                Evidence(
                    id=f"E{len(ledger)+1}",
                    tool="signal_scan",
                    signal=sig_item.signal,
                    observed=f'Message text contains quote: "{sig_item.quote}"',
                    interpretation=interp,
                    span=sig_item.span,
                    quote=sig_item.quote,
                    direction=direction,
                    strength=strength,
                    confidence=sig_item.confidence,
                )
            )

    # 3. URL Extraction & Link Evidence
    urls = list(case.urls)
    if text:
        extracted = _extract_urls(text)
        for u in extracted:
            if u not in urls:
                urls.append(u)

    for url in urls:
        span = None
        quote = None
        if text and url in text:
            start_idx = text.find(url)
            span = (start_idx, start_idx + len(url))
            quote = url

        ledger.add(
            Evidence(
                id=f"E{len(ledger)+1}",
                tool="input_extraction",
                signal=Signal.EXTERNAL_LINK_PRESENT,
                observed=f"Message directs recipient to external URL: {url}",
                interpretation="External link routes user outside secure banking channels",
                span=span,
                quote=quote,
                direction="risk",
                strength="HIGH" if quote else "MEDIUM",
                confidence=1.0,
            )
        )

        # 4. Tool 2: url_inspect
        tool_calls += 1
        url_res = url_inspect(url)
        for s in url_res.signals:
            kb_ref = None
            strength = "MEDIUM"
            if url_res.lookalike_candidates:
                off = url_res.lookalike_candidates[0].official
                kb_ref = f"kb:domain:{off}"
                strength = "HIGH"

            ledger.add(
                Evidence(
                    id=f"E{len(ledger)+1}",
                    tool="url_inspect",
                    signal=s,
                    observed=f"Technical URL inspection of {url} flagged: {s.value}",
                    interpretation=f"Host or path structure exhibits deceptive patterns: {s.value}",
                    direction="risk",
                    strength=strength,
                    confidence=0.95,
                    kb_ref=kb_ref,
                )
            )

    # 5. Tool 3: entity_domain_check
    if claimed_entity and urls:
        tool_calls += 1
        domain_chk = entity_domain_check(claimed_entity, urls)
        for s in domain_chk.signals:
            direction = (
                "benign"
                if s == Signal.DOMAIN_VERIFIED_OFFICIAL
                else "risk"
            )
            if s == Signal.DOMAIN_MISMATCH:
                off_doms = ", ".join(domain_chk.official_domains)
                obs = f"Domain {urls[0]} does not match official domains: {off_doms}"
                interp = f"The destination website does not belong to {claimed_entity}"
            elif s == Signal.DOMAIN_VERIFIED_OFFICIAL:
                obs = f"Domain {domain_chk.matched_domain} matches known official domains"
                interp = (
                    f"The destination website is verified official infrastructure for "
                    f"{claimed_entity}"
                )
            else:
                obs = f"Entity check result: {s.value}"
                interp = "Domain and entity alignment assessment"

            ledger.add(
                Evidence(
                    id=f"E{len(ledger)+1}",
                    tool="entity_domain_check",
                    signal=s,
                    observed=obs,
                    interpretation=interp,
                    direction=direction,
                    strength="HIGH",
                    confidence=1.0,
                    kb_ref=domain_chk.kb_ref,
                )
            )

    # 6. Tool 4: pattern_match
    tool_calls += 1
    collected_signals = [e.signal for e in ledger.items]
    pat_res = pattern_match(collected_signals)

    for p in pat_res.matched_patterns:
        sig_str = ", ".join(p.fired_signals)
        ledger.add(
            Evidence(
                id=f"E{len(ledger)+1}",
                tool="pattern_match",
                signal=Signal.PATTERN_MATCH,
                observed=f"Signals match signature of known fraud pattern: {p.name}",
                interpretation=(
                    f"Corroborating indicators ({sig_str}) match documented "
                    f"{p.name} modus operandi"
                ),
                direction="risk",
                strength="HIGH",
                confidence=p.confidence,
                kb_ref=f"kb:pattern:{p.pattern_id}",
            )
        )

    # 7. Risk Engine Evaluation
    risk_result = evaluate(ledger)

    # 8. Report Generation
    latency_ms = int((time.perf_counter() - start_time) * 1000)
    report = render_template_report(
        case=case,
        ledger=ledger,
        risk_result=risk_result,
        matched_patterns=pat_res.matched_patterns,
        tool_calls=tool_calls,
        latency_ms=latency_ms,
        claimed_entity=claimed_entity,
    )

    return report


def main():
    default_text = (
        "Dear Customer, your HDFC account will be blocked today. "
        "Complete KYC immediately: https://hdfc-secure-kyc.in/verify"
    )
    parser = argparse.ArgumentParser(description="PayGuard Arm 0 - Deterministic Pipeline")
    parser.add_argument(
        "--text",
        type=str,
        default=default_text,
        help="Input message text to analyze",
    )
    parser.add_argument("--url", type=str, default=None, help="Optional external URL")
    args = parser.parse_args()

    case_urls = [args.url] if args.url else []
    case = NormalisedCase(
        case_id=f"case_{uuid.uuid4().hex[:6]}",
        input_types=["text"],
        text=args.text,
        text_source="user",
        urls=case_urls,
    )

    report = run_arm0(case)

    print("\n" + "=" * 65)
    print(f"PAYGUARD ARM 0 VERDICT: {report.risk_level} (Score: {int(report.risk_score)})")
    print("=" * 65)
    print(f"HEADLINE:\n  {report.headline}\n")
    print(f"EVIDENCE LEDGER ({len(report.evidence)} items):")
    for e in report.evidence:
        quote_part = f' | quote: "{e.quote}"' if e.quote else ""
        kb_part = f" | {e.kb_ref}" if e.kb_ref else ""
        print(f"  [{e.id}] {e.tool:<20} {e.signal.value:<25} ({e.strength}){quote_part}{kb_part}")

    print("\nWHY EXPLANATION:")
    for w in report.why:
        print(f"  - {w.text} [Citations: {', '.join(w.evidence_ids)}]")

    print("\nRECOMMENDED ACTIONS:")
    for act in report.recommended_actions:
        print(f"  * {act}")

    meta = (
        f"policy={report.policy_version} | "
        f"kb={report.kb_version} | "
        f"latency={report.latency_ms}ms"
    )
    print(f"\nMETADATA: {meta}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
