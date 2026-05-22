"""ShipmentResolutionService — resolves canonical shipment IDs and rebuilds timelines.

Resolution algorithm (in order):
1. For each tracking number in the extraction, look up the alias table.
2. If a known alias exists, use its canonical_shipment_id.
3. If multiple aliases are found, they're already linked — use the first one.
4. For new tracking numbers, derive a canonical ID and check merge eligibility
   against existing aliases via can_merge_tracking_numbers().
5. Insert shipment_events rows (idempotent via unique constraint).
6. Rebuild the Shipment row from all events.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..config import ProcessingConfig
from ..db.repositories import (
    ShipmentAliasRepository,
    ShipmentEventRepository,
    ShipmentRepository,
)
from ..domain.chronology import check_chronology, select_current_status
from ..domain.events import ShipmentEventDTO
from ..domain.merge import MergeDecision, can_merge_tracking_numbers, canonical_shipment_id
from ..domain.shipments import ShipmentAliasDTO, ShipmentDTO
from ..domain.statuses import STATUS_LABELS, ShipmentStatus
from ..processing.extraction_orchestrator import FinalExtraction

logger = logging.getLogger(__name__)


class ShipmentResolutionService:
    """Maintains shipment identity and rebuilds timeline rows from extractions.

    Args:
        session: SQLAlchemy session (caller manages commit/rollback).
        processing: ProcessingConfig for version stamps.
    """

    def __init__(self, session: Session, processing: ProcessingConfig) -> None:
        self._session = session
        self._alias_repo = ShipmentAliasRepository(session)
        self._event_repo = ShipmentEventRepository(session)
        self._shipment_repo = ShipmentRepository(session)
        self._processing = processing

    def resolve_and_insert(self, extraction: FinalExtraction, received_at: datetime) -> None:
        """Resolve the canonical shipment ID for an extraction and insert events."""
        if not extraction.is_relevant:
            return
        if extraction.status == ShipmentStatus.UNKNOWN:
            return

        canonical = self._resolve_canonical(extraction)
        if canonical is None:
            return

        self._register_aliases(extraction, canonical)

        event = ShipmentEventDTO(
            canonical_shipment_id=canonical,
            email_id=extraction.email_id,
            event_date=received_at,
            status=extraction.status,
            status_confidence=extraction.status_confidence,
            status_evidence=extraction.status_evidence,
            sender_domain=None,
            tracking_number=extraction.selected_tracking_number,
            order_number=extraction.selected_order_number,
            merchant=extraction.merchant,
            processing_version=extraction.processing_version,
        )
        self._event_repo.insert_if_new(event)
        self._rebuild_shipment(canonical)

    def rebuild_all(self) -> None:
        """Rebuild every shipment row from scratch."""
        all_shipments = self._shipment_repo.list_all()
        for s in all_shipments:
            self._rebuild_shipment(s.canonical_shipment_id)

    def rebuild_affected(self, email_ids: list[str]) -> None:
        """Rebuild only shipments touched by the given email IDs."""
        affected = self._event_repo.affected_shipment_ids(email_ids)
        for cid in affected:
            self._rebuild_shipment(cid)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _resolve_canonical(self, extraction: FinalExtraction) -> str | None:
        """Return the canonical_shipment_id for this extraction, or None if undecidable."""
        tracking = extraction.selected_tracking_number
        order = extraction.selected_order_number

        # Try tracking alias first (more specific)
        if tracking:
            known = self._alias_repo.find_canonical("tracking", tracking)
            if known:
                return known

        # Try order alias
        if order:
            known = self._alias_repo.find_canonical("order", order)
            if known:
                return known

        # Nothing known — derive a new canonical ID from primary identifier
        if tracking:
            return canonical_shipment_id("tracking", tracking)
        if order:
            return canonical_shipment_id("order", order)

        # No identifier at all — cannot form a shipment
        return None

    def _register_aliases(self, extraction: FinalExtraction, canonical: str) -> None:
        """Write alias rows for all identifiers in the extraction."""
        tracking = extraction.selected_tracking_number
        order = extraction.selected_order_number

        if tracking:
            # Check merge safety if another tracking is already linked to this canonical
            existing_aliases = self._alias_repo.list_for_shipment(canonical)
            for alias in existing_aliases:
                if alias.alias_type == "tracking" and alias.alias_value != tracking.upper():
                    decision: MergeDecision = can_merge_tracking_numbers(
                        alias.alias_value, tracking
                    )
                    if not decision.should_merge:
                        logger.warning(
                            "Skipping alias %s → %s: %s",
                            tracking,
                            canonical,
                            decision.reason,
                        )
                        return

            self._alias_repo.upsert(
                ShipmentAliasDTO(
                    alias_type="tracking",
                    alias_value=tracking,
                    canonical_shipment_id=canonical,
                    confidence=extraction.status_confidence,
                    evidence_email_id=extraction.email_id,
                )
            )

        if order:
            self._alias_repo.upsert(
                ShipmentAliasDTO(
                    alias_type="order",
                    alias_value=order,
                    canonical_shipment_id=canonical,
                    confidence=extraction.status_confidence,
                    evidence_email_id=extraction.email_id,
                )
            )

    def _rebuild_shipment(self, canonical: str) -> None:
        """Recompute the Shipment row from all its events."""
        events = self._event_repo.list_for_shipment(canonical)
        if not events:
            return

        chrono = check_chronology(events)
        current_event = select_current_status(events)
        if current_event is None:
            return

        dates = [e.event_date for e in events]
        merchants = [e.merchant for e in events if e.merchant]
        tracking_numbers = [e.tracking_number for e in events if e.tracking_number]
        order_numbers = [e.order_number for e in events if e.order_number]

        aliases = self._alias_repo.list_for_shipment(canonical)
        merge_confidence = min((a.confidence for a in aliases), default=1.0)

        shipment = ShipmentDTO(
            canonical_shipment_id=canonical,
            merchant=merchants[0] if merchants else None,
            primary_tracking_number=tracking_numbers[0] if tracking_numbers else None,
            primary_order_number=order_numbers[0] if order_numbers else None,
            current_status=current_event.status,
            current_status_label=STATUS_LABELS.get(current_event.status, current_event.status.value),
            current_status_date=current_event.event_date,
            current_status_evidence=current_event.status_evidence,
            merge_confidence=merge_confidence,
            chronology_ok=chrono.ok,
            chronology_severity=chrono.severity,
            chronology_notes=chrono.notes,
            event_count=len(events),
            first_seen_at=min(dates),
            last_seen_at=max(dates),
            updated_at=datetime.now(timezone.utc),
        )
        self._shipment_repo.upsert(shipment)
