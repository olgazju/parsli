"""Tests for rule-based status extraction."""

import pytest

from parsli.processing.rule_engine import RuleEngine

engine = RuleEngine()


def extract(text: str, sender_domain: str | None = None):
    return engine.extract("test_id", text, sender_domain=sender_domain)


def test_israel_post_pickup_delivered():
    # Hebrew Israel Post pickup confirmation → delivered
    result = extract("תודה שאספת את המשלוח שלך בדואר ישראל. המשלוח הגיע לסניף ביום שישי.")
    assert result.status is not None
    assert result.status.value == "delivered"
    assert result.status_confidence >= 0.90


def test_hfd_collect_before_action_required():
    result = extract(
        "Your parcel is waiting. Please collect before the deadline or it will be returned."
    )
    assert result.status is not None
    assert result.status.value == "action_required"


def test_invoice_not_shipping():
    result = extract(
        "Invoice #12345 — Thank you for your payment. Total: $49.99. "
        "This is your receipt for order #98765."
    )
    assert result.is_invoice is True
    assert result.is_shipping_email is False


def test_out_for_delivery():
    result = extract("Great news! Your package is out for delivery today.")
    assert result.status is not None
    assert result.status.value == "out_for_delivery"


def test_ready_for_pickup():
    result = extract("Your parcel is ready for pickup at branch 42.")
    assert result.status is not None
    assert result.status.value == "ready_for_pickup"


def test_customs_payment_required():
    result = extract(
        "Your shipment has been held. A customs duty of 38 ILS is required to release it."
    )
    assert result.status is not None
    assert result.status.value == "payment_required"
    assert result.amount == 38.0
    assert result.currency == "ILS"


def test_hebrew_shipped():
    result = extract("ההזמנה שלך נשלחה! מספר מעקב: RU012345678IL")
    assert result.status is not None
    assert result.status.value == "shipped"


def test_delivered_terminal():
    result = extract("Your order has been delivered. Thank you for shopping with us!")
    assert result.status is not None
    assert result.status.value == "delivered"


@pytest.mark.parametrize("domain", [
    "payplus.co.il",
    "paypal.com",
    "stripe.com",
    "cardcom.co.il",
    "tranzila.com",
    "isracard.co.il",
])
def test_payment_processor_domain_excluded(domain: str):
    # Even if the body text looks like a shipping email, a payment processor
    # sender domain must set is_invoice=True and suppress all shipping signals.
    result = extract(
        "Your shipment has been dispatched. Tracking: RU012345678IL",
        sender_domain=domain,
    )
    assert result.is_invoice is True
    assert result.is_shipping_email is False
    assert result.status is None


def test_payment_processor_subdomain_not_excluded():
    # Only exact known domains are blocked — an unrelated domain that happens
    # to contain a keyword should pass through normally.
    result = extract(
        "Your parcel has been delivered.",
        sender_domain="notifications.myshop.com",
    )
    assert result.is_invoice is False
