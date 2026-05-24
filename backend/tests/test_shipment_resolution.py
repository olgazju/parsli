"""Tests for ShipmentResolutionService — architecture, routing, and idempotency."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from parsli.config import ProcessingConfig
from parsli.db.models import Base, Shipment, ShipmentAlias, ShipmentEvent
from parsli.domain.email_types import EmailType
from parsli.domain.statuses import ShipmentStatus
from parsli.processing.reconciler import DecisionSource, FinalClassificationResult
from parsli.services.shipment_resolution_service import (
    ShipmentResolutionService,
    _order_alias_value,
)

NOW = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)
DAY2 = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s


@pytest.fixture()
def svc(session):
    return ShipmentResolutionService(session, ProcessingConfig())


# ── Helper factory ─────────────────────────────────────────────────────────────


def _extraction(
    *,
    email_id: str = "email1",
    email_type: EmailType = EmailType.SHIPPING_UPDATE,
    status: ShipmentStatus = ShipmentStatus.IN_TRANSIT,
    tracking: str | None = None,
    order: str | None = None,
    merchant: str | None = None,
    is_relevant: bool = True,
    ignore_reason: str | None = None,
) -> FinalClassificationResult:
    """Build a minimal FinalClassificationResult for resolution tests."""
    return FinalClassificationResult(
        email_id=email_id,
        processing_version="rules:v1;prompt:v2",
        email_type=email_type,
        rule_email_type=email_type,
        model_email_type=None,
        status=status,
        rule_status=status,
        model_status=None,
        status_confidence=0.90,
        status_evidence="test evidence",
        rule_confidence=0.90,
        model_confidence=None,
        selected_tracking_number=tracking,
        tracking_candidates=[],
        selected_order_number=order,
        order_candidates=[],
        merchant=merchant,
        carrier=None,
        pickup_code=None,
        amount=None,
        currency=None,
        is_relevant=is_relevant,
        ignore_reason=ignore_reason,
        is_invoice=False,
        decision_source=DecisionSource.RULE,
        conflict_reason=None,
        needs_review=False,
        model_called=False,
        model_mode="skip_model",
        model_latency_ms=None,
        prompt_tokens=None,
        completion_tokens=None,
        rule_model_agreed=None,
        confidence_delta=None,
        model_provider=None,
        model_name=None,
        classification_method="rules_only",
    )


# ── _order_alias_value unit tests ──────────────────────────────────────────────


def test_order_alias_value_with_merchant():
    assert _order_alias_value("ord-001", "HOODIES") == "ORD-001|HOODIES"


def test_order_alias_value_without_merchant():
    assert _order_alias_value("ord-001", None) == "ORD-001"


def test_order_alias_value_normalises_case():
    assert _order_alias_value("ord-001", "Hoodies") == "ORD-001|HOODIES"


# ── Test 1: digital_product skipped — no shipment layer created ────────────────


def test_digital_product_creates_no_shipment(session, svc):
    """SaaS / digital product emails must be persisted but produce no shipment data."""
    ext = _extraction(
        email_type=EmailType.DIGITAL_PRODUCT,
        status=ShipmentStatus.UNKNOWN,
        is_relevant=False,
        ignore_reason="digital_product",
        order="SaaS-Plan-123",
    )
    svc.resolve_and_insert(ext, NOW)
    session.flush()

    assert session.execute(select(ShipmentEvent)).scalar_one_or_none() is None
    assert session.execute(select(ShipmentAlias)).scalar_one_or_none() is None
    assert session.execute(select(Shipment)).scalar_one_or_none() is None


# ── Test 2: order_confirmation creates order-level event, no tracking alias ───


def test_order_confirmation_creates_order_level_event_only(session, svc):
    """HOODIES order_confirmation: order alias + event created, no tracking alias."""
    ext = _extraction(
        email_type=EmailType.ORDER_CONFIRMATION,
        status=ShipmentStatus.ORDER_CONFIRMED,
        order="ORD-001",
        merchant="HOODIES",
        tracking=None,
    )
    svc.resolve_and_insert(ext, NOW)
    session.flush()

    # Exactly one event
    events = list(session.execute(select(ShipmentEvent)).scalars())
    assert len(events) == 1
    assert events[0].status == "order_confirmed"
    assert events[0].tracking_number is None
    assert events[0].order_number == "ORD-001"

    # Order alias exists with composite key
    aliases = list(session.execute(select(ShipmentAlias)).scalars())
    order_aliases = [a for a in aliases if a.alias_type == "order"]
    assert len(order_aliases) == 1
    assert "ORD-001" in order_aliases[0].alias_value
    assert "HOODIES" in order_aliases[0].alias_value

    # No tracking alias
    assert not any(a.alias_type == "tracking" for a in aliases)

    # Shipment timeline has no tracking number
    shipments = list(session.execute(select(Shipment)).scalars())
    assert len(shipments) == 1
    assert shipments[0].primary_tracking_number is None
    assert shipments[0].current_status == "order_confirmed"


# ── Test 3: Israel Post tracking email creates shipment timeline ───────────────


def test_israel_post_tracking_creates_shipment_timeline(session, svc):
    ext = _extraction(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        tracking="RU0136772947IL",
    )
    svc.resolve_and_insert(ext, NOW)
    session.flush()

    events = list(session.execute(select(ShipmentEvent)).scalars())
    assert len(events) == 1
    assert events[0].status == "in_transit"
    assert events[0].tracking_number == "RU0136772947IL"

    aliases = list(session.execute(select(ShipmentAlias)).scalars())
    tracking_aliases = [a for a in aliases if a.alias_type == "tracking"]
    assert len(tracking_aliases) == 1
    assert tracking_aliases[0].alias_value == "RU0136772947IL"

    shipments = list(session.execute(select(Shipment)).scalars())
    assert len(shipments) == 1
    assert shipments[0].primary_tracking_number == "RU0136772947IL"
    assert shipments[0].current_status == "in_transit"


# ── Test 4: HFD pickup_ready with ECSA tracking creates shipment event ─────────


def test_hfd_pickup_ready_creates_shipment_event(session, svc):
    ext = _extraction(
        email_type=EmailType.PICKUP_READY,
        status=ShipmentStatus.ACTION_REQUIRED,
        tracking="ECSA1234567",
    )
    svc.resolve_and_insert(ext, NOW)
    session.flush()

    events = list(session.execute(select(ShipmentEvent)).scalars())
    assert len(events) == 1
    assert events[0].status == "action_required"
    assert events[0].tracking_number == "ECSA1234567"

    shipments = list(session.execute(select(Shipment)).scalars())
    assert len(shipments) == 1
    assert shipments[0].current_status == "action_required"


# ── Test 5: re-processing same email does not duplicate events ─────────────────


def test_reprocessing_does_not_duplicate_events(session, svc):
    ext = _extraction(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.DELIVERED,
        tracking="1Z999AA10123456784",
    )
    svc.resolve_and_insert(ext, NOW)
    session.flush()

    svc.resolve_and_insert(ext, NOW)
    session.flush()

    events = list(session.execute(select(ShipmentEvent)).scalars())
    assert len(events) == 1  # idempotent — second call is a no-op

    shipments = list(session.execute(select(Shipment)).scalars())
    assert len(shipments) == 1


# ── Test 6: tracking attaches to existing order timeline ──────────────────────


def test_tracking_attaches_to_existing_order_timeline(session, svc):
    """order_confirmation followed by shipping_update (same order+merchant+tracking)
    must attach the tracking to the same canonical instead of creating a second shipment.
    """
    # Step 1 — order_confirmation: creates the order-level canonical
    order_ext = _extraction(
        email_id="order_email",
        email_type=EmailType.ORDER_CONFIRMATION,
        status=ShipmentStatus.ORDER_CONFIRMED,
        order="ORD-42",
        merchant="All4Pet",
        tracking=None,
    )
    svc.resolve_and_insert(order_ext, NOW)
    session.flush()

    # Step 2 — shipping_update: same order+merchant, now with tracking
    ship_ext = _extraction(
        email_id="ship_email",
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        order="ORD-42",
        merchant="All4Pet",
        tracking="ECSA9876543",
    )
    svc.resolve_and_insert(ship_ext, DAY2)
    session.flush()

    # Both events exist
    events = list(session.execute(select(ShipmentEvent)).scalars())
    assert len(events) == 2

    # All events share the same canonical_shipment_id
    canonical_ids = {e.canonical_shipment_id for e in events}
    assert len(canonical_ids) == 1, "events must belong to a single canonical shipment"

    # All aliases point to the same canonical
    aliases = list(session.execute(select(ShipmentAlias)).scalars())
    alias_canonicals = {a.canonical_shipment_id for a in aliases}
    assert len(alias_canonicals) == 1

    # Tracking alias now registered
    tracking_aliases = [a for a in aliases if a.alias_type == "tracking"]
    assert len(tracking_aliases) == 1
    assert tracking_aliases[0].alias_value == "ECSA9876543"

    # One shipment with tracking and latest status
    shipments = list(session.execute(select(Shipment)).scalars())
    assert len(shipments) == 1
    assert shipments[0].primary_tracking_number == "ECSA9876543"
    assert shipments[0].current_status == "in_transit"
    assert shipments[0].event_count == 2
