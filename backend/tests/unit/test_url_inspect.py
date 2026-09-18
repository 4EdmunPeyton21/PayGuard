from app.schemas.evidence import Signal
from app.tools.url_inspect import url_inspect


def test_url_inspect_hdfc_lookalike():
    res = url_inspect("hdfcbank.com.verify-kyc.ru")
    assert Signal.LOOKALIKE_DOMAIN in res.signals
    assert Signal.BRAND_TOKEN_OUTSIDE_DOMAIN in res.signals
    assert "hdfcbank" in res.brand_token_outside_domain
    assert res.registered_domain == "verify-kyc.ru"

def test_url_inspect_ip_address():
    res = url_inspect("192.168.1.1/hdfc")
    assert Signal.IP_ADDRESS_HOST in res.signals
    # hdfc is also a brand token inside the path
    assert Signal.BRAND_TOKEN_OUTSIDE_DOMAIN in res.signals
    assert "hdfc" in res.brand_token_outside_domain
    assert res.is_ip_host is True

def test_url_inspect_link_shortener():
    res = url_inspect("bit.ly/x")
    assert Signal.LINK_SHORTENER in res.signals
    assert res.is_shortener is True

def test_url_inspect_sbi_clean():
    res = url_inspect("sbi.co.in")
    assert len(res.signals) == 0
    assert res.registered_domain == "sbi.co.in"

def test_url_inspect_cyrillic_lookalike():
    # 'с' is a Cyrillic character (U+0441), making it punycode
    url = "hdfсbank.com"
    res = url_inspect(url)
    assert Signal.PUNYCODE_HOST in res.signals
    assert res.is_punycode is True
