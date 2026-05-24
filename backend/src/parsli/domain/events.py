from datetime import datetime

from pydantic import BaseModel

from .statuses import ShipmentStatus


class ShipmentEventDTO(BaseModel):
    id: int | None = None
    canonical_shipment_id: str
    email_id: str
    event_date: datetime
    status: ShipmentStatus
    status_confidence: float
    status_evidence: str
    sender_domain: str | None
    sender_display_name: str | None = None
    tracking_number: str | None
    order_number: str | None
    merchant: str | None
    processing_version: str
    created_at: datetime | None = None
