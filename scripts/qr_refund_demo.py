"""D22 demo: the refund-QR case.

Generates a "scan to receive your Rs 2,000 refund" QR that actually
encodes a UPI *collect* request to a personal VPA, then runs it through
qr_decode -> upi_analyze exactly as the agent would, and checks the
result carries upi_collect_request, upi_payee_mismatch, and
upi_amount_mismatch.

Run: python scripts/qr_refund_demo.py
"""
import os
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

import qrcode  # noqa: E402
from app.schemas.evidence import Signal  # noqa: E402
from app.tools.qr_decode import qr_decode  # noqa: E402
from app.tools.upi_analyze import upi_analyze  # noqa: E402

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "..", "eval", "dataset", "fixtures")
QR_PATH = os.path.join(FIXTURE_DIR, "qr_refund_demo.png")

# A real "refund" QR would never exist -- scanning a UPI QR always creates a
# pay/collect intent from the scanner. This one collects Rs 1 from whoever
# scans it, to a personal VPA, while the message claims a Rs 2,000 refund.
UPI_URI = (
    "upi://pay?pa=" + quote("random.person@ybl")
    + "&pn=" + quote("RAHUL KUMAR")
    + "&am=1&cu=INR&tn=" + quote("Refund verification")
)
PAYMENT_CONTEXT = "I was told I'd receive a Rs 2,000 refund from Flipkart for a cancelled order."


def main() -> None:
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    qrcode.make(UPI_URI).save(QR_PATH)
    print(f"Generated demo QR at {QR_PATH}")

    decoded = qr_decode(QR_PATH)
    print("qr_decode ->", decoded.model_dump())
    assert decoded.decoded is True
    assert decoded.payload_type == "upi"
    assert decoded.upi_fields is not None

    analysis = upi_analyze(decoded.upi_fields, payment_context=PAYMENT_CONTEXT)
    print("upi_analyze ->", analysis.model_dump())

    expected_signals = (
        Signal.UPI_COLLECT_REQUEST,
        Signal.UPI_PAYEE_MISMATCH,
        Signal.UPI_AMOUNT_MISMATCH,
    )
    for expected in expected_signals:
        assert expected in analysis.signals, f"expected {expected} in {analysis.signals}"

    print("\nPASS: refund-QR case produced", [s.value for s in analysis.signals])


if __name__ == "__main__":
    main()
