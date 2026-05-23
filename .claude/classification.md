# Classification — How It Works

This document covers the model-assisted classification stage: everything that
happens after `RuleExtractionResult` is produced and before `FinalClassificationResult`
is persisted. The rule engine runs first; the model is only invoked when the rules
need assistance or validation.

---

## Overview

```
RuleExtractionResult  +  CleanedEmail
        │
        ▼
ModelClassifier.select_mode(rules, cleaned, sender_trust_level)
        │
        ├── SKIP_MODEL   → no model call
        ├── MODEL_AUDIT  → lightweight agreement prompt (audit_max_chars)
        └── MODEL_REQUIRED → full extraction prompt (required_max_chars)
        │
        ▼
ModelClassifier.classify(cleaned, mode, rules)
        │  → (ModelClassificationResult | None, ModelCallObservability)
        │
        ▼
ClassificationReconciler.reconcile(rules, model, obs, cleaned, ...)
        │  → FinalClassificationResult
        │
        ▼
ExtractionOrchestrator._persist(cleaned, final, version)
        │  → processed_emails + email_extractions rows
```

---

## 1. EmailType — `domain/email_types.py`

`EmailType` is the coarse category of an email, separate from `ShipmentStatus`
(which describes the physical state of the parcel).

| Value | Meaning |
|---|---|
| `order_confirmation` | Order placed, not yet shipped |
| `shipping_update` | Carrier has parcel, in transit, customs, out for delivery |
| `pickup_ready` | Parcel waiting at branch/locker for collection (includes HFD alerts) |
| `delivered` | Parcel confirmed delivered or collected |
| `payment_problem` | Customs duty or payment required to release parcel |
| `billing_only` | Invoice, receipt, account statement — no physical shipment |
| `non_shipping` | Unrelated email |
| `digital_product` | SaaS, ebook, software licence, download — not a physical parcel |

`email_type_from_status(status, is_invoice) → EmailType` derives the coarse
category from rule-engine outputs. Billing takes priority over status mapping;
`UNKNOWN` status → `NON_SHIPPING`.

Status → EmailType mapping:

| Status | EmailType |
|---|---|
| `order_confirmed` | `order_confirmation` |
| `shipped`, `received_by_carrier`, `in_transit`, `arrived_in_destination_country`, `customs_pending`, `customs_released`, `handed_to_local_carrier`, `out_for_delivery`, `delayed_or_problem` | `shipping_update` |
| `ready_for_pickup`, `action_required` | `pickup_ready` |
| `delivered` | `delivered` |
| `payment_required` | `payment_problem` |
| `unknown` | `non_shipping` |

---

## 2. ModelClassifier — `processing/model_classifier.py`

### Mode selection (`select_mode`)

```python
ModelClassifier.select_mode(rules, cleaned, sender_trust_level) → ModelExecutionMode
```

| Condition | Mode |
|---|---|
| `model_client is None` | `SKIP_MODEL` |
| `sender_trust_level == "blocked"` | `SKIP_MODEL` |
| `rules.is_invoice and not cleaned.is_shipping_shaped` | `SKIP_MODEL` |
| `rules.is_shipping_email and rules.status_confidence >= 0.80` | `MODEL_AUDIT` |
| everything else | `MODEL_REQUIRED` |

### `MODEL_REQUIRED` — full extraction

- Prompt: `format_required_prompt(subject, sender_domain, email_text)`
- Text size: up to `ModelConfig.required_max_chars` (default 4000)
- Response model: `ModelClassificationResult`

The required prompt asks the model to classify the email from scratch and extract
all identifiers. Schema includes: `email_type`, `status`, `status_confidence`,
`status_evidence`, `merchant`, `carrier`, `tracking_numbers`, `order_numbers`,
`pickup_code`, `amount`, `currency`, `reasoning`.

### `MODEL_AUDIT` — lightweight agreement

- Prompt: `format_audit_prompt(subject, sender_domain, preview, rule_email_type, rule_status, ...)`
- Text size: up to `ModelConfig.audit_max_chars` (default 1500)
- Response model: `ModelAuditResult`

The audit prompt shows the model the rule classification and a short preview.
The model only needs to agree or disagree; it does not re-extract identifiers.
Schema: `agrees`, `email_type`, `status`, `status_confidence`, `reason`.

When the model agrees (`agrees=True`), `_audit_to_classification()` reflects the
rule values back as a `ModelClassificationResult` so the reconciler can record
clean agreement. When it disagrees, the model's corrected values are used.

### `ModelCallObservability`

Every classify() call (including skipped ones) returns a `ModelCallObservability`:

```python
class ModelCallObservability(BaseModel):
    mode: ModelExecutionMode      # MODEL_REQUIRED | MODEL_AUDIT | SKIP_MODEL
    called: bool
    prompt_type: str | None       # "required" | "audit" | None
    latency_ms: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
```

On model error, `called=True` but the result is `None` — the reconciler
degrades gracefully to rules-only.

---

## 3. Prompts — `model/prompts.py`

