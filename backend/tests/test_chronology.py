"""Tests for chronology checking and current-status selection."""

from datetime import datetime, timedelta, timezone

import pytest

from parsli.domain.chronology import check_chronology, select_current_status
from parsli.domain.events import ShipmentEventDTO
from parsli.domain.statuses import ShipmentStatus


def _event(
    status: ShipmentStatus,
    days_ago: int,
    email_id: str = "e1",
    tracking: str | None = None,
) -> ShipmentEventDTO:
    return ShipmentEventDTO(
        canonical_shipment_id="test_shipment",
        email_id=email_id,
        event_date=datetime.now(timezone.utc) - timedelta(days=days_ago),
        status=status,
        status_confidence=0.9,
        status_evidence="test",
        sender_domain=None,
        tracking_number=tracking,
        order_number=None,
        merchant=None,
        processing_version="rules:v1;prompt:v1",
    )


def test_happy_path_no_conflict():
    events = [
        _event(ShipmentStatus.SHIPPED, 10),
        _event(ShipmentStatus.IN_TRANSIT, 7),
        _event(ShipmentStatus.OUT_FOR_DELIVERY, 1),
        _event(ShipmentStatus.DELIVERED, 0),
    ]
    result = check_chronology(events)
    assert result.severity == "ok"
    assert result.notes == []


def test_delivered_terminal():
    events = [
        _event(ShipmentStatus.DELIVERED, 2),
        _event(ShipmentStatus.SHIPPED, 0),  # arrives after delivered — conflict
    ]
    result = check_chronology(events)
    assert result.severity == "conflict"


def test_action_required_after_ready_for_pickup_ok():
    # action_required is a side status — must not cause conflict
    events = [
        _event(ShipmentStatus.READY_FOR_PICKUP, 5),
        _event(ShipmentStatus.ACTION_REQUIRED, 2),
    ]
    result = check_chronology(events)
    assert result.severity == "ok"


def test_unknown_does_not_conflict():
    events = [
        _event(ShipmentStatus.SHIPPED, 5),
        _event(ShipmentStatus.UNKNOWN, 3),
        _event(ShipmentStatus.DELIVERED, 0),
    ]
    result = check_chronology(events)
    assert result.severity == "ok"


def test_delayed_does_not_conflict():
    events = [
        _event(ShipmentStatus.IN_TRANSIT, 5),
        _event(ShipmentStatus.DELAYED_OR_PROBLEM, 3),
        _event(ShipmentStatus.OUT_FOR_DELIVERY, 1),
    ]
    result = check_chronology(events)
    assert result.severity == "ok"


def test_current_status_delivered_wins():
    events = [
        _event(ShipmentStatus.ACTION_REQUIRED, 1),
        _event(ShipmentStatus.DELIVERED, 0),
    ]
    current = select_current_status(events)
    assert current is not None
    assert current.status == ShipmentStatus.DELIVERED


def test_current_status_action_overrides_older_status():
    # action_required is more recent than the last main status → overrides
    events = [
        _event(ShipmentStatus.READY_FOR_PICKUP, 5),
        _event(ShipmentStatus.ACTION_REQUIRED, 1),
    ]
    current = select_current_status(events)
    assert current is not None
    assert current.status == ShipmentStatus.ACTION_REQUIRED


def test_unknown_does_not_override_known():
    events = [
        _event(ShipmentStatus.IN_TRANSIT, 3),
        _event(ShipmentStatus.UNKNOWN, 0),
    ]
    current = select_current_status(events)
    assert current is not None
    assert current.status == ShipmentStatus.IN_TRANSIT
