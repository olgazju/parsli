from datetime import datetime

from pydantic import BaseModel

from .statuses import ShipmentStatus


class ShipmentAliasDTO(BaseModel):
    alias_type: str  # "tracking" | "order"
    alias_value: str
    canonical_shipment_id: str
    confidence: float
    evidence_email_id: str
    created_at: datetime | None = None


class ShipmentDTO(BaseModel):
    canonical_shipment_id: str
    merchant: str | None
    primary_tracking_number: str | None
    primary_order_number: str | None
    current_status: ShipmentStatus
    current_status_label: str
    current_status_date: datetime
    current_status_evidence: str
    merge_confidence: float
    chronology_ok: bool
    chronology_severity: str  # "ok" | "warning" | "conflict"
    chronology_notes: list[str]
    event_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    updated_at: datetime


class DashboardDTO(BaseModel):
    shipments: list[ShipmentDTO]
    generated_at: datetime
    total_count: int
    active_count: int
    delivered_count: int
