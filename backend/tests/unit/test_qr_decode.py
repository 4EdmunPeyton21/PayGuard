from pathlib import Path

import qrcode
from PIL import Image

from app.tools.qr_decode import qr_decode


def _make_qr(tmp_path: Path, payload: str, name: str = "qr.png") -> str:
    path = tmp_path / name
    qrcode.make(payload).save(str(path))
    return str(path)


def test_decodes_upi_uri(tmp_path: Path):
    payload = "upi://pay?pa=rahul.kumar@oksbi&pn=RAHUL%20K&am=5000&cu=INR&tn=fee&mc=1234"
    path = _make_qr(tmp_path, payload)

    result = qr_decode(path)

    assert result.decoded is True
    assert result.payload_type == "upi"
    assert result.raw_payload == payload
    assert result.upi_fields is not None
    assert result.upi_fields.payee_vpa == "rahul.kumar@oksbi"
    assert result.upi_fields.payee_name == "RAHUL K"
    assert result.upi_fields.amount == 5000.0
    assert result.upi_fields.currency == "INR"
    assert result.upi_fields.merchant_code == "1234"


def test_decodes_url(tmp_path: Path):
    path = _make_qr(tmp_path, "https://example.com/pay")

    result = qr_decode(path)

    assert result.decoded is True
    assert result.payload_type == "url"
    assert result.url == "https://example.com/pay"


def test_decodes_plain_text(tmp_path: Path):
    path = _make_qr(tmp_path, "just some text, not a link or upi uri")

    result = qr_decode(path)

    assert result.decoded is True
    assert result.payload_type == "text"
    assert result.upi_fields is None
    assert result.url is None


def test_image_without_qr_returns_false(tmp_path: Path):
    path = tmp_path / "blank.png"
    Image.new("RGB", (100, 100), color="white").save(path)

    result = qr_decode(str(path))

    assert result.decoded is False
    assert result.payload_type == "none"


def test_missing_file_returns_false():
    result = qr_decode("/does/not/exist.png")

    assert result.decoded is False
    assert result.payload_type == "none"
