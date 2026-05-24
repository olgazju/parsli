"""Tests for the language-pack architecture.

Covers: loading packs, merging, query generation, footer cleaning,
Hebrew+English shipping detection, and disabling Hebrew removes its rules.
"""

import pytest

from parsli.config import GmailConfig
from parsli.domain.identifiers import IdentifierExtractor
from parsli.gmail.models import DomainPreferences
from parsli.gmail.query_builder import GmailQueryBuilder
from parsli.languages import DEFAULT_LANGUAGES, load_language_packs
from parsli.processing.cleaner import EmailCleaner
from parsli.processing.rule_engine import RuleEngine


# ── Loading ───────────────────────────────────────────────────────────────────


def test_load_en_pack():
    cfg = load_language_packs(["en"])
    assert "en" in cfg.active_codes
    assert any("tracking" in s for s in cfg.shipping_signals)


def test_load_he_pack():
    cfg = load_language_packs(["he"])
    assert "he" in cfg.active_codes
    assert "משלוח" in cfg.shipping_signals


def test_load_missing_pack_raises():
    with pytest.raises(FileNotFoundError):
        load_language_packs(["xx"])


def test_load_multiple_packs_combines_signals():
    cfg = load_language_packs(["en", "he"])
    signals = cfg.shipping_signals
    assert any("tracking" in s for s in signals)
    assert "משלוח" in signals


def test_merged_active_codes():
    cfg = load_language_packs(["en", "he"])
    assert cfg.active_codes == ["en", "he"]


def test_default_languages_constant_matches_he_plus_en():
    assert set(DEFAULT_LANGUAGES) == {"en", "he"}


# ── Query generation ──────────────────────────────────────────────────────────


def _builder(codes: list[str], prefs: DomainPreferences | None = None) -> GmailQueryBuilder:
    cfg = load_language_packs(codes)
    return GmailQueryBuilder(GmailConfig(lookback_days=30), prefs, lang_config=cfg)


def test_query_en_only_has_english_shipping_terms():
    queries = _builder(["en"]).build_queries()
    strong = next(q for q in queries if q.name == "strong_shipping")
    assert "shipped" in strong.query
    assert '"tracking number"' in strong.query


def test_query_he_only_has_hebrew_shipping_terms():
    queries = _builder(["he"]).build_queries()
    strong = next(q for q in queries if q.name == "strong_shipping")
    assert '"מספר מעקב"' in strong.query


def test_query_merged_en_he_has_both_language_terms():
    queries = _builder(["en", "he"]).build_queries()
    strong = next(q for q in queries if q.name == "strong_shipping")
    assert '"tracking number"' in strong.query
    assert '"מספר מעקב"' in strong.query


def test_query_en_only_excludes_do_not_contain_hebrew():
    queries = _builder(["en"]).build_queries()
    for q in queries:
        assert "פרסומת" not in q.query


def test_query_he_excludes_contain_hebrew_billing_terms():
    queries = _builder(["he"]).build_queries()
    combined = " ".join(q.query for q in queries)
    assert "פירוט חיובים" in combined or '"פירוט חיובים"' in combined


# ── Footer cleaning ───────────────────────────────────────────────────────────


def test_hebrew_footer_stripped_when_he_pack_active():
    cleaner = EmailCleaner(load_language_packs(["en", "he"]))
    body = (
        "Your package is on its way.\n"
        "הודעה זו נשלחה ל- user@example.com על ידי example.com\n"
        "נשלח באמצעות מסר עשר"
    )
    result = cleaner.clean("x", body)
    assert "הודעה זו נשלחה ל-" not in result.cleaned_text
    assert "נשלח באמצעות" not in result.cleaned_text


def test_hebrew_footer_not_stripped_when_en_only():
    cleaner = EmailCleaner(load_language_packs(["en"]))
    body = "הודעה זו נשלחה ל- user@example.com על ידי example.com"
    result = cleaner.clean("x", body)
    assert "הודעה זו נשלחה ל-" in result.cleaned_text


