from app.kb.loader import kb


def test_kb_loads_entities():
    """Knowledge base loads all 10 seed entities."""
    assert len(kb.entities) == 10
    assert "hdfc_bank" in kb.entities
    assert "sbi" in kb.entities
    assert "icici_bank" in kb.entities
    assert "axis_bank" in kb.entities
    assert "phonepe" in kb.entities
    assert "paytm" in kb.entities
    assert "google_pay" in kb.entities
    assert "amazon_in" in kb.entities
    assert "flipkart" in kb.entities
    assert "india_post" in kb.entities


def test_kb_version_hash():
    """kb.version returns a version string starting with 'kb@' and a hex content hash."""
    assert kb.version.startswith("kb@")
    assert len(kb.version) == 11  # "kb@" + 8 hex chars


def test_resolve_entity_hdfc_variants():
    """resolve_entity matches English name, acronym alias,
    and Devanagari alias to the same entity id."""
    by_name = kb.resolve_entity("HDFC Bank")
    by_alias = kb.resolve_entity("hdfc")
    by_hindi = kb.resolve_entity("एचडीएफसी")

    assert by_name is not None
    assert by_alias is not None
    assert by_hindi is not None

    assert by_name.id == "hdfc_bank"
    assert by_alias.id == "hdfc_bank"
    assert by_hindi.id == "hdfc_bank"


def test_resolve_entity_other_banks_and_services():
    """resolve_entity works for SBI, PhonePe, Paytm, and India Post."""
    sbi_entity = kb.resolve_entity("SBI")
    assert sbi_entity is not None
    assert sbi_entity.id == "sbi"
    assert "sbi.co.in" in sbi_entity.official_domains

    phonepe = kb.resolve_entity("phonepe")
    assert phonepe is not None
    assert phonepe.id == "phonepe"

    post = kb.resolve_entity("India Post")
    assert post is not None
    assert post.id == "india_post"
    assert "indiapost.gov.in" in post.official_domains


def test_resolve_unknown_entity():
    """resolve_entity returns None for unknown, empty, or garbage strings."""
    assert kb.resolve_entity("random_unknown_bank_12345") is None
    assert kb.resolve_entity("") is None
    assert kb.resolve_entity(None) is None
    assert kb.resolve_entity("   ") is None


def test_entity_never_asks_for():
    """Entities declare sensitive fields they never ask for."""
    hdfc = kb.get_entity("hdfc_bank")
    assert hdfc is not None
    assert "otp" in hdfc.never_asks_for
    assert "pin" in hdfc.never_asks_for
