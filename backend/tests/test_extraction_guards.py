"""Tests for extraction-stage guards: Hebrew footer cleaning, billing exclusion,
context-guarded pure-digit tracking extraction, and regression cases."""

from parsli.domain.identifiers import extract_order_candidates, extract_tracking_candidates
from parsli.processing.cleaner import EmailCleaner
from parsli.processing.rule_engine import RuleEngine

cleaner = EmailCleaner()
engine = RuleEngine()


# ── Hebrew footer cleaning ────────────────────────────────────────────────────


def test_hebrew_footer_stripped_before_classification() -> None:
    body = (
        "שלום Test User,\n"
        "פירוט החיובים התקופתי שלך כבר כאן!\n"
        "הודעה זו נשלחה ל- user@example.com על ידי DoNotReply@moovit-pango.co.il\n"
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


# ── Invoice detection regressions ─────────────────────────────────────────────


def test_hoodies_order_confirmation_not_invoice() -> None:
    # "התקבלה" (was received) must not trigger invoice detection
    body = (
        "היי Alex Romanov,\n"
        "ההזמנה שביצעת באתר HOODIES התקבלה בהצלחה.\n"
        "מספר הזמנה שלך: #521231550\n"
        "לאחר מכן, הזמנתך עוברת למשלוח."
    )
    result = engine.extract("x", body)
    assert result.is_invoice is False


def test_hoodies_order_confirmation_extracts_order_number() -> None:
    body = (
        "היי Alex,\n"
        "ההזמנה שביצעת באתר HOODIES התקבלה בהצלחה.\n"
        "מספר הזמנה שלך: #521231550\n"
    )
    result = engine.extract("x", body)
    order_values = [o.value for o in result.order_candidates]
    assert "521231550" in order_values


def test_all4pet_order_confirmation_not_invoice() -> None:
    # Mention of חשבונית (invoice document) referring to a future invoice does not
    # mean the email itself is a billing invoice.
    body = (
        "שלום, הזמנתך התקבלה בהצלחה ותטופל בהקדם.\n"
        "בסיום התהליך ישלח אליך מייל עם פרטי החשבונית.\n"
        "מספר הזמנה: 450964 סיכום ההזמנה"
    )
    result = engine.extract("x", body)
    assert result.is_invoice is False


def test_all4pet_order_confirmation_extracts_order_number() -> None:
    body = (
        "שלום, הזמנתך התקבלה בהצלחה.\n"
        "מספר הזמנה: 450964 סיכום ההזמנה"
    )
    result = engine.extract("x", body)
    order_values = [o.value for o in result.order_candidates]
    assert "450964" in order_values


# ── Delayed-or-problem regressions ────────────────────────────────────────────


def test_cancellation_policy_delay_not_shipping_delay() -> None:
    # "יחול עיכוב בביטול" = "a delay in cancellation will apply" — legal text, not delivery.
    body = "בהיעדר פרטים כאמור, יחול עיכוב בביטול עד להבהרת הפרטים."
    result = engine.extract("x", body)
    assert result.status is None or result.status.value != "delayed_or_problem"


def test_generic_apology_delay_not_shipping_delay() -> None:
    body = "My sincerest apologies for the delay. I am so excited about this project."
    result = engine.extract("x", body)
    assert result.status is None or result.status.value != "delayed_or_problem"


def test_shipping_delay_is_classified() -> None:
    body = "We're sorry, your delivery has been delayed due to high demand."
    result = engine.extract("x", body)
    assert result.status is not None
    assert result.status.value == "delayed_or_problem"


# ── Tracking extraction regressions ──────────────────────────────────────────


def test_phone_number_in_url_not_extracted_as_tracking() -> None:
    # Phone numbers embedded in URL query params must be stripped by the cleaner.
    raw_body = (
        "המשלוח יימסר בכתובת שהוזנה.\n"
        "ניתן לעדכן את הכתובת בקישור [ לחץ כאן ]"
        "(https://israelpost.co.il/setaddress?barcode=RU01234567IL&phone=0545226889)\n"
    )
    cleaned = cleaner.clean("x", raw_body)
    candidates = extract_tracking_candidates(cleaned.cleaned_text)
    values = [c.value for c in candidates]
    assert "0545226889" not in values


def test_asos_css_font_name_not_extracted() -> None:
    # "asossansdisplay" is a CSS font-family name, not an ASOS tracking code.
    body = "font-family:'ASOS Sans Display';src:local('asossansdisplay')"
    candidates = extract_tracking_candidates(body)
    asos_hits = [c for c in candidates if c.carrier_hint == "asos"]
    assert asos_hits == []


def test_starlinks_subject_tracking_extracted() -> None:
    # Tracking number in subject must be extracted when subject is passed.
    subject = "Shipment in transit. Tracking Number: ASO1006GB02687136001"
    body = "Your shipment is being processed."
    result = engine.extract("x", body, subject=subject)
    values = [t.value for t in result.tracking_candidates]
    assert "ASO1006GB02687136001" in values


def test_url_token_not_extracted_as_tracking() -> None:
    # Token in URL query string must not be extracted as a tracking number.
    raw_body = "[  ](https://uclicks.inforu.net/?page=webview&token=15632131559-abc123)"
    cleaned = cleaner.clean("x", raw_body)
    candidates = extract_tracking_candidates(cleaned.cleaned_text)
    values = [c.value for c in candidates]
    assert "15632131559" not in values


# ── Order extraction regressions ──────────────────────────────────────────────


def test_order_junk_words_not_extracted() -> None:
    body = "Your order CONTAINS the following items. ORDER SUMMARY attached. ORDER DETAILS below."
    orders = extract_order_candidates(body)
    junk = {"CONTAINS", "SUMMARY", "DETAILS", "ORDER"}
    assert not any(o.value in junk for o in orders)


def test_amazon_order_number_extracted() -> None:
    body = "Your Amazon order 112-5902454-9986650 has shipped."
    orders = extract_order_candidates(body)
    values = [o.value for o in orders]
    assert "112-5902454-9986650" in values


def test_hebrew_order_number_extracted() -> None:
    body = "מספר הזמנה: 450964 סיכום ההזמנה"
    orders = extract_order_candidates(body)
    values = [o.value for o in orders]
    assert "450964" in values


def test_asos_junk_words_not_extracted() -> None:
    body = "If you have any ISSUES, please use this REFERENCE number. Your order 1041491735."
    orders = extract_order_candidates(body)
    junk = {"ISSUES", "REFERENCE"}
    assert not any(o.value in junk for o in orders)


# ── UPS delivered status ──────────────────────────────────────────────────────


def test_ups_delivered_classified() -> None:
    body = "משלוח מס' 1Z08407V0463442370 נמסר בשעה 18:46 והושאר ב- מבואה."
    result = engine.extract("x", body)
    assert result.status is not None
    assert result.status.value == "delivered"


def test_ups_delivered_subject_matched() -> None:
    # Status matching now includes the subject, so "המשלוח נמסר" in subject fires
    # DELIVERED even when the body alone has no matching phrase.
    subject = "המשלוח נמסר, נשמח לשמוע את דעתך על השירות"
    body = "תודה שבחרת ב-UPS. אנחנו מקווים שנהנית מהשירות."
    result = engine.extract("x", body, subject=subject)
    assert result.status is not None
    assert result.status.value == "delivered"


# ── Israel Post tracking number extraction ────────────────────────────────────


def test_israel_post_9digit_extracted_from_subject() -> None:
    # Real Israel Post numbers use 9 digits: LS233312341CH (2+9+2)
    subject = "הודעה על משלוח שמספרו LS233312341CH"
    body = "המשלוח שלך בדרך."
    result = engine.extract("x", body, subject=subject)
    values = [t.value for t in result.tracking_candidates]
    assert "LS233312341CH" in values


def test_israel_post_10digit_with_single_check_extracted() -> None:
    # 10-digit variant with single trailing letter: RU0136772947Z (2+10+1)
    subject = "הודעה על משלוח שמספרו RU0136772947Z"
    body = "המשלוח שלך בדרך."
    result = engine.extract("x", body, subject=subject)
    values = [t.value for t in result.tracking_candidates]
    assert "RU0136772947Z" in values


def test_israel_post_standard_still_extracted() -> None:
    # Standard UPU 2+8+2 format must still be extracted
    body = "מספר מעקב: RU01234567IL"
    candidates = extract_tracking_candidates(body)
    values = [c.value for c in candidates]
    assert "RU01234567IL" in values


# ── Order-labeled numbers must not appear in tracking ─────────────────────────


def test_order_labeled_number_not_in_tracking() -> None:
    # "Order #4500043904" is an order number; DHL pattern would match the digits
    # but the value must be filtered out of tracking_candidates.
    body = (
        "Your order was shipped via DHL\n"
        "Tracking Code: 4885422043\n"
        "Order Number:#4500043904\n"
    )
    result = engine.extract("x", body)
    tracking_values = [t.value for t in result.tracking_candidates]
    order_values = [o.value for o in result.order_candidates]
    assert "4885422043" in tracking_values       # real tracking kept
    assert "4500043904" in order_values           # correctly identified as order
    assert "4500043904" not in tracking_values   # must not bleed into tracking


# ── Amazon Ordered: subject prefix ────────────────────────────────────────────


def test_amazon_ordered_subject_is_order_confirmed() -> None:
    # Amazon "Ordered:" prefix means order confirmation even though the email body
    # contains a progress bar with "Ordered  Shipped  Out for delivery  Delivered".
    subject = 'Ordered: "Some Great Book" and 1 more item'
    body = (
        "Order placed!\n"
        "Ordered  Shipped  Out for delivery  Delivered\n"
        "Your order 112-1234567-8901234 is being prepared."
    )
    result = engine.extract("x", body, subject=subject)
    assert result.status is not None
    assert result.status.value == "order_confirmed"


def test_amazon_shipped_subject_not_forced_order_confirmed() -> None:
    # "Shipped:" subject must NOT trigger the ORDER_CONFIRMED override.
    subject = 'Shipped: "Some Great Book"'
    body = (
        "Your order has shipped!\n"
        "Ordered  Shipped  Out for delivery  Delivered\n"
        "It is on its way to you."
    )
    result = engine.extract("x", body, subject=subject)
    assert result.status is not None
    # Should be a shipping-progress status (shipped, in_transit, or out_for_delivery),
    # never order_confirmed.
    assert result.status.value != "order_confirmed"


# ── New Order subject prefix ──────────────────────────────────────────────────


def test_caretobeauty_new_order_subject_is_order_confirmed() -> None:
    # "New Order #..." in subject means ORDER_CONFIRMED even when the body contains
    # shipping-adjacent text that would otherwise match the SHIPPED rule.
    subject = "New Order #4500043904"
    body = "Thank you for your order. Your items will be shipped soon."
    result = engine.extract("x", body, subject=subject)
    assert result.status is not None
    assert result.status.value == "order_confirmed"
    order_values = [o.value for o in result.order_candidates]
    assert "4500043904" in order_values
    tracking_values = [t.value for t in result.tracking_candidates]
    assert "4500043904" not in tracking_values
