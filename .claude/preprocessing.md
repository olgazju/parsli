# Preprocessing — How It Works

This document covers the deterministic preprocessing stage: everything that
happens between a raw email body and the `RuleExtractionResult` that feeds the
model or goes straight to persistence. No LLM is involved here.

---

## Overview

```
raw body (string)
        │
        ▼
EmailCleaner.clean(email_id, raw_body)
        │  ← language pack: footer_patterns, unsubscribe_patterns, shipping_signals
        │  strips boilerplate, URLs, tracking pixels
        ▼
CleanedEmail DTO
  cleaned_text          analysis-ready plain text (never stored)
  cleaned_text_hash     sha256[:32] (stored)
  cleaned_full_len      char count (stored)
  is_shipping_shaped    True if any shipping signal matches
  subject               email subject line (default ""; model-prompt context, never stored)
  sender_domain         e.g. "amazon.com" (default None; model-prompt context, never stored)

        │
        ▼
RuleEngine.extract(email_id, cleaned_text, sender_domain, subject)
        │  ← language pack: status_patterns, billing_exclusion_phrases,
        │                    shipping_override_phrases
        │  ← IdentifierExtractor: tracking_context_words, order_label_patterns
        ▼
RuleExtractionResult DTO
  is_shipping_email     True if (status or tracking) and not invoice
  is_invoice            True if billing signal and no shipping override
  status                ShipmentStatus enum or None
  status_confidence     float 0–1
  status_evidence       short snippet centred on the match
  tracking_candidates   list[TrackingIdentifier]
  order_candidates      list[OrderIdentifier]
  merchant, pickup_code, amount, currency
```

---

## 1. Language Packs

All locale-specific phrases are in YAML files, not in Python source.
Components are constructed with a `MergedLanguageConfig`:

```python
from parsli.languages import load_language_packs

lang = load_language_packs(["en", "he"])   # default
lang = load_language_packs(["en"])         # English-only: Hebrew rules invisible
```

`AppConfig.language.enabled` controls which packs are active in production.
In the notebook, `lang_config` is built once and passed to both `EmailCleaner`
and `RuleEngine` so they share identical patterns.

---

## 2. EmailCleaner — `processing/cleaner.py`

### What gets stripped (in order)

| Step | What | Source |
|---|---|---|
| Tracking pixels | `https://….(gif\|png\|jpg)?…` | hardcoded (not language-specific) |
| Footer boilerplate | e.g. `הודעה זו נשלחה ל-…`, `this email was sent…` | `footer_patterns` in language packs |
| Unsubscribe blocks | `unsubscribe…`, `הסר מרשימה…` | `unsubscribe_patterns` in language packs |
| Markdown link URLs | `(https://…)` — strips URL, keeps link text | hardcoded |
| Bare URLs | `https://…` | hardcoded |
| Repeated blank lines | collapses 3+ newlines → 2 | hardcoded |

URL stripping is critical for identifier correctness: phone numbers and token
IDs embedded in URL query params (e.g. `?phone=0545226889&token=1563…`) are
removed before any extraction runs.

### `is_shipping_shaped`

Built from `MergedLanguageConfig.shipping_signals`. A regex alternation of all
signals from active packs is searched case-insensitively. Returns `True` if any
match. This is a heuristic gate — downstream components do not rely on it for
correctness, only for observability and model-call filtering.

---

## 3. RuleEngine — `processing/rule_engine.py`

### Early exits

**Payment processor domains** — checked before any text analysis. If
`sender_domain` matches `_PAYMENT_PROCESSOR_DOMAINS` (paypal.com, stripe.com,
payplus.co.il, cardcom.co.il, tranzila.com, isracard.co.il), returns a fixed
`is_invoice=True` result immediately. This list is a Python constant, not in
language packs — payment processors are domain-level, not language-level.

### Invoice detection

Two compiled patterns built from the merged language config:

**`_INVOICE_RE`** — matches billing-dominant phrases. Active phrases per pack:

| Pack | Phrases |
|---|---|
| `en` | `\binvoice\b`, `tax invoice`, `billing statement`, `account statement` |
| `he` | `חשבונית\s+מס`, `פירוט חיובים`, `חיובים תקופתיים` |

