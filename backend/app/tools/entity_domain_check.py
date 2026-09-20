from typing import List, Optional
from urllib.parse import urlparse

from app.kb.loader import kb
from app.schemas.evidence import Signal
from app.schemas.tools import EntityDomainCheckResult


def _normalize_host(cand: str) -> str:
    cand = cand.strip().lower()
    if "://" not in cand:
        cand = "http://" + cand
    parsed = urlparse(cand)
    host = parsed.hostname or ""
    return host


def _domain_matches(candidate: str, official: str) -> bool:
    cand_host = _normalize_host(candidate)
    off_host = _normalize_host(official)
    if not cand_host or not off_host:
        return False
    if cand_host == off_host:
        return True
    if cand_host.endswith("." + off_host):
        return True
    return False


def entity_domain_check(
    claimed_entity: str,
    domains: Optional[List[str]] = None,
    domain: Optional[str] = None,
    **kwargs,
) -> EntityDomainCheckResult:
    """Check claimed entity against domains strictly using the YAML knowledge base.

    Contract:
    in: claimed_entity: str, domains: list[str]
    out: EntityDomainCheckResult with match, official_domains, entity_in_kb, kb_ref.
    """
    if domains is None:
        domains = []
    elif isinstance(domains, str):
        domains = [domains]
    else:
        domains = list(domains)

    if domain and domain not in domains:
        domains.append(domain)

    entity = kb.resolve_entity(claimed_entity)

    if entity is None:
        return EntityDomainCheckResult(
            claimed_entity=claimed_entity,
            resolved_entity_id=None,
            entity_in_kb=False,
            official_domains=[],
            match=False,
            matched_domain=None,
            unmatched_domains=list(domains),
            kb_ref=None,
            signals=[Signal.UNKNOWN_ENTITY],
        )

    # STRICT RULE: ONLY the entity loaded from YAML supplies official domains.
    official_domains = list(entity.official_domains)
    version_hash = kb.version.split("@")[-1] if "@" in kb.version else kb.version
    kb_ref = f"kb:entity:{entity.id}@{version_hash}"

    matched_domains: List[str] = []
    unmatched_domains: List[str] = []

    for d in domains:
        if any(_domain_matches(d, off) for off in official_domains):
            matched_domains.append(d)
        else:
            unmatched_domains.append(d)

    match = len(matched_domains) > 0 and len(unmatched_domains) == 0
    matched_domain: Optional[str] = matched_domains[0] if matched_domains else None

    signals: List[Signal] = []
    if match:
        signals.append(Signal.DOMAIN_VERIFIED_OFFICIAL)
    elif len(unmatched_domains) > 0:
        signals.append(Signal.DOMAIN_MISMATCH)

    return EntityDomainCheckResult(
        claimed_entity=claimed_entity,
        resolved_entity_id=entity.id,
        entity_in_kb=True,
        official_domains=official_domains,
        match=match,
        matched_domain=matched_domain,
        unmatched_domains=unmatched_domains,
        kb_ref=kb_ref,
        signals=signals,
    )
