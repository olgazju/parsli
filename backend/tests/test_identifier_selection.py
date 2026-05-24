"""Tests for candidate-level tracking identifier selection.

Verifies that select_best_tracking uses evidence quality (structure, source
context) rather than a hardcoded carrier ranking.
"""

from parsli.domain.identifiers import IdentifierExtractor, select_best_tracking
from parsli.processing.rule_engine import RuleEngine

_extractor = IdentifierExtractor()
_engine = RuleEngine()


def test_structured_beats_generic_numeric() -> None:
    # An ECSA-prefixed identifier (structured) must win over a DHL 10-digit
    # (generic numeric) present in the same email, regardless of order.
    body = "Your shipment ECSA0041206 is ready. Ref: 8785274012 tracking."
    candidates = _extractor.extract_tracking_candidates(body)
    best = select_best_tracking(candidates)
    assert best is not None
    assert best.value == "ECSA0041206"


def test_glued_ecsa_duplicate_normalized() -> None:
    # ECSA0041206ECSA0041206 must be collapsed to ECSA0041206 before selection.
    # The structured candidate must still win over any generic numeric co-present.
    body = "Tracking: ECSA0041206ECSA0041206. Your shipment 8785274012 is on its way."
    candidates = _extractor.extract_tracking_candidates(body)
    values = [c.value for c in candidates]
    assert "ECSA0041206" in values
    assert "ECSA0041206ECSA0041206" not in values
    best = select_best_tracking(candidates)
    assert best is not None
    assert best.value == "ECSA0041206"


def test_subject_identifier_beats_body_only() -> None:
    # When two otherwise-equal candidates exist (same structure tier), the one
    # found in the subject line must be selected over the body-only one.
    subject = "Shipment 123456789012345 is on its way"
    body = "Your reference shipment number: 432154321543215"
    result = _engine.extract("x", body, subject=subject)
    sources = {t.value: t.source for t in result.tracking_candidates}
    assert sources.get("123456789012345") == "subject", (
        "Identifier found in subject must carry source='subject'"
    )
    best = select_best_tracking(result.tracking_candidates)
    assert best is not None
    assert best.value == "123456789012345"


def test_generic_numeric_selected_when_only_candidate() -> None:
    # A generic numeric identifier with explicit shipping context must be
    # selected when it is the only valid candidate in the email.
    body = "Your tracking shipment number: 123456789012345"
    candidates = _extractor.extract_tracking_candidates(body)
    assert candidates, "FedEx 15-digit adjacent to shipping keywords must be extracted"
    best = select_best_tracking(candidates)
    assert best is not None
    assert best.value == "123456789012345"
