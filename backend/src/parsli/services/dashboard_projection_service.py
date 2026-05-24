"""DashboardProjectionService — builds UI-ready projections from resolved shipment data.

Reads the pre-computed `shipments`, `shipment_events`, and `email_extractions`
tables. Never re-runs business logic — the projection layer is read-only and
derives everything from already-resolved rows.
"""

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import EmailExtraction, ShipmentEvent
from ..db.repositories import (
    EmailExtractionRepository,
    ShipmentEventRepository,
    ShipmentRepository,
)
from ..domain.events import ShipmentEventDTO
from ..domain.projections import (
    DashboardProjection,
    ShipmentDetailProjection,
    ShipmentEventProjection,
    ShipmentSummaryRow,
)
from ..domain.shipments import ShipmentDTO
from ..domain.statuses import STATUS_LABELS, TERMINAL_STATUSES

# Ordered display-prefix rules derived from tracking number format alone.
# "UPS" is structurally identifiable by the 1Z prefix (industry-standard).
# All other structured formats get generic labels ("Shipment", "Package").
# Pure-digit formats fall through to the "Tracking" fallback.
_TRACKING_PREFIX_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^1Z", re.IGNORECASE), "UPS"),
    (re.compile(r"^ECSA", re.IGNORECASE), "Shipment"),
    (re.compile(r"^ASO\d", re.IGNORECASE), "Shipment"),
    (re.compile(r"^[A-Z]{2}\d{8,10}[A-Z]{1,2}$"), "Package"),
]


def _tracking_display_prefix(tracking: str) -> str:
    for pattern, label in _TRACKING_PREFIX_RULES:
        if pattern.match(tracking):
            return label
    return "Tracking"


def _shipment_kind(shipment: ShipmentDTO) -> str:
    return "tracked" if shipment.primary_tracking_number else "order_only"


def _resolve_display_merchant(
    merchant: str | None,
    sender_display_name: str | None,
    sender_domain: str | None,
) -> str:
    """Resolve a human-readable merchant name for display.

    Fallback order:
    1. Resolved merchant from classification (most authoritative).
    2. Sender display name from the source email header.
    3. Sender domain as a last-resort identifier.
    4. "Unknown" when no sender information is available.

    The raw ``merchant`` field on the shipment/summary row is never mutated —
    this value is purely for UI display.
    """
    return merchant or sender_display_name or sender_domain or "Unknown"


def _display_title(shipment: ShipmentDTO, display_merchant: str) -> str:
    """Build a human-readable title using the enriched display_merchant.

    Priority:
    1. Tracking number — prefixed with display_merchant (if known) or format-derived label.
    2. Order number — prefixed with display_merchant or generic "Order #".
    3. Fallback to first 8 chars of canonical ID.
    """
    tracking = shipment.primary_tracking_number
    order = shipment.primary_order_number
    has_merchant = display_merchant != "Unknown"

    if tracking:
        if has_merchant:
            return f"{tracking} ({display_merchant})"
        prefix = _tracking_display_prefix(tracking)
        return f"{prefix} {tracking}"

    if has_merchant and order:
        return f"{display_merchant} #{order}"
    if order:
        return f"Order #{order}"
    return f"Shipment {shipment.canonical_shipment_id[:8]}"


