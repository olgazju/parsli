"""Tests for DashboardProjectionService — UI-ready projections from resolved data."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from parsli.config import ProcessingConfig
from parsli.db.models import Base, EmailExtraction
from parsli.domain.email_types import EmailType
from parsli.domain.statuses import ShipmentStatus
from parsli.processing.reconciler import DecisionSource, FinalClassificationResult
from parsli.services.dashboard_projection_service import DashboardProjectionService
from parsli.services.shipment_resolution_service import ShipmentResolutionService

DAY1 = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
DAY2 = datetime(2026, 5, 21, 10, 0, tzinfo=timezone.utc)
DAY3 = datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc)


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


@pytest.fixture()
def proj(session):
    return DashboardProjectionService(session)


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
    decision_source: DecisionSource = DecisionSource.RULE,
    needs_review: bool = False,
) -> FinalClassificationResult:
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
        decision_source=decision_source,
        conflict_reason=None,
        needs_review=needs_review,
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


def _insert_extraction_row(session, email_id: str, needs_review: bool) -> None:
    """Insert a minimal EmailExtraction row to test extraction-level needs_review."""
    row = EmailExtraction(
        email_id=email_id,
        processing_version="rules:v1;prompt:v2",
        email_type="shipping_update",
        status="in_transit",
        rule_status="in_transit",
        model_status=None,
        status_confidence=0.9,
        status_evidence="test",
        decision_source=DecisionSource.RULE.value,
        needs_review=needs_review,
        prompt_version="v2",
        rules_version="v1",
    )
    session.add(row)
    session.flush()


# ── Test 1: order_confirmation → order_only kind ───────────────────────────────


def test_order_only_appears_as_order_only(session, svc, proj):
    """order_confirmation with no tracking must project as shipment_kind='order_only'."""
    svc.resolve_and_insert(
        _extraction(
            email_type=EmailType.ORDER_CONFIRMATION,
            status=ShipmentStatus.ORDER_CONFIRMED,
            order="ORD-001",
            merchant="HOODIES",
        ),
        DAY1,
    )
    session.flush()

    dashboard = proj.get_dashboard_projection()
    assert len(dashboard.shipments) == 1

    row = dashboard.shipments[0]
    assert row.shipment_kind == "order_only"
    assert row.tracking_number is None
    assert row.merchant == "HOODIES"
    assert row.order_number == "ORD-001"
    assert "HOODIES" in row.display_title
    assert "ORD-001" in row.display_title
    assert dashboard.order_only_count == 1


# ── Test 2: tracking email → tracked kind ─────────────────────────────────────


def test_tracked_shipment_appears_as_tracked(session, svc, proj):
    """Shipping update with tracking must project as shipment_kind='tracked'."""
    svc.resolve_and_insert(
        _extraction(
            email_type=EmailType.SHIPPING_UPDATE,
            status=ShipmentStatus.IN_TRANSIT,
            tracking="LS233312341CH",
        ),
        DAY1,
    )
    session.flush()

    dashboard = proj.get_dashboard_projection()
    assert len(dashboard.shipments) == 1

    row = dashboard.shipments[0]
    assert row.shipment_kind == "tracked"
    assert row.tracking_number == "LS233312341CH"
    assert "LS233312341CH" in row.display_title
    assert dashboard.order_only_count == 0


# ── Test 3: tracked without merchant gets readable title ──────────────────────


def test_tracked_no_merchant_gets_readable_title(session, svc, proj):
    """A tracked shipment with no merchant must get a format-derived prefix, not a bare number."""
    svc.resolve_and_insert(
        _extraction(
            email_type=EmailType.SHIPPING_UPDATE,
            status=ShipmentStatus.IN_TRANSIT,
            tracking="1Z08407V0463442370",
            merchant=None,
        ),
        DAY1,
    )
    session.flush()

    dashboard = proj.get_dashboard_projection()
    row = dashboard.shipments[0]

    # Should be "UPS 1Z08407V0463442370", not a bare number
    assert row.display_title.startswith("UPS ")
    assert "1Z08407V0463442370" in row.display_title

    # Generic numeric tracking → "Tracking" prefix
    svc.resolve_and_insert(
        _extraction(
            email_id="email2",
            email_type=EmailType.SHIPPING_UPDATE,
            status=ShipmentStatus.IN_TRANSIT,
            tracking="488542204312345",
            merchant=None,
        ),
        DAY1,
    )
    session.flush()

    dashboard2 = proj.get_dashboard_projection()
    numeric_row = next(r for r in dashboard2.shipments if r.tracking_number == "488542204312345")
    assert numeric_row.display_title.startswith("Tracking ")


# ── Test 4: multi-event timeline in detail view ────────────────────────────────


def test_multi_event_timeline_in_detail(session, svc, proj):
    """Shipment with two events must appear with an ordered timeline."""
    svc.resolve_and_insert(
        _extraction(
            email_id="email1",
            email_type=EmailType.SHIPPING_UPDATE,
            status=ShipmentStatus.IN_TRANSIT,
            tracking="ECSA0041206",
        ),
        DAY1,
    )
    svc.resolve_and_insert(
        _extraction(
            email_id="email2",
            email_type=EmailType.PICKUP_READY,
            status=ShipmentStatus.ACTION_REQUIRED,
            tracking="ECSA0041206",
        ),
        DAY2,
    )
    session.flush()

    dashboard = proj.get_dashboard_projection()
    assert len(dashboard.shipments) == 1
    canonical_id = dashboard.shipments[0].shipment_id

    detail = proj.get_shipment_detail(canonical_id)
    assert detail is not None
    assert len(detail.events) == 2

    # Events must be in chronological order
    assert detail.events[0].event_date < detail.events[1].event_date
    assert detail.events[0].status == ShipmentStatus.IN_TRANSIT
    assert detail.events[1].status == ShipmentStatus.ACTION_REQUIRED


# ── Test 5: chronology warning surfaced with structured reason code ────────────


def test_chronology_warning_surfaced_with_reason_code(session, svc, proj):
    """A status regression must surface as warning with a structured chronology_reason code."""
    # out_for_delivery (rank 9) followed by in_transit (rank 3) — significant regression
    svc.resolve_and_insert(
        _extraction(
            email_id="email1",
            email_type=EmailType.SHIPPING_UPDATE,
            status=ShipmentStatus.OUT_FOR_DELIVERY,
            tracking="ECSA1111111",
        ),
        DAY1,
    )
    svc.resolve_and_insert(
        _extraction(
            email_id="email2",
            email_type=EmailType.SHIPPING_UPDATE,
            status=ShipmentStatus.IN_TRANSIT,
            tracking="ECSA1111111",
        ),
        DAY2,
    )
    session.flush()

    dashboard = proj.get_dashboard_projection()
    assert len(dashboard.shipments) == 1
    row = dashboard.shipments[0]

    assert row.chronology_status == "warning"
    assert row.chronology_reason == "status_date_regression"
    assert row.needs_review is True
    assert dashboard.needs_review_count == 1


# ── Test 6: terminal followed by non-terminal → conflict reason code ───────────


def test_terminal_followed_by_non_terminal_reason_code(session, svc, proj):
    """Non-terminal status after delivered must produce 'terminal_status_followed_by_non_terminal'."""
    svc.resolve_and_insert(
        _extraction(
            email_id="email1",
            email_type=EmailType.SHIPPING_UPDATE,
            status=ShipmentStatus.DELIVERED,
            tracking="ECSA9999999",
        ),
        DAY1,
    )
    svc.resolve_and_insert(
        _extraction(
            email_id="email2",
            email_type=EmailType.SHIPPING_UPDATE,
            status=ShipmentStatus.IN_TRANSIT,
            tracking="ECSA9999999",
        ),
        DAY2,
    )
    session.flush()

    dashboard = proj.get_dashboard_projection()
    row = dashboard.shipments[0]

    assert row.chronology_status == "conflict"
    assert row.chronology_reason == "terminal_status_followed_by_non_terminal"
    assert row.needs_review is True


# ── Test 7: digital_product / non_shipping excluded ───────────────────────────


def test_non_physical_emails_excluded_from_projection(session, svc, proj):
    """digital_product and non_shipping emails must not appear in dashboard projections."""
    svc.resolve_and_insert(
        _extraction(
            email_id="digital1",
            email_type=EmailType.DIGITAL_PRODUCT,
            status=ShipmentStatus.UNKNOWN,
            is_relevant=False,
            ignore_reason="digital_product",
            order="SAAS-PLAN-123",
        ),
        DAY1,
    )
    svc.resolve_and_insert(
        _extraction(
            email_id="nonship1",
            email_type=EmailType.NON_SHIPPING,
            status=ShipmentStatus.UNKNOWN,
            is_relevant=False,
            ignore_reason="non_shipping",
        ),
        DAY1,
    )
    # One real shipment to confirm projection works alongside excluded types
    svc.resolve_and_insert(
        _extraction(
            email_id="real1",
            email_type=EmailType.SHIPPING_UPDATE,
            status=ShipmentStatus.IN_TRANSIT,
            tracking="RU0136772947IL",
        ),
        DAY2,
    )
    session.flush()

    dashboard = proj.get_dashboard_projection()
    assert dashboard.total_count == 1
    assert dashboard.shipments[0].tracking_number == "RU0136772947IL"


# ── Test 8: extraction needs_review surfaced via join ─────────────────────────


def test_extraction_needs_review_surfaces_in_projection(session, svc, proj):
    """needs_review=True in email_extractions must be reflected in the summary row."""
    svc.resolve_and_insert(
        _extraction(
            email_id="conflict_email",
            email_type=EmailType.SHIPPING_UPDATE,
            status=ShipmentStatus.IN_TRANSIT,
            tracking="1Z999AA10123456784",
        ),
        DAY1,
    )
    session.flush()

    # Manually insert the extraction row with needs_review=True
    _insert_extraction_row(session, "conflict_email", needs_review=True)
    session.flush()

    dashboard = proj.get_dashboard_projection()
    assert len(dashboard.shipments) == 1
    row = dashboard.shipments[0]

    assert row.needs_review is True
    assert dashboard.needs_review_count == 1


# ── Test 9: sender display name used as display_merchant fallback ─────────────


def test_display_merchant_falls_back_to_sender_display_name(session, svc, proj):
    """When merchant is null, display_merchant must come from sender_display_name."""
    svc.resolve_and_insert(
        _extraction(
            email_id="email1",
            email_type=EmailType.ORDER_CONFIRMATION,
            status=ShipmentStatus.ORDER_CONFIRMED,
            order="ORD-100",
            merchant=None,
        ),
        DAY1,
        sender_display_name="Care to Beauty",
        sender_domain="caretobeauty.com",
    )
    session.flush()

    dashboard = proj.get_dashboard_projection()
    row = dashboard.shipments[0]

    assert row.display_merchant == "Care to Beauty"
    assert row.merchant is None
    assert "Care to Beauty" in row.display_title


# ── Test 10: sender domain used as final display_merchant fallback ─────────────


def test_display_merchant_falls_back_to_sender_domain(session, svc, proj):
    """When merchant and sender_display_name are null, display_merchant comes from domain."""
    svc.resolve_and_insert(
        _extraction(
            email_id="email1",
            email_type=EmailType.ORDER_CONFIRMATION,
            status=ShipmentStatus.ORDER_CONFIRMED,
            order="ORD-200",
            merchant=None,
        ),
        DAY1,
        sender_display_name=None,
        sender_domain="shopexample.com",
    )
    session.flush()

    dashboard = proj.get_dashboard_projection()
    row = dashboard.shipments[0]

    assert row.display_merchant == "shopexample.com"
    assert row.merchant is None


# ── Test 11: raw merchant unchanged when display_merchant is enriched ──────────


def test_raw_merchant_unchanged_when_display_merchant_enriched(session, svc, proj):
    """Raw merchant field must stay unchanged; only display_merchant is enriched."""
    svc.resolve_and_insert(
        _extraction(
            email_id="email1",
            email_type=EmailType.SHIPPING_UPDATE,
            status=ShipmentStatus.IN_TRANSIT,
            tracking="ECSA5555555",
            merchant="RAWMERCHANT",
        ),
        DAY1,
        sender_display_name="Pretty Display Name",
        sender_domain="rawmerchant.com",
    )
    session.flush()

    dashboard = proj.get_dashboard_projection()
    row = dashboard.shipments[0]

    # Resolved merchant takes priority over sender info
    assert row.merchant == "RAWMERCHANT"
    assert row.display_merchant == "RAWMERCHANT"

    # Verify detail projection also preserves raw merchant
    detail = proj.get_shipment_detail(row.shipment_id)
    assert detail is not None
    assert detail.merchant == "RAWMERCHANT"
    assert detail.display_merchant == "RAWMERCHANT"
