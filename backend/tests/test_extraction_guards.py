"""Tests for extraction-stage guards: Hebrew footer cleaning, billing exclusion,
and context-guarded pure-digit tracking extraction."""

from parsli.domain.identifiers import extract_tracking_candidates
from parsli.processing.cleaner import EmailCleaner
from parsli.processing.rule_engine import RuleEngine

cleaner = EmailCleaner()
engine = RuleEngine()


# ── Hebrew footer cleaning ────────────────────────────────────────────────────


def test_hebrew_footer_stripped_before_classification() -> None:
    body = (
        "שלום Olga Braginskaya,\n"
        "פירוט החיובים התקופתי שלך כבר כאן!\n"
        "הודעה זו נשלחה ל- olgazjuzju@gmail.com על ידי DoNotReply@moovit-pango.co.il\n"
        "נשלח באמצעות מסר עשר מערכת דיוור אלקטרוני ומסרונים"
    )
    result = cleaner.clean("x", body)
    assert "הודעה זו נשלחה ל-" not in result.cleaned_text
    assert "נשלח באמצעות" not in result.cleaned_text
    assert "מערכת דיוור" not in result.cleaned_text


# ── Billing / invoice exclusion ───────────────────────────────────────────────


def test_pango_billing_is_invoice() -> None:
    body = "פירוט חיובים תקופתי — ריכזנו עבורך את פירוט החיובים לשנת 2025"
    result = engine.extract("x", body)
    assert result.is_invoice is True
    assert result.is_shipping_email is False
    assert result.status is None


def test_billing_with_periodic_charges_term() -> None:
    body = "חיובים תקופתיים לחודש מאי — סכום: 49.90 ₪"
    result = engine.extract("x", body)
    assert result.is_invoice is True
    assert result.is_shipping_email is False


# ── Context-guarded pure-digit extraction ─────────────────────────────────────


def test_dhl_without_context_not_extracted() -> None:
    # 10-digit number appearing alone in billing text — must not be extracted
    body = "חיוב מספר 0546541173 עבור שירות תקשורת. סכום: 89.90 ₪."
    candidates = extract_tracking_candidates(body)
    dhl_hits = [c for c in candidates if c.carrier_hint == "dhl"]
    assert dhl_hits == []


def test_fedex_without_context_not_extracted() -> None:
    # 15-digit number in a billing context — must not be extracted
    body = "מספר עסקה: 123456789012345. תאריך: 22.05.2026. סכום: 120.00 ₪."
    candidates = extract_tracking_candidates(body)
    fedex_hits = [c for c in candidates if c.carrier_hint == "fedex"]
    assert fedex_hits == []


def test_tracking_with_hebrew_context_extracted() -> None:
    # Israel Post format: 2 letters + 8 digits + 2 letters (format-specific, always extracted)
    body = "ההזמנה שלך נשלחה! מספר מעקב: RU01234567IL"
    candidates = extract_tracking_candidates(body)
    values = [c.value for c in candidates]
    assert "RU01234567IL" in values


def test_tracking_with_english_context_extracted() -> None:
    # 15-digit FedEx number with "tracking number" nearby — must be extracted
    body = "Your shipment is on its way. Tracking number: 123456789012345. Expected: tomorrow."
    candidates = extract_tracking_candidates(body)
    fedex_hits = [c for c in candidates if c.carrier_hint == "fedex"]
    assert len(fedex_hits) == 1
    assert fedex_hits[0].value == "123456789012345"
    assert fedex_hits[0].source == "body_near_keyword"
