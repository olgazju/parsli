"""ShipmentResolutionService — resolves canonical shipment IDs and rebuilds timelines.

Resolution algorithm (by email type):

order_confirmation (with order_number):
  - Canonical key = sha256("order:{ORDER}|{MERCHANT}")[:16] (merchant-qualified)
  - Creates order alias + order_confirmed event
  - Does NOT create or require a tracking number

shipping_update / pickup_ready / delivered / payment_problem:
  1. Look up tracking alias (most specific — carrier IDs are globally unique)
  2. Fall back to order + merchant alias (attaches tracking to an existing
     order-level timeline from a prior order_confirmation email)
  3. Derive new canonical from tracking, then from order
  - Creates tracking alias (with merge safety check), order alias, shipment event

Non-physical emails (digital_product, billing_only, non_shipping) and
irrelevant emails (is_relevant=False) are skipped entirely — no aliases,
events, or timeline rows are created for them.

Shipment events are inserted idempotently via an explicit existence check.
The Shipment row is rebuilt from all events after every insert.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..config import ProcessingConfig
from ..db.repositories import (
    ShipmentAliasRepository,
    ShipmentEventRepository,
    ShipmentRepository,
)
from ..domain.carriers import CarrierFamily, carrier_family_from_tracking
from ..domain.chronology import check_chronology, select_current_status
from ..domain.email_types import EmailType
from ..domain.events import ShipmentEventDTO
from ..domain.merge import MergeDecision, can_merge_tracking_numbers, canonical_shipment_id
from ..domain.shipments import ShipmentAliasDTO, ShipmentDTO
from ..domain.statuses import STATUS_LABELS, ShipmentStatus
from ..processing.reconciler import FinalClassificationResult as FinalExtraction

logger = logging.getLogger(__name__)

# These email types never produce physical logistics events.
_NON_PHYSICAL_TYPES: frozenset[EmailType] = frozenset({
    EmailType.NON_SHIPPING,
    EmailType.BILLING_ONLY,
    EmailType.DIGITAL_PRODUCT,
})


# Carriers with a non-numeric prefix are structurally identifiable — they sort
# first as the primary tracking number for display. Same principle as
# _STRUCTURED_CARRIERS in domain/identifiers.py; no carrier-brand ranking.
_STRUCTURED_FAMILIES: frozenset[CarrierFamily] = frozenset({
    CarrierFamily.UPS,
    CarrierFamily.ISRAEL_POST,
    CarrierFamily.HFD,
    CarrierFamily.ASOS,
})


def _tracking_sort_key(value: str) -> int:
    return 0 if carrier_family_from_tracking(value) in _STRUCTURED_FAMILIES else 1


def _order_alias_value(order: str, merchant: str | None) -> str:
    """Composite alias key for an order, qualified by merchant when known.

    Using merchant in the key prevents two different merchants' orders with
    identical order numbers from being merged into one shipment timeline.
    """
    if merchant:
        return f"{order.upper()}|{merchant.upper()}"
    return order.upper()


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

    def resolve_and_insert(
        self,
        extraction: FinalExtraction,
        received_at: datetime,
        *,
        sender_display_name: str | None = None,
        sender_domain: str | None = None,
    ) -> None:
        """Resolve canonical shipment ID, insert event, and update timeline.

        Persistence (processed_emails + email_extractions) is always done by
        ExtractionOrchestrator before this method is called. This method owns
        only the shipment layer — aliases, events, and timeline rows.

        Args:
            extraction: Fully reconciled FinalClassificationResult.
            received_at: When the original email was received (from email_messages).
            sender_display_name: Human-readable sender name from the email header
                (e.g. "Care to Beauty" from "Care to Beauty <help@caretobeauty.com>").
                Used as a display_merchant fallback in the projection layer.
            sender_domain: Sender domain (e.g. "caretobeauty.com"). Used as a
                final display_merchant fallback when merchant and display name are absent.
        """
        if not extraction.is_relevant:
            return
        if extraction.email_type in _NON_PHYSICAL_TYPES:
            return

        if extraction.email_type == EmailType.ORDER_CONFIRMATION:
            self._process_order_confirmation(
                extraction, received_at,
                sender_display_name=sender_display_name,
                sender_domain=sender_domain,
            )
        else:
            self._process_shipping_event(
                extraction, received_at,
                sender_display_name=sender_display_name,
                sender_domain=sender_domain,
            )

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

    # ── order_confirmation path ────────────────────────────────────────────────

    def _process_order_confirmation(
        self,
        extraction: FinalExtraction,
        received_at: datetime,
        *,
        sender_display_name: str | None = None,
        sender_domain: str | None = None,
    ) -> None:
        """Create an order-level timeline entry without inventing a tracking shipment."""
        order = extraction.selected_order_number
        if not order:
            return  # no identifier → cannot form a canonical shipment

        alias_val = _order_alias_value(order, extraction.merchant)
        canonical = self._alias_repo.find_canonical("order", alias_val)
        if canonical is None:
            canonical = canonical_shipment_id("order", alias_val)

        self._alias_repo.upsert(
            ShipmentAliasDTO(
                alias_type="order",
                alias_value=alias_val,
                canonical_shipment_id=canonical,
                confidence=extraction.status_confidence,
                evidence_email_id=extraction.email_id,
            )
        )

        event = ShipmentEventDTO(
            canonical_shipment_id=canonical,
            email_id=extraction.email_id,
            event_date=received_at,
            status=extraction.status,
            status_confidence=extraction.status_confidence,
            status_evidence=extraction.status_evidence,
            sender_domain=sender_domain,
            sender_display_name=sender_display_name,
            tracking_number=None,
            order_number=order,
            merchant=extraction.merchant,
            processing_version=extraction.processing_version,
        )
        self._event_repo.insert_if_new(event)
        self._rebuild_shipment(canonical)

    # ── shipping event path ────────────────────────────────────────────────────

    def _process_shipping_event(
        self,
        extraction: FinalExtraction,
        received_at: datetime,
        *,
        sender_display_name: str | None = None,
        sender_domain: str | None = None,
    ) -> None:
        """Create a carrier-level shipment event and update the timeline."""
        tracking = extraction.selected_tracking_number
        order = extraction.selected_order_number

        canonical = self._resolve_canonical_for_shipping(tracking, order, extraction.merchant)
        if canonical is None:
            return

        if tracking:
            self._register_tracking_alias(canonical, tracking, extraction)
        if order:
            self._alias_repo.upsert(
                ShipmentAliasDTO(
                    alias_type="order",
                    alias_value=_order_alias_value(order, extraction.merchant),
                    canonical_shipment_id=canonical,
                    confidence=extraction.status_confidence,
                    evidence_email_id=extraction.email_id,
                )
            )

        event = ShipmentEventDTO(
            canonical_shipment_id=canonical,
            email_id=extraction.email_id,
            event_date=received_at,
            status=extraction.status,
            status_confidence=extraction.status_confidence,
            status_evidence=extraction.status_evidence,
            sender_domain=sender_domain,
            sender_display_name=sender_display_name,
            tracking_number=tracking,
            order_number=order,
            merchant=extraction.merchant,
            processing_version=extraction.processing_version,
        )
        self._event_repo.insert_if_new(event)
        self._rebuild_shipment(canonical)

    def _resolve_canonical_for_shipping(
        self,
        tracking: str | None,
        order: str | None,
        merchant: str | None,
    ) -> str | None:
        """Resolve or derive the canonical shipment ID for a shipping event.

        Look-up priority:
        1. Exact tracking alias (carrier IDs are globally unique).
        2. Order + merchant alias (attaches tracking to an existing order timeline).
        3. Derive new canonical from tracking.
        4. Derive new canonical from order + merchant.
        """
        if tracking:
            known = self._alias_repo.find_canonical("tracking", tracking)
            if known:
                return known

        if order:
            known = self._alias_repo.find_canonical("order", _order_alias_value(order, merchant))
            if known:
                return known

        if tracking:
            return canonical_shipment_id("tracking", tracking)
        if order:
            return canonical_shipment_id("order", _order_alias_value(order, merchant))

        return None

    def _register_tracking_alias(
        self,
        canonical: str,
        tracking: str,
        extraction: FinalExtraction,
    ) -> None:
        """Register a tracking alias, checking for unsafe merges first."""
        existing = self._alias_repo.list_for_shipment(canonical)
        for alias in existing:
            if alias.alias_type == "tracking" and alias.alias_value != tracking.upper():
                decision: MergeDecision = can_merge_tracking_numbers(
                    alias.alias_value, tracking
                )
                if not decision.should_merge:
                    logger.warning(
                        "Skipping tracking alias %s → %s: %s",
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

    # ── timeline rebuild ───────────────────────────────────────────────────────

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
        tracking_numbers = sorted(
            (e.tracking_number for e in events if e.tracking_number),
            key=_tracking_sort_key,
        )
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
            chronology_reason_code=chrono.reason_code,
            event_count=len(events),
            first_seen_at=min(dates),
            last_seen_at=max(dates),
            updated_at=datetime.now(timezone.utc),
        )
        self._shipment_repo.upsert(shipment)
