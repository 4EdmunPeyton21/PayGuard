import re
from urllib.parse import urlparse

import Levenshtein
import tldextract

from app.kb.loader import kb
from app.schemas.evidence import Signal
from app.schemas.tools import LookalikeCandidate, UrlInspectResult

SHORTENERS = {
    "bit.ly", "t.co", "tinyurl.com", "is.gd", "goo.gl", "ow.ly", "buff.ly", "cutt.ly"
}

# Empty suffix_list_urls prevents any network calls. Deterministic offline behavior using snapshot.
extract = tldextract.TLDExtract(suffix_list_urls=(), fallback_to_snapshot=True)

def url_inspect(url: str) -> UrlInspectResult:
    original_url = url
    if not url.startswith(("http://", "https://")):
        url = "http://" + url

    parsed = urlparse(url)
    ext = extract(url)

    fallback_domain = f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain
    registered_domain = getattr(ext, "top_domain_under_public_suffix", "") or fallback_domain
    subdomain = ext.subdomain
    tld = ext.suffix

    # 1. IP Address Host
    is_ip_host = False
    if ext.domain and not ext.suffix:
        # e.g. 192.168.1.1
        if re.match(r'^[\d\.]+$', ext.domain):
            is_ip_host = True
    elif parsed.hostname and re.match(r'^[\d\.]+$', parsed.hostname):
        is_ip_host = True

    # 2. Punycode (Cyrillic lookalikes etc.)
    is_punycode = False
    if parsed.hostname:
        try:
            encoded_host = parsed.hostname.encode("idna").decode("ascii")
            if "xn--" in encoded_host:
                is_punycode = True
        except Exception:
            if "xn--" in parsed.hostname:
                is_punycode = True

    # 3. Link Shortener
    is_shortener = False
    if registered_domain and registered_domain.lower() in SHORTENERS:
        is_shortener = True

    # Metrics
    hyphen_count = registered_domain.count("-") if registered_domain else 0
    subdomain_depth = len([p for p in subdomain.split(".") if p]) if subdomain else 0

    # 4. Brand tokens outside domain
    # Extract components from subdomain, path, and domain
    tokens = set()
    if subdomain:
        tokens.update(p.lower() for p in subdomain.split("."))
    if parsed.path:
        tokens.update(p.lower() for p in parsed.path.split("/") if p)
    if ext.domain:
        tokens.update(p.lower() for p in ext.domain.split("-"))

    brand_tokens_found = []
    lookalike_candidates = []
    signals = set()

    if is_ip_host:
        signals.add(Signal.IP_ADDRESS_HOST)
    if is_punycode:
        signals.add(Signal.PUNYCODE_HOST)
    if is_shortener:
        signals.add(Signal.LINK_SHORTENER)
    if subdomain_depth > 2:
        signals.add(Signal.EXCESSIVE_SUBDOMAINS)

    # Resolve Lookalikes & Brand Tokens
    for entity in kb.entities.values():
        official_domains = [d.lower() for d in entity.official_domains]
        if registered_domain and registered_domain.lower() in official_domains:
            continue  # It's officially theirs.

        # Build entity tokens (id, name, aliases)
        entity_tokens = {entity.id.lower(), entity.name.lower()}
        for alias in entity.aliases:
            entity_tokens.add(alias.lower())

        found = tokens.intersection(entity_tokens)
        if found:
            brand_tokens_found.extend(list(found))
            # Tag as brand token reuse lookalike candidate
            if official_domains:
                off = official_domains[0]
                dist = Levenshtein.distance(registered_domain or "", off)
                lookalike_candidates.append(
                    LookalikeCandidate(official=off, distance=dist, kind="brand_token_reuse")
                )

        # Direct typosquatting check (edit distance 1-2 on registered domain vs official domain)
        if registered_domain:
            for off in official_domains:
                dist = Levenshtein.distance(registered_domain.lower(), off)
                if 0 < dist <= 2:
                    lookalike_candidates.append(
                        LookalikeCandidate(official=off, distance=dist, kind="typosquatting")
                    )

    # Deduplicate brand tokens and lookalikes
    brand_tokens_found = list(set(brand_tokens_found))
    unique_candidates = {
        (c.official, c.distance, c.kind): c for c in lookalike_candidates
    }
    lookalike_candidates = list(unique_candidates.values())

    if brand_tokens_found:
        signals.add(Signal.BRAND_TOKEN_OUTSIDE_DOMAIN)

    if lookalike_candidates:
        signals.add(Signal.LOOKALIKE_DOMAIN)

    return UrlInspectResult(
        url=original_url,
        scheme=parsed.scheme or "http",
        registered_domain=registered_domain or "",
        subdomain=subdomain or "",
        tld=tld or "",
        path=parsed.path or "",
        is_ip_host=is_ip_host,
        is_punycode=is_punycode,
        is_shortener=is_shortener,
        hyphen_count=hyphen_count,
        subdomain_depth=subdomain_depth,
        brand_token_outside_domain=brand_tokens_found,
        lookalike_candidates=lookalike_candidates,
        signals=list(signals),
    )