def test_english_unsubscribe_stripped_with_en_pack():
    cleaner = EmailCleaner(load_language_packs(["en"]))
    body = "Your order shipped. Unsubscribe from these emails here."
    result = cleaner.clean("x", body)
    assert "Unsubscribe" not in result.cleaned_text


# ── Shipping detection ────────────────────────────────────────────────────────


def test_english_shipping_shaped_with_en_pack():
    cleaner = EmailCleaner(load_language_packs(["en"]))
    assert cleaner.clean("x", "Your shipment is on its way.").is_shipping_shaped is True


def test_hebrew_shipping_shaped_with_he_pack():
    cleaner = EmailCleaner(load_language_packs(["he"]))
    assert cleaner.clean("x", "המשלוח שלך בדרך.").is_shipping_shaped is True


def test_hebrew_not_shipping_shaped_when_en_only():
    cleaner = EmailCleaner(load_language_packs(["en"]))
    assert cleaner.clean("x", "המשלוח שלך בדרך.").is_shipping_shaped is False


def test_both_languages_detected_with_merged_pack():
    cleaner = EmailCleaner(load_language_packs(["en", "he"]))
    assert cleaner.clean("x", "Your shipment is on its way.").is_shipping_shaped is True
    assert cleaner.clean("x", "המשלוח שלך בדרך.").is_shipping_shaped is True


# ── Status classification ─────────────────────────────────────────────────────


def test_english_delivered_status_with_en_pack():
    engine = RuleEngine(load_language_packs(["en"]))
    result = engine.extract("x", "Your order has been delivered.")
    assert result.status is not None
    assert result.status.value == "delivered"


def test_hebrew_delivered_status_with_he_pack():
    engine = RuleEngine(load_language_packs(["he"]))
    result = engine.extract("x", "המשלוח נמסר בשעה 18:00.")
    assert result.status is not None
    assert result.status.value == "delivered"


def test_hebrew_status_not_matched_when_en_only():
    engine = RuleEngine(load_language_packs(["en"]))
    # "נמסר" alone must not match when Hebrew pack is disabled.
    result = engine.extract("x", "נמסר")
    assert result.status is None or result.status.value != "delivered"


def test_both_languages_status_works_together():
    engine = RuleEngine(load_language_packs(["en", "he"]))
    en_result = engine.extract("x", "Your order has been delivered.")
    he_result = engine.extract("x", "המשלוח נמסר.")
    assert en_result.status is not None and en_result.status.value == "delivered"
    assert he_result.status is not None and he_result.status.value == "delivered"


# ── Invoice detection ─────────────────────────────────────────────────────────


def test_hebrew_billing_detected_with_he_pack():
    engine = RuleEngine(load_language_packs(["he"]))
    result = engine.extract("x", "פירוט חיובים תקופתי לחודש מאי")
    assert result.is_invoice is True


def test_hebrew_billing_not_detected_when_en_only():
    engine = RuleEngine(load_language_packs(["en"]))
    # Hebrew billing phrase must be invisible when he pack is disabled.
    result = engine.extract("x", "פירוט חיובים תקופתי לחודש מאי")
    assert result.is_invoice is False


# ── Order extraction ──────────────────────────────────────────────────────────


def test_hebrew_order_label_extracted_with_he_pack():
    extractor = IdentifierExtractor(load_language_packs(["he"]))
    orders = extractor.extract_order_candidates("מספר הזמנה: 450964")
    assert any(o.value == "450964" for o in orders)


def test_hebrew_order_label_not_extracted_when_en_only():
    extractor = IdentifierExtractor(load_language_packs(["en"]))
    orders = extractor.extract_order_candidates("מספר הזמנה: 450964")
    assert not any(o.value == "450964" for o in orders)


def test_english_order_label_extracted_with_en_pack():
    extractor = IdentifierExtractor(load_language_packs(["en"]))
    orders = extractor.extract_order_candidates("Order #112345 has shipped.")
    assert any(o.value == "112345" for o in orders)