**`_INVOICE_NEGATIVE_RE`** — shipping signals that override the invoice flag.
An email that mentions "invoice" only as a download link is not a billing email.

| Pack | Phrases |
|---|---|
| `en` | `tracking\s+(number\|code)`, `shipment`, `has\s+(shipped\|been\s+shipped)`, etc. |
| `he` | `מספר\s+מעקב`, `נשלח`, `משלוח`, `חבילה`, `יצא\s+לדרך` |

`is_invoice = _INVOICE_RE.search(text) and not _INVOICE_NEGATIVE_RE.search(text)`

### Status detection

`_detect_status(subject, id_text)` — subject-prefix overrides run before the
main pattern table:

| Subject prefix | Forced status | Reason |
|---|---|---|
| `Ordered:` | `order_confirmed` (0.85) | Amazon progress-bar boilerplate in every email body would otherwise match `out_for_delivery` |
| `New Order #…` | `order_confirmed` (0.85) | Order-creation subject; body may contain "will be shipped soon" |

After overrides, `_match_status(id_text)` scans the combined `subject\nbody`
text against `_status_rules` — a list of `(ShipmentStatus, confidence, compiled_pattern)`
built from `MergedLanguageConfig.status_patterns`.

**Status rule ordering** (first match wins):

| Status | Confidence | Notes |
|---|---|---|
| `delivered` | 0.95 | |
| `action_required` | 0.90 | Fires **before** `ready_for_pickup` — "collect before … will be returned" is more urgent |
| `ready_for_pickup` | 0.93 | |
| `payment_required` | 0.92 | Customs duty / import duty |
| `out_for_delivery` | 0.92 | |
| `customs_released` | 0.88 | |
| `customs_pending` | 0.85 | |
| `handed_to_local_carrier` | 0.82 | |
| `arrived_in_destination_country` | 0.82 | |
| `delayed_or_problem` | 0.80 | Requires delivery context — bare `עיכוב`/`delay` does not fire |
| `in_transit` | 0.75 | |
| `received_by_carrier` | 0.75 | |
| `shipped` | 0.80 | |
| `order_confirmed` | 0.70 | Lowest priority — catches confirmations the overrides missed |

Status patterns per pack are raw regex strings, combined into one alternation
per status at `RuleEngine.__init__`. The `action_required` pattern is compiled
with `re.DOTALL` (for `collect.*?before.*?return` spanning lines); all others
use `re.IGNORECASE` only.

### Identifier extraction

`RuleEngine` holds an `IdentifierExtractor` built from the same `lang_config`.
After extracting both tracking and order candidates, it runs a dedup pass:

```python
_order_values = {o.value for o in orders}
tracking = [t for t in tracking if t.value not in _order_values]
```

This prevents a number like `4500043904` from appearing in both
`order_candidates` (correctly labeled `Order #4500043904`) and
`tracking_candidates` (DHL digit match).

### `is_shipping_email` flag

```python
is_shipping = (bool(status) or bool(tracking)) and not is_invoice
```

An email with valid tracking but no classified status is still a shipping email.

---

## 4. IdentifierExtractor — `domain/identifiers.py`

### Tracking number patterns

Carrier format patterns are **language-agnostic** — same in all packs:

| Carrier | Pattern | Context required? |
|---|---|---|
| `ups` | `\b1Z[A-Z0-9]{16}\b` | No |
| `israel_post` | `\b[A-Z]{2}\d{8,10}[A-Z]{1,2}\b` | No |
| `hfd` | `\bECSA\d{7,12}\b` | No |
| `asos` | `\bASO\d[A-Z0-9]{10,18}\b` | Yes — must start with digit to exclude `asossansdisplay` CSS font name |
| `fedex` | `\b\d{15}\b` | Yes |
| `dhl` | `\b\d{10,11}\b` | Yes |

**Context guard** — carriers in `_CONTEXT_REQUIRED` (`fedex`, `dhl`, `asos`)
require a shipping keyword within 150 chars on either side. The keyword regex is
built from `MergedLanguageConfig.tracking_context_words`:

