"""PayGuard upi_analyze tool — T5.

Contract:
  in:  upi_fields: UpiFields, payment_context: str | None
  out: UpiAnalysisResult — parsed fields + upi_collect_request /
       upi_payee_mismatch / upi_amount_mismatch signals

Deterministic. stated_purpose/expected_amount come from payment_context
via regex, not an LLM call: the free text in scope here is short (a
currency amount plus a short reason), and keeping the tool pure keeps it
inside the arg-hash cache the registry (D13) already built around
deterministic tools.
# ponytail: regex amount/purpose extraction; swap for an LLM extraction
# call if eval turns up phrasing the regex can't parse.

The core insight this tool encodes: scanning a UPI QR always creates a
pay/collect intent from the scanner's account. There is no such thing as
a "receive money" QR — a message that says otherwise is the tell.
"""
from __future__ import annotations

import re
from typing import List, Optional

from app.schemas.evidence import Signal
from app.schemas.tools import UpiAnalysisResult, UpiFields

_RECEIVE_WORDS = re.compile(
    r"\b(refund|receive|cashback|reward|prize|winning|won|credited back)\b",
    re.IGNORECASE,
)

_AMOUNT_RE = re.compile(r"(?:₹|rs\.?|inr)\s*([\d][\d,]*(?:\.\d+)?)", re.IGNORECASE)

_MISMATCH_TOLERANCE = 0.15  # +-15% isn't a mismatch -- QR fees round


def _extract_expected_amount(payment_context: str) -> Optional[float]:
    match = _AMOUNT_RE.search(payment_context)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def upi_analyze(
    upi_fields: UpiFields,
    payment_context: Optional[str] = None,
) -> UpiAnalysisResult:
    payee_handle: Optional[str] = None
    if upi_fields.payee_vpa and "@" in upi_fields.payee_vpa:
        payee_handle = upi_fields.payee_vpa.split("@", 1)[1]

    payee_is_merchant_vpa = bool(upi_fields.merchant_code and upi_fields.merchant_code.strip())

    stated_purpose: Optional[str] = None
    expected_amount: Optional[float] = None
    if payment_context and payment_context.strip():
        stated_purpose = payment_context.strip()
        expected_amount = _extract_expected_amount(payment_context)

    amount_mismatch = False
    amount_ratio: Optional[float] = None
    if expected_amount and upi_fields.amount is not None and expected_amount > 0:
        amount_ratio = upi_fields.amount / expected_amount
        amount_mismatch = abs(amount_ratio - 1.0) > _MISMATCH_TOLERANCE

    signals: List[Signal] = []
    if payment_context and _RECEIVE_WORDS.search(payment_context):
        signals.append(Signal.UPI_COLLECT_REQUEST)
    if stated_purpose is not None and not payee_is_merchant_vpa:
        signals.append(Signal.UPI_PAYEE_MISMATCH)
    if amount_mismatch:
        signals.append(Signal.UPI_AMOUNT_MISMATCH)

    return UpiAnalysisResult(
        payee_vpa=upi_fields.payee_vpa,
        payee_name=upi_fields.payee_name,
        amount=upi_fields.amount,
        currency=upi_fields.currency,
        stated_purpose=stated_purpose,
        expected_amount=expected_amount,
        amount_mismatch=amount_mismatch,
        amount_ratio=amount_ratio,
        payee_handle=payee_handle,
        payee_is_merchant_vpa=payee_is_merchant_vpa,
        signals=signals,
    )