### Required prompt (`_REQUIRED_SYSTEM` + `_REQUIRED_EMAIL_BLOCK`)

System prompt instructs the model to return only valid JSON. Key rules in the
system prompt:

- `"תודה שאספת את המשלוח"` (Israel Post pickup complete) → `email_type: delivered`
- HFD "collect before" / "last day to collect" → `email_type: pickup_ready`
- Invoices, receipts → `email_type: billing_only`
- SaaS / downloadable products → `email_type: digital_product`
- If status is unknown, `status_confidence` must be 0.0
- Never guess tracking numbers — only extract explicitly labelled IDs

Email block format:
```
Subject: {subject}
Sender: {sender_domain}

{email_text}
```

### Audit prompt (`_AUDIT_SYSTEM` + `_AUDIT_RULE_BLOCK`)

Rule context block format:
```
Rules classified this email as:
  email_type:  {rule_email_type}
  status:      {rule_status}
  confidence:  {rule_confidence:.2f}
  evidence:    "{rule_evidence}"
  tracking:    {tracking}
  orders:      {orders}

Email context:
  Subject:  {subject}
  Sender:   {sender_domain}
  Preview:  {preview}
```

---

## 4. Model result types — `model/base.py`

```python
class ModelClassificationResult(BaseModel):
    email_type: EmailType = EmailType.NON_SHIPPING
    status: ShipmentStatus = ShipmentStatus.UNKNOWN
    status_confidence: float = 0.0
    status_evidence: str = ""
    merchant: str | None = None
    carrier: str | None = None
    tracking_numbers: list[str] = []
    order_numbers: list[str] = []
    pickup_code: str | None = None
    amount: float | None = None
    currency: str | None = None
    reasoning: str | None = None

class ModelAuditResult(BaseModel):
    agrees: bool
    email_type: EmailType = EmailType.NON_SHIPPING
    status: ShipmentStatus = ShipmentStatus.UNKNOWN
    status_confidence: float = 0.0
    reason: str | None = None
```

`ModelExtractionResult = ModelClassificationResult` is kept as a backward-compat alias.

---

## 5. ClassificationReconciler — `processing/reconciler.py`

`ClassificationReconciler.reconcile(rules, model, obs, cleaned, email_id, processing_version, model_provider, model_name, privacy)` → `FinalClassificationResult`

Rules are always the starting point. Model outputs override only when justified
by the reconciliation logic below.

### DecisionSource enum

| Value | When set |
|---|---|
| `rule` | No model call was made |
| `rule_model_agree` | Both sources agree on type and status |
| `rule_override` | Rule wins: `DELIVERED` is terminal, or rule conf ≥ 0.9 and model conf < 0.7 |
| `model_override` | Model wins: non-physical email type (`digital_product`/`billing_only`), or rule saw nothing (`NON_SHIPPING`) and model is very confident (≥ 0.9) |
| `semantic_guard` | Rule wins: model tried to upgrade `order_confirmation` → `shipping_update` without physical shipping evidence |
| `review_needed` | Both sources too uncertain (conf < 0.5) |
| `model_fallback` | Genuine conflict, model used as tiebreaker, `needs_review=True` |

### Reconciliation flow (simplified)

```
1. Derive rule_email_type from rules.status + rules.is_invoice
2. If model is None → decision_source = RULE, done

3. Check agreement: types_agree AND statuses_agree?
   → RULE_MODEL_AGREE: use higher-confidence source for status

4. DELIVERED is terminal → RULE_OVERRIDE

5. Model says non-physical (digital_product / billing_only)?
   → MODEL_OVERRIDE (overrides rule output)

6. _reconcile_email_type() five-case logic:
   a. Types agree → RULE_MODEL_AGREE
   b. rule_conf ≥ 0.9 and model_conf < 0.7 → RULE_OVERRIDE ("low_model_confidence")
   c. Rule=order_confirmation, model=shipping_update, no shipping evidence → SEMANTIC_GUARD
   d. Rule=non_shipping, model_conf ≥ 0.9 → MODEL_OVERRIDE ("rules_missed_semantic_email_type")
   e. Both conf < 0.5 → REVIEW_NEEDED (lower-confidence source wins, needs_review=True)
   f. Otherwise → MODEL_FALLBACK (model wins, needs_review=True)

7. Status follows email_type winner
   (MODEL_OVERRIDE/MODEL_FALLBACK → model status if higher conf; RULE_OVERRIDE → rule status)

8. Relevance: is_relevant = (shipping email or model says shipping) and not invoice
   and final_status != UNKNOWN
   Digital-product and billing_only are never relevant.

9. Identifier merge: rules first, then model (deduped by uppercase value, confidence 0.7)

10. Clip evidence to privacy.evidence_max_chars (default 240)
```

### `_has_shipping_evidence` guard

Used in step 6c. Returns `True` if any of:
- `rules.tracking_candidates` is non-empty
- `rules.status` is in `{SHIPPED, RECEIVED_BY_CARRIER, IN_TRANSIT, OUT_FOR_DELIVERY}`
- `model.tracking_numbers` is non-empty
- `model.carrier` is set

