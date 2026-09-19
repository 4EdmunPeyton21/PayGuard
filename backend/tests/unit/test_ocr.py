from pathlib import Path

from PIL import Image, ImageDraw

from app.ingest.ocr import OCR_CONFIDENCE_THRESHOLD, extract_text


def _render_sms(tmp_path: Path, lines: list[str]) -> str:
    path = tmp_path / "sms.png"
    img = Image.new("RGB", (700, 40 * len(lines) + 20), color="white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((10, 10 + i * 40), line, fill="black")
    img.save(path)
    return str(path)


def test_extracts_text_from_rendered_sms(tmp_path: Path):
    path = _render_sms(
        tmp_path,
        ["Dear customer, your account will be blocked today."],
    )

    result = extract_text(path)

    assert "account" in result.text.lower()
    assert "blocked" in result.text.lower()
    assert result.line_count == 1
    assert 0.0 <= result.confidence <= 1.0


def test_confidence_flag_is_consistent_with_threshold(tmp_path: Path):
    path = _render_sms(tmp_path, ["Some ordinary readable text here"])

    result = extract_text(path)

    assert result.low_confidence == (result.confidence < OCR_CONFIDENCE_THRESHOLD)


def test_blank_image_returns_empty_low_confidence(tmp_path: Path):
    path = tmp_path / "blank.png"
    Image.new("RGB", (200, 100), color="white").save(path)

    result = extract_text(str(path))

    assert result.text == ""
    assert result.low_confidence is True
    assert result.line_count == 0