class DashboardProjectionService:
    """Builds UI-ready projections from resolved shipment data.

    Args:
        session: SQLAlchemy session (read-only usage).
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._shipment_repo = ShipmentRepository(session)
        self._event_repo = ShipmentEventRepository(session)
        self._extraction_repo = EmailExtractionRepository(session)

    def get_dashboard_projection(self) -> DashboardProjection:
        """Return the full dashboard payload: summary rows + aggregated counts.

        Returns:
            DashboardProjection with all shipments projected as ShipmentSummaryRows.
        """
        shipments = self._shipment_repo.list_all()
        needs_review_canonicals = self._load_needs_review_canonicals()

        canonical_ids = [s.canonical_shipment_id for s in shipments]
        sender_info = self._load_sender_info(canonical_ids)

        rows = [
            self._to_summary(
                s,
                s.canonical_shipment_id in needs_review_canonicals,
                sender_info.get(s.canonical_shipment_id, (None, None)),
            )
            for s in shipments
        ]

        total = len(rows)
        delivered = sum(1 for r in rows if r.current_status in TERMINAL_STATUSES)

        return DashboardProjection(
            shipments=rows,
            total_count=total,
            active_count=total - delivered,
            delivered_count=delivered,
            order_only_count=sum(1 for r in rows if r.shipment_kind == "order_only"),
            needs_review_count=sum(1 for r in rows if r.needs_review),
            generated_at=datetime.now(timezone.utc),
        )

    def get_shipment_detail(self, canonical_id: str) -> ShipmentDetailProjection | None:
        """Return the full detail projection for one shipment.

        Args:
            canonical_id: 16-char canonical shipment ID.

        Returns:
            ShipmentDetailProjection with ordered timeline, or None if not found.
        """
        shipment = self._shipment_repo.get(canonical_id)
        if shipment is None:
            return None

        events = self._event_repo.list_for_shipment(canonical_id)
        needs_review_canonicals = self._load_needs_review_canonicals()
        sender_info = self._load_sender_info([canonical_id])
        display_name, domain = sender_info.get(canonical_id, (None, None))
        display_merchant = _resolve_display_merchant(shipment.merchant, display_name, domain)

        return ShipmentDetailProjection(
            shipment_id=shipment.canonical_shipment_id,
            display_title=_display_title(shipment, display_merchant),
            merchant=shipment.merchant,
            display_merchant=display_merchant,
            tracking_number=shipment.primary_tracking_number,
            order_number=shipment.primary_order_number,
            current_status=shipment.current_status,
            current_status_label=shipment.current_status_label,
            last_status_date=shipment.current_status_date,
            first_seen_at=shipment.first_seen_at,
            shipment_kind=_shipment_kind(shipment),
            chronology_status=shipment.chronology_severity,
            chronology_reason=shipment.chronology_reason_code,
            chronology_notes=shipment.chronology_notes,
            needs_review=(
                shipment.chronology_severity != "ok"
                or shipment.canonical_shipment_id in needs_review_canonicals
            ),
            merge_confidence=shipment.merge_confidence,
            events=[self._to_event_projection(e) for e in events],
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _to_summary(
        self,
        shipment: ShipmentDTO,
        extraction_needs_review: bool,
        sender_info: tuple[str | None, str | None],
    ) -> ShipmentSummaryRow:
        display_name, domain = sender_info
        display_merchant = _resolve_display_merchant(shipment.merchant, display_name, domain)
        return ShipmentSummaryRow(
            shipment_id=shipment.canonical_shipment_id,
            display_title=_display_title(shipment, display_merchant),
            merchant=shipment.merchant,
            display_merchant=display_merchant,
            tracking_number=shipment.primary_tracking_number,
            order_number=shipment.primary_order_number,
            current_status=shipment.current_status,
            current_status_label=shipment.current_status_label,
            last_status_date=shipment.current_status_date,
            events_count=shipment.event_count,
            shipment_kind=_shipment_kind(shipment),
            chronology_status=shipment.chronology_severity,
            chronology_reason=shipment.chronology_reason_code,
            needs_review=shipment.chronology_severity != "ok" or extraction_needs_review,
        )

    def _to_event_projection(self, event: ShipmentEventDTO) -> ShipmentEventProjection:
        extraction = self._extraction_repo.get(event.email_id, event.processing_version)
        return ShipmentEventProjection(
            event_date=event.event_date,
            status=event.status,
            status_label=STATUS_LABELS.get(event.status, event.status.value),
            status_confidence=event.status_confidence,
            status_evidence=event.status_evidence,
            tracking_number=event.tracking_number,
            order_number=event.order_number,
            email_id=event.email_id,
            decision_source=extraction.decision_source if extraction else None,
            needs_review=bool(extraction.needs_review) if extraction else False,
            model_mode=extraction.model_mode if extraction else None,
            model_latency_ms=extraction.model_latency_ms if extraction else None,
        )

    def _load_needs_review_canonicals(self) -> set[str]:
        """Return canonical IDs where any event's extraction has needs_review=True."""
        rows = self._session.execute(
            select(ShipmentEvent.canonical_shipment_id)
            .join(EmailExtraction, EmailExtraction.email_id == ShipmentEvent.email_id)
            .where(EmailExtraction.needs_review.is_(True))
            .distinct()
        ).scalars()
        return set(rows)

    def _load_sender_info(
        self, canonical_ids: list[str]
    ) -> dict[str, tuple[str | None, str | None]]:
        """Return (sender_display_name, sender_domain) from the oldest event per shipment.

        Uses the first (chronologically earliest) event so the original sender
        is preferred over any subsequent forwarded or re-sent emails.
        """
        if not canonical_ids:
            return {}
        rows = self._session.execute(
            select(
                ShipmentEvent.canonical_shipment_id,
                ShipmentEvent.sender_display_name,
                ShipmentEvent.sender_domain,
            )
            .where(ShipmentEvent.canonical_shipment_id.in_(canonical_ids))
            .order_by(ShipmentEvent.event_date)
        ).all()

        result: dict[str, tuple[str | None, str | None]] = {}
        for row in rows:
            cid = row.canonical_shipment_id
            if cid not in result:
                result[cid] = (row.sender_display_name, row.sender_domain)
        return result
