from datetime import datetime

from pydantic import BaseModel

from .statuses import ShipmentStatus


class ShipmentEventProjection(BaseModel):
    """One event in the shipment timeline, enriched with extraction observability."""

    event_date: datetime
    status: ShipmentStatus
    status_label: str
    status_confidence: float
    status_evidence: str
    tracking_number: str | None
    order_number: str | None
    email_id: str
    # From email_extractions — None when the extraction record is absent.
    decision_source: str | None
    needs_review: bool
    model_mode: str | None
    model_latency_ms: float | None


class ShipmentSummaryRow(BaseModel):
    """UI-ready summary row for the shipments list view."""

    shipment_id: str
    display_title: str
    merchant: str | None         # raw resolved merchant — unchanged, for provenance
    display_merchant: str        # enriched: merchant → sender display name → domain → "Unknown"
    tracking_number: str | None
    order_number: str | None
    current_status: ShipmentStatus
    current_status_label: str
    last_status_date: datetime
    events_count: int
    shipment_kind: str  # "tracked" | "order_only"
    chronology_status: str  # "ok" | "warning" | "conflict"
    chronology_reason: str | None  # structured reason code, or None
    needs_review: bool


class ShipmentDetailProjection(BaseModel):
    """Full detail view for one shipment — metadata + ordered timeline."""

    shipment_id: str
    display_title: str
    merchant: str | None         # raw resolved merchant — unchanged, for provenance
    display_merchant: str        # enriched: merchant → sender display name → domain → "Unknown"
    tracking_number: str | None
    order_number: str | None
    current_status: ShipmentStatus
    current_status_label: str
    last_status_date: datetime
    first_seen_at: datetime
    shipment_kind: str  # "tracked" | "order_only"
    chronology_status: str  # "ok" | "warning" | "conflict"
    chronology_reason: str | None  # first structured reason code, or None
    chronology_notes: list[str]
    needs_review: bool
    merge_confidence: float
    events: list[ShipmentEventProjection]


class DashboardProjection(BaseModel):
    """Dashboard payload — summary list + aggregated counts."""

    shipments: list[ShipmentSummaryRow]
    total_count: int
    active_count: int         # not yet delivered
    delivered_count: int
    order_only_count: int  # shipments with no tracking number
    needs_review_count: int
    generated_at: datetime