---

## 6. FinalClassificationResult — `processing/reconciler.py`

```python
class FinalClassificationResult(BaseModel):
    # Identity
    email_id: str
    processing_version: str

    # Email type
    email_type: EmailType          # final reconciled
    rule_email_type: EmailType     # rule-engine coarse category
    model_email_type: EmailType | None

    # Shipment status
    status: ShipmentStatus         # final reconciled
    rule_status: ShipmentStatus | None
    model_status: ShipmentStatus | None
    status_confidence: float
    status_evidence: str

    # Per-source confidence
    rule_confidence: float
    model_confidence: float | None

    # Identifiers (merged, deduped)
    selected_tracking_number: str | None   # first candidate
    tracking_candidates: list[TrackingIdentifier]
    selected_order_number: str | None      # first candidate
    order_candidates: list[OrderIdentifier]

    # Extracted fields
    merchant: str | None       # rule merchant or model merchant
    carrier: str | None        # model only
    pickup_code: str | None
    amount: float | None
    currency: str | None

    # Relevance
    is_relevant: bool
    ignore_reason: str | None  # "invoice" | "not_shipping_shaped" | "non_shipping" | "no_status_matched" | EmailType.value
    is_invoice: bool

    # Decision metadata
    decision_source: DecisionSource
    conflict_reason: str | None
    needs_review: bool

    # Observability
    model_called: bool
    model_mode: str                   # ModelExecutionMode.value
    model_latency_ms: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    rule_model_agreed: bool | None
    confidence_delta: float | None    # |model_conf - rule_conf|

    # Provenance
    model_provider: str | None
    model_name: str | None
    classification_method: str        # "rules_only" | "model_only" | "rules+model"
```

`FinalExtraction = FinalClassificationResult` is the backward-compat alias used
by `extraction_orchestrator.py`.

---

## 7. Persistence — `extraction_orchestrator.py`

`ExtractionOrchestrator._persist(cleaned, final, version)` writes two rows:

**`processed_emails`**

| Column | Source |
|---|---|
| `email_id` | `cleaned.email_id` |
| `processing_version` | version string |
| `cleaned_text_hash` | `cleaned.cleaned_text_hash` |
| `model_input_len` | `min(len(cleaned.cleaned_text), 1500)` |
| `cleaned_full_len` | `cleaned.cleaned_full_len` |
| `classification_method` | `final.classification_method` |
| `is_shipping_shaped` | `cleaned.is_shipping_shaped` |
| `is_relevant` | `final.is_relevant` |
| `ignore_reason` | `final.ignore_reason` |
| `model_mode` | `final.model_mode` |

**`email_extractions`**

| Column | Source |
|---|---|
| `email_type` | `final.email_type.value` |
| `status` | `final.status.value` |
| `rule_status` | `final.rule_status.value` or None |
| `model_status` | `final.model_status.value` or None |
| `status_confidence` | `final.status_confidence` |
| `status_evidence` | `final.status_evidence` (clipped to `evidence_max_chars`) |
| `merchant` | `final.merchant` |
| `carrier` | `final.carrier` |
| `selected_tracking_number` | first tracking candidate |
| `tracking_candidates_json` | JSON array of `TrackingIdentifier.model_dump()` |
| `selected_order_number` | first order candidate |
| `order_candidates_json` | JSON array of `OrderIdentifier.model_dump()` |
| `pickup_code` | `final.pickup_code` |
| `amount` | `final.amount` |
| `currency` | `final.currency` |
| `decision_source` | `final.decision_source.value` |
| `conflict_reason` | `final.conflict_reason` |
| `model_provider` | `final.model_provider` |
| `model_name` | `final.model_name` |
| `model_mode` | `final.model_mode` |
| `model_latency_ms` | `final.model_latency_ms` |
| `prompt_tokens` | `final.prompt_tokens` |
| `completion_tokens` | `final.completion_tokens` |
| `rule_model_agreed` | `final.rule_model_agreed` |
| `confidence_delta` | `final.confidence_delta` |
| `needs_review` | `final.needs_review` |
| `prompt_version` | `ProcessingConfig.prompt_version` (default `"v2"`) |
| `rules_version` | `ProcessingConfig.rules_version` (default `"v1"`) |
| `extraction_error` | `None` (errors result in the row not being written) |

---

## 8. ModelConfig — `config.py`

```python
class ModelConfig(BaseModel):
    provider: Literal["lmstudio", "llamacpp"] = "lmstudio"
    endpoint_url: str | None = None
    model_name: str = "gemma-3-4b"
    timeout_seconds: int = 120
    required_max_chars: int = 4000   # text size for MODEL_REQUIRED
    audit_max_chars: int = 1500      # text size for MODEL_AUDIT
```

`required_max_chars` is the larger budget — the model needs the full body to
extract identifiers and classify from scratch. `audit_max_chars` is the shorter
budget — the model only needs a preview because the rule context block already
carries the key facts.