| Pack | Context words |
|---|---|
| `en` | `tracking`, `tracking\s+number`, `shipment`, `parcel`, `delivery` |
| `he` | `מספר\s+מעקב`, `משלוח`, `חבילה` |

**Israeli mobile exclusion** — `^05\d{8}$` is always excluded regardless of
context (10-digit Israeli mobile numbers are indistinguishable from DHL IDs by
format alone).

`TrackingIdentifier.source` is `"body"` for format-specific carriers and
`"body_near_keyword"` for context-guarded ones.

### Order number patterns

Order patterns come entirely from language packs — the only format-specific
constant is the Amazon number format which is carrier-level, not linguistic:

| Name | Source | Pattern |
|---|---|---|
| `amazon` | hardcoded | `\b\d{3}-\d{7}-\d{7}\b` |
| `generic` | `en.yaml` | `\border\s*(?:#\|no\.?\b\|number\b\|num\b\|:)\s*…` |
| `hebrew` | `he.yaml` | `(?:מספר\s*הזמנה\|מס[׳']\s*הזמנה)[^#\d]{0,20}#?(\d{4,30})\b` |

Words in `_ORDER_JUNK` (CONTAINS, SUMMARY, DETAILS, REFERENCE, etc.) are
silently dropped even when matched.

---

## 5. Pipeline wiring — `processing/pipeline.py`

`EmailProcessingPipeline` is constructed by `EmailProcessingService` with a
shared `lang_config`:

```python
lang_config = load_language_packs(config.language.enabled)
pipeline = EmailProcessingPipeline(
    cleaner=EmailCleaner(lang_config),
    rule_engine=RuleEngine(lang_config),
    orchestrator=...,
    debug_store=...,
)
```

`pipeline.process(email_id, raw_body, sender_domain, subject)` runs:
1. `cleaner.clean(email_id, raw_body)` → `CleanedEmail`
2. Optionally stores cleaned text via `DebugStore` (no-op unless debug mode on)
3. `rule_engine.extract(email_id, cleaned_text, sender_domain, subject)` → `RuleExtractionResult`
4. `orchestrator.orchestrate(cleaned, rules)` → `FinalExtraction`

---

## 6. Known regression guards (`tests/test_extraction_guards.py`)

Key cases protected by regression tests:

| Case | Guard |
|---|---|
| Hebrew mailing-system footer stripped | `test_hebrew_footer_stripped_before_classification` |
| Pango/Moovit periodic billing → `is_invoice=True` | `test_pango_billing_is_invoice` |
| HOODIES/All4Pet order confirmation → NOT invoice | `test_hoodies_order_confirmation_not_invoice` |
| CareToBeauty `חשבונית` mention → NOT invoice | `test_all4pet_order_confirmation_not_invoice` |
| DHL 10-digit without context → not extracted | `test_dhl_without_context_not_extracted` |
| Phone `0545226889` in body → not extracted | (covered by Israeli mobile exclusion) |
| Phone in URL → stripped before extraction | `test_phone_number_in_url_not_extracted_as_tracking` |
| URL token `15632131559` → not extracted | `test_url_token_not_extracted_as_tracking` |
| `ASOSSANSDISPLAY` CSS font → not extracted | `test_asos_css_font_name_not_extracted` |
| Cancellation-policy `עיכוב` → not `delayed_or_problem` | `test_cancellation_policy_delay_not_shipping_delay` |
| Generic apology `delay` → not `delayed_or_problem` | `test_generic_apology_delay_not_shipping_delay` |
| `Order #4500043904` → in orders, not tracking | `test_order_labeled_number_not_in_tracking` |
| Amazon `Ordered:` subject → `order_confirmed` | `test_amazon_ordered_subject_is_order_confirmed` |
| Amazon `Shipped:` subject → NOT `order_confirmed` | `test_amazon_shipped_subject_not_forced_order_confirmed` |
| CareToBeauty `New Order #…` subject → `order_confirmed` | `test_caretobeauty_new_order_subject_is_order_confirmed` |
| Israel Post 9-digit `LS233312341CH` → extracted | `test_israel_post_9digit_extracted_from_subject` |
| Israel Post 10-digit `RU0136772947Z` → extracted | `test_israel_post_10digit_with_single_check_extracted` |
