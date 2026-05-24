# Resolution — How It Works

This document covers Part 4 of the pipeline: everything that happens after
`FinalClassificationResult` is produced and persisted by the extraction
orchestrator, up to the final `ShipmentDTO` rows the dashboard reads.

---

## Overview

```
FinalClassificationResult (from ExtractionOrchestrator)
        │
        ▼
ShipmentResolutionService.resolve_and_insert(extraction, received_at)
        │
        ├── email_type == order_confirmation
        │       ↓
        │   _process_order_confirmation
        │       • derive/look up canonical from order alias
        │       • upsert order alias
        │       • insert order_confirmed event
        │       • _rebuild_shipment
        │
        └── shipping_update / pickup_ready / delivered / payment_problem
                ↓
            _process_shipping_event
                • _resolve_canonical_for_shipping (4-step look-up)
                • _register_tracking_alias (merge safety check)
                • upsert order alias (if order number present)
                • insert shipment event
                • _rebuild_shipment

_rebuild_shipment(canonical)
        • list all events for canonical
        • check_chronology(events)   → ChronologyResult
        • select_current_status(events) → ShipmentEventDTO
        • sort tracking numbers (structured first)
        • ShipmentRepository.upsert(ShipmentDTO)
```

Non-physical email types (`non_shipping`, `billing_only`, `digital_product`)
and irrelevant extractions (`is_relevant=False`) are skipped entirely — no
aliases, events, or timeline rows are written.

---

## 1. Canonical Shipment ID — `domain/merge.py`

Every shipment has a single stable `canonical_shipment_id` (16-char hex).

```python
def canonical_shipment_id(alias_type: str, alias_value: str) -> str:
    key = f"{alias_type}:{alias_value.upper().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

The function is deterministic: the same `(alias_type, alias_value)` always
produces the same ID. Alias values are normalised to UPPERCASE before hashing
so casing differences in raw email text never create duplicate shipments.

**Two alias types:**

| `alias_type` | `alias_value` | Example |
|---|---|---|
| `"tracking"` | tracking number as extracted | `"ECSA0041206"` |
| `"order"` | `"{ORDER}|{MERCHANT}"` or just `"{ORDER}"` | `"206-3447859-4940302"` or `"4500043904|AMAZON"` |

The merchant qualifier in the order alias prevents two different merchants'
coincidentally identical order numbers from being merged into one shipment.

---

## 2. Alias Management — `db/repositories.py` `ShipmentAliasRepository`

`ShipmentAlias` rows link every known identifier to its canonical.

```
shipment_aliases
  alias_type           "tracking" | "order"
  alias_value          normalised identifier
  canonical_shipment_id  FK → shipments
  confidence           float — from the extraction that created this alias
  evidence_email_id    which email first established this link
```

Key methods:

| Method | What it does |
|---|---|
| `find_canonical(type, value)` | Exact look-up; returns `canonical_shipment_id` or `None` |
| `upsert(alias)` | Insert or update on `(alias_type, alias_value)` conflict |
| `list_for_shipment(canonical)` | All aliases for one shipment |

---

## 3. Canonical Resolution — 4-Step Look-Up

`_resolve_canonical_for_shipping(tracking, order, merchant)` applies this
priority, stopping at the first hit:

```
1. tracking alias (find_canonical("tracking", tracking))
      → carrier IDs are globally unique; this is the strongest signal.

2. order+merchant alias (find_canonical("order", order|merchant))
      → attaches a new carrier update to an existing order-confirmation timeline.

3. derive new canonical from tracking
      → canonical_shipment_id("tracking", tracking)

4. derive new canonical from order+merchant
      → canonical_shipment_id("order", order|merchant)

