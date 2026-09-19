"""PayGuard qr_decode tool — T4.

Contract:
  in:  image_ref: str (path to an image containing a QR code)
  out: QrDecodeResult(decoded, payload_type, raw_payload, upi_fields, url)

Deterministic: decode with OpenCV's built-in QR detector, classify the
payload (upi:// / http(s):// / plain text), and for a UPI URI parse its
query params. Returns decoded=False honestly rather than guessing — never
invents a payload for an image that doesn't hold a readable QR code.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import parse_qs, urlparse

import cv2

from app.schemas.tools import QrDecodeResult, UpiFields


def _parse_upi_uri(raw: str) -> UpiFields:
    params = parse_qs(urlparse(raw).query)

    def first(key: str) -> Optional[str]:
        values = params.get(key)
        return values[0] if values else None

    amount: Optional[float] = None
    raw_amount = first("am")
    if raw_amount:
        try:
            amount = float(raw_amount)
        except ValueError:
            amount = None

    return UpiFields(
        payee_vpa=first("pa"),
        payee_name=first("pn"),
        amount=amount,
        currency=first("cu"),
        transaction_note=first("tn"),
        merchant_code=first("mc"),
    )


def qr_decode(image_ref: str) -> QrDecodeResult:
    image = cv2.imread(image_ref)
    if image is None:
        return QrDecodeResult(decoded=False, payload_type="none")

    raw, _points, _straight = cv2.QRCodeDetector().detectAndDecode(image)
    if not raw:
        return QrDecodeResult(decoded=False, payload_type="none")

    if raw.startswith("upi://"):
        return QrDecodeResult(
            decoded=True,
            payload_type="upi",
            raw_payload=raw,
            upi_fields=_parse_upi_uri(raw),
        )
    if raw.startswith("http://") or raw.startswith("https://"):
        return QrDecodeResult(decoded=True, payload_type="url", raw_payload=raw, url=raw)

    return QrDecodeResult(decoded=True, payload_type="text", raw_payload=raw)
