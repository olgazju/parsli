"""Tests for merge and alias resolution logic."""

import pytest

from parsli.domain.merge import can_merge_tracking_numbers


def test_identical_tracking_always_merge():
    d = can_merge_tracking_numbers("RU0136772947Z", "RU0136772947Z")
    assert d.should_merge is True


def test_asos_hfd_different_families_no_merge():
    # ASOS and HFD are different carrier families — no automatic cross-family merge
    d = can_merge_tracking_numbers("ASO1006GB02687136001", "ECSA0086743")
    assert d.should_merge is False


def test_different_russia_post_no_merge():
    # RU* tracking numbers from the same carrier must NOT auto-merge
    d = can_merge_tracking_numbers("RU0136772947Z", "RU0136815887Z")
    assert d.should_merge is False


def test_different_carrier_families_no_merge():
    d = can_merge_tracking_numbers("1Z999AA10123456784", "123456789012345")
    # UPS vs FedEx — different families, no alias evidence
    assert d.should_merge is False


def test_canonical_id_is_stable():
    from parsli.domain.merge import canonical_shipment_id
    id1 = canonical_shipment_id("tracking", "RU0136772947Z")
    id2 = canonical_shipment_id("tracking", "RU0136772947Z")
    assert id1 == id2
    assert len(id1) == 16


def test_canonical_id_case_insensitive():
    from parsli.domain.merge import canonical_shipment_id
    assert canonical_shipment_id("tracking", "ru0136772947z") == canonical_shipment_id(
        "tracking", "RU0136772947Z"
    )