Returns None if neither tracking nor order is present — event is skipped.
```

---

## 4. Merge Safety — `domain/merge.py`

Before registering a new tracking alias, `_register_tracking_alias` checks
whether the new number is safe to attach to the existing canonical.

```python
def can_merge_tracking_numbers(a: str, b: str) -> MergeDecision:
```

| Condition | Decision |
|---|---|
| `a == b` (normalised) | MERGE — identical, no ambiguity |
| Same carrier family, different values | DENY — two distinct carrier IDs for same carrier |
| Different carrier families | DENY — no alias evidence to justify cross-carrier merge |

No LLM calls. No merchant-specific rules. If merge is denied, a warning is
logged and the alias is silently skipped — the event is still inserted under
whatever canonical was already resolved.

`CarrierFamily` is detected by `carrier_family_from_tracking(value)` in
`domain/carriers.py` using format patterns identical to those in
`domain/identifiers.py`.

---

## 5. Shipment Events — `db/repositories.py` `ShipmentEventRepository`

```
shipment_events
  canonical_shipment_id  FK → shipments
  email_id               which email produced this event
  event_date             received_at of the email (UTC)
  status                 ShipmentStatus enum value
  status_confidence      float
  status_evidence        short snippet (≤ evidence_max_chars)
  sender_domain          extracted from From header (e.g. "caretobeauty.com")
  sender_display_name    display name from From header (e.g. "Care to Beauty")
  tracking_number        may be null (order-only events)
  order_number           may be null (tracking-only events)
  merchant               may be null
  processing_version     version stamp from ProcessingConfig
```

**`insert_if_new`** — explicit SELECT before INSERT because SQLite treats
`NULL ≠ NULL` in unique constraints. The unique check is on
`(email_id, event_date, status, tracking_number, order_number)`. Running
`resolve_and_insert` twice for the same email produces exactly one event row.

**Sender backfill** — when an event already exists with NULL `sender_display_name`
and the new call has sender info, `insert_if_new` updates those fields in place.
This handles the case where emails were processed before sender info was tracked.

---

## 6. Chronology — `domain/chronology.py`

`check_chronology(events)` analyses the event sequence for impossible
transitions.

### Status classification

| Category | Statuses | Behaviour |
|---|---|---|
| Main statuses | `order_confirmed` → … → `delivered` | Ordered linearly; regressions flagged |
| Terminal | `delivered` | Any subsequent main event → `conflict` severity |
| Side statuses | `action_required`, `payment_required`, `delayed_or_problem`, `unknown` | Never create conflicts; coexist alongside main progression |

### Conflict rules

- Events with side statuses are filtered out before sequence analysis.
- A rank drop of exactly 1 is allowed (carrier systems sometimes re-emit prior
  states after an update).
- A rank drop of 2 or more → `ChronologyResult(severity="warning", ...)`.
- Any main-status event after `delivered` → `severity="conflict"`.

`ChronologyResult` fields:

```python
class ChronologyResult(BaseModel):
    severity: str               # "ok" | "warning" | "conflict"
    notes: list[str]            # verbose prose descriptions
    reason_codes: list[str]     # structured machine-readable codes

    @property
    def ok(self) -> bool: ...
    @property
    def reason(self) -> str | None: ...      # notes[0]
    @property
    def reason_code(self) -> str | None: ... # reason_codes[0]
```

Structured reason codes:

| Code | Trigger |
|---|---|
| `"status_date_regression"` | rank drop ≥ 2 in main-status sequence |
| `"terminal_status_followed_by_non_terminal"` | non-terminal after delivered |
| `"duplicate_terminal_status"` | multiple delivered events |

Stored on `ShipmentDTO` / `shipments` table:
- `chronology_ok: bool`
- `chronology_severity: str`
- `chronology_notes: list[str]`
- `chronology_reason_code: str | None` — `reason_codes[0]`, surfaced in projections

---

## 7. Current Status Selection — `domain/chronology.py`

`select_current_status(events)` picks the single most authoritative event to
display as the shipment's current state.

```
Priority rules (applied in order):

1. DELIVERED (terminal) — always wins if present.

2. ACTION_REQUIRED or PAYMENT_REQUIRED — wins over the best main-status event
   only if it is more recent. (An HFD "collect before return" alert that
   arrives after an "in transit" update is more urgent than the last transit
   state.)

3. Best main-status event (most recent, not UNKNOWN).

4. Fallback: most recent event of any kind (all events are UNKNOWN).
```

`UNKNOWN` never overrides a known status.

---

## 8. Timeline Rebuild — `_rebuild_shipment`

Called after every `insert_if_new`. Recomputes the full `ShipmentDTO` from scratch:

```python
events = self._event_repo.list_for_shipment(canonical)
chrono = check_chronology(events)
current_event = select_current_status(events)

