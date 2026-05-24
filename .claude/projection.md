# Part 5 — Dashboard Projection Layer

Read-only layer that converts pre-resolved shipment rows into UI-ready payloads.
Never re-runs business logic; never writes to the database.

---

## Data sources

| Table | What it provides |
|---|---|
| `shipments` | canonical ID, current status, chronology severity/notes/reason_code, merge confidence |
| `shipment_events` | per-email status events with timestamps, evidence, tracking/order numbers, sender info |
| `email_extractions` | decision_source, needs_review flag, model observability fields |

---

## Models (`domain/projections.py`)

### ShipmentSummaryRow
One row in the dashboard list view.

| Field | Notes |
|---|---|
| `shipment_id` | 16-char canonical ID |
| `display_title` | human-readable (see Display Title rules below) |
| `merchant` | raw resolved merchant — never mutated, for provenance |
| `display_merchant` | enriched: merchant → sender_display_name → sender_domain → "Unknown" |
| `tracking_number` | nullable — None for order-only shipments |
| `order_number` | nullable |
| `current_status` | `ShipmentStatus` enum |
| `current_status_label` | human-readable label from `STATUS_LABELS` |
| `last_status_date` | datetime of most recent event |
| `events_count` | total number of events for this shipment |
| `shipment_kind` | `"tracked"` or `"order_only"` |
| `chronology_status` | `"ok"` / `"warning"` / `"conflict"` — from `Shipment.chronology_severity` |
| `chronology_reason` | first structured reason code, or None (e.g. `"status_date_regression"`) |
| `needs_review` | True when chronology is not "ok" OR any linked extraction has `needs_review=True` |

### ShipmentDetailProjection
Full detail view for one shipment.

Same fields as ShipmentSummaryRow plus:
- `first_seen_at`: datetime the shipment was first created
- `chronology_notes`: full list of verbose prose notes (not just first)
- `merge_confidence`: float 0–1 from the Shipment row
- `events`: ordered list of `ShipmentEventProjection`

### ShipmentEventProjection
One timeline entry, enriched with extraction observability.

| Field | Source |
|---|---|
| `event_date` | `shipment_events.event_date` |
| `status` | `ShipmentStatus` enum |
| `status_label` | from `STATUS_LABELS` |
| `status_confidence` | float |
| `status_evidence` | clipped evidence string (never raw email text) |
| `tracking_number` | from the event row |
| `order_number` | from the event row |
| `email_id` | source email |
| `decision_source` | from `email_extractions` JOIN — None if extraction absent |
| `needs_review` | from `email_extractions` JOIN — False if extraction absent |
| `model_mode` | `"skip_model"` / `"model_only"` / `"hybrid"` etc. |
| `model_latency_ms` | nullable float |

### DashboardProjection
Top-level dashboard payload.

| Field | Notes |
|---|---|
| `shipments` | list of ShipmentSummaryRow |
| `total_count` | len(shipments) |
| `active_count` | total − delivered (TERMINAL_STATUSES) |
| `delivered_count` | shipments in TERMINAL_STATUSES |
| `order_only_count` | shipments with kind == "order_only" (no tracking number) |
| `needs_review_count` | shipments where needs_review == True |
| `generated_at` | UTC timestamp of projection build |

---

## Shipment kind

```
shipment.primary_tracking_number present → "tracked"
absent                                   → "order_only"
```

`order_only`: order confirmation emails that have not yet received a tracking number.
`tracked`: any shipment that has a carrier tracking number.

---

## Display merchant

`_resolve_display_merchant(merchant, sender_display_name, sender_domain) -> str`

Fallback chain (first non-None wins):
1. `merchant` — resolved by the classifier (most authoritative)
2. `sender_display_name` — from the email `From` header (e.g. `"Care to Beauty"`)
3. `sender_domain` — e.g. `"caretobeauty.com"`
4. `"Unknown"` — when no sender information is available

Raw `merchant` on the model is never mutated — `display_merchant` is computed purely for display.

Sender info is loaded in a single batch query via `_load_sender_info()` (oldest event per shipment)
to avoid N+1 queries.

---

## Display title rules

```python
def _display_title(shipment, display_merchant) -> str:
    has_merchant = display_merchant != "Unknown"

    if tracking:
        if has_merchant:  →  "{tracking} ({display_merchant})"
        else:
            prefix = _tracking_display_prefix(tracking)
            →  "{prefix} {tracking}"   # e.g. "UPS 1Z...", "Tracking 488..."

    if has_merchant and order:  →  "{display_merchant} #{order}"
    if order:                   →  "Order #{order}"
    fallback:                   →  "Shipment {canonical[:8]}"
```

Tracking prefix rules (`_TRACKING_PREFIX_RULES` — format-based, no carrier-brand ranking):

| Pattern | Prefix |
|---|---|
| `^1Z` | `"UPS"` |
| `^ECSA` | `"Shipment"` |
| `^ASO\d` | `"Shipment"` |
| `^[A-Z]{2}\d{8,10}[A-Z]{1,2}$` | `"Package"` (UPU format) |
| everything else | `"Tracking"` |

---

## Chronology reason codes

`chronology_reason` in projections is a structured machine-readable code (not prose):

| Code | Meaning |
|---|---|
| `"status_date_regression"` | A significant rank regression in main-status sequence |
| `"terminal_status_followed_by_non_terminal"` | Non-terminal event after `delivered` |
| `"duplicate_terminal_status"` | Multiple delivered events |

Populated by `ChronologyResult.reason_codes: list[str]` (parallel to `notes: list[str]`).
`chronology_reason` in projections = `reason_codes[0]` via the `reason_code` property.

---

## needs_review aggregation

Two independent sources; either one sets `needs_review=True`:

1. **Chronology**: `Shipment.chronology_severity != "ok"` (warning or conflict)
2. **Extraction-level**: any `email_extractions.needs_review = True` for an event linked to this shipment

For efficiency, source 2 is resolved in a single batch query:
```sql
SELECT DISTINCT shipment_events.canonical_shipment_id
FROM shipment_events
JOIN email_extractions ON email_extractions.email_id = shipment_events.email_id
WHERE email_extractions.needs_review = TRUE
```
This avoids N+1 queries across all shipments.

---

## Service entry points (`services/dashboard_projection_service.py`)

```python
DashboardProjectionService(session)
  .get_dashboard_projection() -> DashboardProjection
  .get_shipment_detail(canonical_id: str) -> ShipmentDetailProjection | None
```

Private helpers:
- `_load_sender_info(canonical_ids)` — single SQL query, returns dict of `canonical_id → (display_name, domain)` using oldest event per shipment
- `_load_needs_review_canonicals()` — single SQL query for extraction-level needs_review
- `_to_summary(shipment, extraction_needs_review, sender_info)` — builds ShipmentSummaryRow
- `_to_event_projection(event)` — builds ShipmentEventProjection (joins email_extractions)

---

## API endpoints (`api/routes_dashboard.py`)

| Method | Path | Response |
|---|---|---|
| GET | `/api/dashboard/projection` | `DashboardProjection` |
| GET | `/api/shipments/{canonical_id}/detail` | `ShipmentDetailProjection` (404 if not found) |

---

## Privacy invariants

- `status_evidence` in `ShipmentEventProjection` is already clipped before storage — the projection layer never re-clips, never reads raw email text.
- No PII flows through projection models. Merchant names and tracking numbers are identifiers, not personal data.
- `sender_display_name` stored in `shipment_events` is a brand/merchant name from automated shipping emails, not a real person's name.
- The projection layer is purely read-only; no DB writes.
