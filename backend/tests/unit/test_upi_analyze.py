from app.schemas.evidence import Signal
from app.schemas.tools import UpiFields
from app.tools.upi_analyze import upi_analyze


def test_refund_qr_produces_all_three_signals():
    """The D22 'Done when' case: personal VPA, tiny collect vs a big stated refund."""
    fields = UpiFields(
        payee_vpa="random.person@ybl", payee_name="RAHUL KUMAR", amount=1.0, currency="INR"
    )
    context = "I was told I'd receive a Rs 2,000 refund from Flipkart."

    result = upi_analyze(fields, payment_context=context)

    assert result.payee_is_merchant_vpa is False
    assert result.payee_handle == "ybl"
    assert result.expected_amount == 2000.0
    assert result.amount_mismatch is True
    assert Signal.UPI_COLLECT_REQUEST in result.signals
    assert Signal.UPI_PAYEE_MISMATCH in result.signals
    assert Signal.UPI_AMOUNT_MISMATCH in result.signals


def test_merchant_vpa_does_not_fire_payee_mismatch():
    fields = UpiFields(payee_vpa="flipkart@paytmqr", amount=500.0, merchant_code="5411")

    result = upi_analyze(fields, payment_context="Paying Rs 500 delivery fee")

    assert result.payee_is_merchant_vpa is True
    assert Signal.UPI_PAYEE_MISMATCH not in result.signals


def test_amount_within_tolerance_is_not_a_mismatch():
    fields = UpiFields(payee_vpa="shop@ybl", amount=505.0, merchant_code="5411")

    result = upi_analyze(fields, payment_context="Rs 500 delivery fee")

    assert result.amount_mismatch is False
    assert Signal.UPI_AMOUNT_MISMATCH not in result.signals


def test_no_payment_context_extracts_nothing():
    fields = UpiFields(payee_vpa="someone@ybl", amount=100.0)

    result = upi_analyze(fields, payment_context=None)

    assert result.stated_purpose is None
    assert result.expected_amount is None
    assert result.signals == []


def test_payee_handle_none_without_at_sign():
    fields = UpiFields(payee_vpa="not-a-valid-vpa")

    result = upi_analyze(fields, payment_context=None)

    assert result.payee_handle is None