tracking_numbers = sorted(
    (e.tracking_number for e in events if e.tracking_number),
    key=_tracking_sort_key,   # structured carriers first; no carrier-brand ranking
)
```

**`primary_tracking_number`** — first in the sorted list. Sort key:
structured carriers (non-numeric prefix: UPS, Israel Post, HFD, ASOS) → 0;
generic numeric (FedEx, DHL, UNKNOWN) → 1. No carrier-brand ranking within
either tier.

`ShipmentDTO` fields written:

| Field | Source |
|---|---|
| `canonical_shipment_id` | fixed |
| `merchant` | first merchant across all events |
| `primary_tracking_number` | sorted tracking list[0] |
| `primary_order_number` | first order across all events |
| `current_status` | `select_current_status` |
| `current_status_label` | `STATUS_LABELS[status]` (human-readable string) |
| `current_status_date` | event date of current event |
| `current_status_evidence` | evidence snippet from current event |
| `merge_confidence` | min confidence across all aliases |
| `chronology_ok` / `chronology_severity` / `chronology_notes` | from `check_chronology` |
| `event_count` | total events |
| `first_seen_at` / `last_seen_at` | min/max event dates |
| `updated_at` | `datetime.now(UTC)` |

---

## 9. DashboardService — `services/dashboard_service.py`

`DashboardService.get_dashboard()` is a read-only materialisation of all
`ShipmentDTO` rows.

```python
class DashboardDTO(BaseModel):
    shipments: list[ShipmentDTO]
    generated_at: datetime
    total_count: int
    active_count: int     # not yet delivered
    delivered_count: int  # status in TERMINAL_STATUSES
```

No business logic — counting and grouping only. All shipment data comes from
the pre-computed `shipments` table; no joins or event re-analysis at read time.

---

## 10. DB Tables

```
shipment_aliases
  alias_type | alias_value | canonical_shipment_id | confidence | evidence_email_id

shipment_events
  id | canonical_shipment_id | email_id | event_date | status | status_confidence
     | status_evidence | sender_domain | sender_display_name
     | tracking_number | order_number | merchant | processing_version

shipments
  canonical_shipment_id (PK) | merchant | primary_tracking_number | primary_order_number
  | current_status | current_status_label | current_status_date | current_status_evidence
  | merge_confidence | chronology_ok | chronology_severity | chronology_notes
  | chronology_reason_code | event_count | first_seen_at | last_seen_at | updated_at
```

New columns added via `ensure_schema()` in `db/session.py`:
- `shipment_events.sender_display_name VARCHAR(255)`
- `shipments.chronology_reason_code VARCHAR(64)`
- `email_messages.sender_display_name VARCHAR(255)` — populated by `GmailIngestor` from `From` header; used by `sync_service` to pass to `resolve_and_insert`

---

## 11. Service Entry Points

### `resolve_and_insert(extraction, received_at, *, sender_display_name=None, sender_domain=None)`

Called after extraction for every email that passes the `is_relevant` gate.
Idempotent: running twice for the same email produces no duplicate rows
(aliases upserted, events existence-checked).

`sender_display_name` and `sender_domain` are keyword-only and come from the
email `From` header. They are stored in `shipment_events` for use by the
projection layer's `display_merchant` fallback chain.

**Callers must pass these**:
- `sync_service.py` — reads from `email_messages.sender_display_name` / `.sender_domain`
- Notebook Part 4 — extracts from `emails[*]['sender']` using `extract_sender_display_name` / `extract_sender_domain`

### `rebuild_all()`

Recomputes every `ShipmentDTO` row from its events. Used by `parsli rebuild`
CLI and by tests after bulk re-processing.

### `rebuild_affected(email_ids)`

Targeted rebuild for only the canonical IDs touched by the given emails.
Used by `reprocess_email()` in `EmailProcessingService` to avoid a full
table scan.

---

## 12. Key Invariants

- **No LLM in resolution** — all decisions are pure Python.
- **No merchant-specific merge rules** — `can_merge_tracking_numbers` is format-only.
- **Idempotent** — `resolve_and_insert` is safe to call multiple times for the
  same email. Sender info is backfilled on existing rows with NULL values.
- **`DELIVERED` is final** — `select_current_status` always returns the
  `delivered` event if one exists; no later event can override it.
- **Side statuses are parallel** — `action_required`/`payment_required`/
  `delayed_or_problem`/`unknown` never trigger chronology conflicts.
- **Canonical IDs are stable** — same `(alias_type, alias_value)` always
  hashes to the same 16-char hex.
- **Sender info is display-only** — `sender_display_name`/`sender_domain` are
  never used in canonical resolution or merge decisions; only the projection
  layer reads them for `display_merchant`.
