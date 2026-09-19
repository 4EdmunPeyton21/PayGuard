"""PayGuard OCR ingest — D23.

Contract:
  in:  image_ref: str (path to an uploaded screenshot)
  out: OcrResult(text, confidence, low_confidence, line_count)

Uses rapidocr (already a dependency, shared with the QR path) to pull text
out of a screenshot. Confidence is the mean per-line score; below
OCR_CONFIDENCE_THRESHOLD, low_confidence=True and the caller should show
the user the extracted text to confirm/edit before it's investigated --
that confirm-text step, not OCR accuracy, is the actual reliability
strategy here (D23's "Don't fight OCR quality").
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

OCR_CONFIDENCE_THRESHOLD = 0.75

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
    return _engine


class OcrResult(BaseModel):
    text: str
    confidence: float
    low_confidence: bool
    line_count: int


def extract_text(image_ref: str) -> OcrResult:
    lines_result: Optional[list] = _get_engine()(image_ref)[0]
    if not lines_result:
        return OcrResult(text="", confidence=0.0, low_confidence=True, line_count=0)

    lines: List[str] = [line[1] for line in lines_result]
    scores: List[float] = [float(line[2]) for line in lines_result]
    confidence = sum(scores) / len(scores)

    return OcrResult(
        text="\n".join(lines),
        confidence=confidence,
        low_confidence=confidence < OCR_CONFIDENCE_THRESHOLD,
        line_count=len(lines),
    )
