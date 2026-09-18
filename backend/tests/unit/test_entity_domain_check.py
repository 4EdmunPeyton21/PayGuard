from app.kb.loader import kb
from app.schemas.evidence import Signal
from app.tools.entity_domain_check import entity_domain_check


def test_hdfc_bank_mismatch():
    res = entity_domain_check("HDFC Bank", ["hdfc-secure-kyc.in"])
    assert res.match is False
    assert res["match"] is False
    assert res.entity_in_kb is True
    assert "hdfcbank.com" in res.official_domains
    assert res.kb_ref is not None
    assert res.kb_ref.startswith("kb:entity:hdfc_bank@")
    assert Signal.DOMAIN_MISMATCH in res.signals
    assert "hdfc-secure-kyc.in" in res.unmatched_domains


def test_hdfc_bank_match():
    res = entity_domain_check("HDFC Bank", ["hdfcbank.com"])
    assert res.match is True
    assert res["match"] is True
    assert res.entity_in_kb is True
    assert res.matched_domain == "hdfcbank.com"
    assert len(res.unmatched_domains) == 0
    assert Signal.DOMAIN_VERIFIED_OFFICIAL in res.signals


def test_nonexistent_bank():
    res = entity_domain_check("Nonexistent Bank", ["https://anydomain.com"])
    assert res.entity_in_kb is False
    assert res["entity_in_kb"] is False
    assert res.match is False
    assert res.kb_ref is None
    assert res.official_domains == []
    assert Signal.UNKNOWN_ENTITY in res.signals


def test_official_domains_strictly_from_yaml():
    # Proves official domains come strictly from YAML KB
    res = entity_domain_check("HDFC Bank", ["hdfcbank.com"])
    entity = kb.get_entity("hdfc_bank")
    assert entity is not None
    assert res.official_domains == entity.official_domains


def test_subdomain_and_url_normalization():
    # Genuine bank subdomain
    res = entity_domain_check("HDFC", ["https://netbanking.hdfcbank.com/portal"])
    assert res.match is True
    assert res.entity_in_kb is True

    # Attack lookalike where official domain is just in subdomain
    res_attack = entity_domain_check("HDFC Bank", ["hdfcbank.com.verify-kyc.ru"])
    assert res_attack.match is False
    assert Signal.DOMAIN_MISMATCH in res_attack.signals
