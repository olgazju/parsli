"""Tests for ClassificationReconciler — decision source, conflict detection, no-model path."""

import pytest

from parsli.config import PrivacyConfig
from parsli.domain.email_types import EmailType, email_type_from_status
from parsli.domain.identifiers import OrderIdentifier, TrackingIdentifier
from parsli.domain.statuses import ShipmentStatus
from parsli.model.base import ModelClassificationResult
from parsli.processing.cleaner import CleanedEmail
from parsli.processing.model_classifier import ModelCallObservability, ModelExecutionMode
from parsli.processing.reconciler import (
    ClassificationReconciler,
    DecisionSource,
    FinalClassificationResult,
    _has_shipping_evidence,
)
from parsli.processing.rule_engine import RuleExtractionResult


# ── Helpers ───────────────────────────────────────────────────────────────────


def _cleaned(shipping_shaped: bool = True) -> CleanedEmail:
    return CleanedEmail(
        email_id="test-id",
        cleaned_text="parcel is on the way",
        cleaned_text_hash="abc123",
        cleaned_full_len=20,
        is_shipping_shaped=shipping_shaped,
    )


def _rules(
    *,
    status: ShipmentStatus | None = None,
    confidence: float = 0.0,
    is_shipping: bool = False,
    is_invoice: bool = False,
    tracking: list[TrackingIdentifier] | None = None,
    orders: list[OrderIdentifier] | None = None,
    merchant: str | None = None,
    evidence: str = "",
) -> RuleExtractionResult:
    return RuleExtractionResult(
        is_shipping_email=is_shipping,
        is_invoice=is_invoice,
        status=status,
        status_confidence=confidence,
        status_evidence=evidence,
        tracking_candidates=tracking or [],
        order_candidates=orders or [],
        merchant=merchant,
        pickup_code=None,
        amount=None,
        currency=None,
    )


def _model(
    *,
    email_type: EmailType = EmailType.SHIPPING_UPDATE,
    status: ShipmentStatus = ShipmentStatus.UNKNOWN,
    confidence: float = 0.0,
    evidence: str = "",
    tracking: list[str] | None = None,
    orders: list[str] | None = None,
    merchant: str | None = None,
    carrier: str | None = None,
) -> ModelClassificationResult:
    return ModelClassificationResult(
        email_type=email_type,
        status=status,
        status_confidence=confidence,
        status_evidence=evidence,
        merchant=merchant,
        carrier=carrier,
        tracking_numbers=tracking or [],
        order_numbers=orders or [],
    )


def _obs(*, called: bool = False, mode: ModelExecutionMode = ModelExecutionMode.SKIP_MODEL) -> ModelCallObservability:
    return ModelCallObservability(mode=mode, called=called)


def _reconcile(
    rules: RuleExtractionResult,
    model: ModelClassificationResult | None,
    obs: ModelCallObservability | None = None,
    cleaned: CleanedEmail | None = None,
) -> FinalClassificationResult:
    reconciler = ClassificationReconciler()
    return reconciler.reconcile(
        rules=rules,
        model=model,
        obs=obs or _obs(),
        cleaned=cleaned or _cleaned(),
        email_id="test-id",
        processing_version="rules:v1;prompt:v2",
        model_provider="lmstudio",
        model_name="gemma",
        privacy=PrivacyConfig(evidence_max_chars=240),
    )


# ── email_type_from_status ─────────────────────────────────────────────────────


def test_invoice_overrides_status():
    assert email_type_from_status(ShipmentStatus.SHIPPED, is_invoice=True) == EmailType.BILLING_ONLY


def test_none_status_is_non_shipping():
    assert email_type_from_status(None, is_invoice=False) == EmailType.NON_SHIPPING


def test_delivered_maps_to_delivered():
    assert email_type_from_status(ShipmentStatus.DELIVERED, is_invoice=False) == EmailType.DELIVERED


def test_action_required_maps_to_pickup_ready():
    assert email_type_from_status(ShipmentStatus.ACTION_REQUIRED, is_invoice=False) == EmailType.PICKUP_READY


def test_payment_required_maps_to_payment_problem():
    assert email_type_from_status(ShipmentStatus.PAYMENT_REQUIRED, is_invoice=False) == EmailType.PAYMENT_PROBLEM


# ── No-model path ─────────────────────────────────────────────────────────────


def test_no_model_uses_rule_status():
    r = _rules(status=ShipmentStatus.IN_TRANSIT, confidence=0.85, is_shipping=True)
    result = _reconcile(r, model=None)
    assert result.status == ShipmentStatus.IN_TRANSIT
    assert result.decision_source == DecisionSource.RULE
    assert result.classification_method == "rules_only"
    assert result.rule_model_agreed is None
    assert result.model_called is False


def test_no_model_no_status_is_non_relevant():
    r = _rules(status=None, confidence=0.0, is_shipping=False)
    result = _reconcile(r, model=None)
    assert result.is_relevant is False
    assert result.status == ShipmentStatus.UNKNOWN


# ── Agreement ─────────────────────────────────────────────────────────────────


def test_rule_model_agree_when_same_status():
    r = _rules(status=ShipmentStatus.DELIVERED, confidence=0.92, is_shipping=True)
    m = _model(
        email_type=EmailType.DELIVERED,
        status=ShipmentStatus.DELIVERED,
        confidence=0.88,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_AUDIT))
    assert result.decision_source == DecisionSource.RULE_MODEL_AGREE
    assert result.rule_model_agreed is True
    assert result.conflict_reason is None


def test_rule_wins_when_higher_confidence_and_agree():
    r = _rules(status=ShipmentStatus.IN_TRANSIT, confidence=0.90, is_shipping=True)
    m = _model(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        confidence=0.70,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_AUDIT))
    assert result.status == ShipmentStatus.IN_TRANSIT
    assert result.status_confidence == pytest.approx(0.90)


# ── Conflict detection ────────────────────────────────────────────────────────


def test_conflict_recorded_when_statuses_differ():
    r = _rules(status=ShipmentStatus.SHIPPED, confidence=0.75, is_shipping=True)
    m = _model(
        email_type=EmailType.ORDER_CONFIRMATION,
        status=ShipmentStatus.ORDER_CONFIRMED,
        confidence=0.80,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_REQUIRED))
    assert result.decision_source == DecisionSource.MODEL_FALLBACK
    assert result.rule_model_agreed is False
    assert result.needs_review is True
    assert result.conflict_reason is not None


def test_model_wins_conflict_when_higher_confidence():
    r = _rules(status=ShipmentStatus.SHIPPED, confidence=0.60, is_shipping=True)
    m = _model(
        email_type=EmailType.ORDER_CONFIRMATION,
        status=ShipmentStatus.ORDER_CONFIRMED,
        confidence=0.88,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_REQUIRED))
    assert result.status == ShipmentStatus.ORDER_CONFIRMED
    assert result.decision_source == DecisionSource.MODEL_FALLBACK


def test_rule_wins_conflict_when_higher_confidence():
    r = _rules(status=ShipmentStatus.OUT_FOR_DELIVERY, confidence=0.93, is_shipping=True)
    m = _model(
        email_type=EmailType.ORDER_CONFIRMATION,
        status=ShipmentStatus.ORDER_CONFIRMED,
        confidence=0.55,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_AUDIT))
    assert result.status == ShipmentStatus.OUT_FOR_DELIVERY
    assert result.decision_source == DecisionSource.RULE_OVERRIDE


# ── DELIVERED is terminal ─────────────────────────────────────────────────────


def test_delivered_is_terminal_model_cannot_override():
    r = _rules(status=ShipmentStatus.DELIVERED, confidence=0.95, is_shipping=True)
    m = _model(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        confidence=0.99,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_AUDIT))
    assert result.status == ShipmentStatus.DELIVERED


# ── Digital product / billing override ───────────────────────────────────────


def test_digital_product_is_not_relevant():
    r = _rules(status=None, confidence=0.0, is_shipping=False)
    m = _model(email_type=EmailType.DIGITAL_PRODUCT, status=ShipmentStatus.UNKNOWN, confidence=0.0)
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_REQUIRED))
    assert result.is_relevant is False
    assert result.email_type == EmailType.DIGITAL_PRODUCT
    assert result.ignore_reason == "digital_product"


def test_billing_only_is_not_relevant():
    r = _rules(status=None, confidence=0.0, is_invoice=True)
    m = _model(email_type=EmailType.BILLING_ONLY, status=ShipmentStatus.UNKNOWN, confidence=0.0)
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_REQUIRED))
    assert result.is_relevant is False
    assert result.ignore_reason == "billing_only"


# ── Identifier merging ────────────────────────────────────────────────────────


def test_model_tracking_merged_into_rule_candidates():
    r = _rules(
        status=ShipmentStatus.IN_TRANSIT,
        confidence=0.85,
        is_shipping=True,
        tracking=[TrackingIdentifier(value="1ZABCDE1234567890", confidence=0.95)],
    )
    m = _model(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        confidence=0.80,
        tracking=["NEW-TRK-999"],
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_AUDIT))
    values = [t.value for t in result.tracking_candidates]
    assert "1ZABCDE1234567890" in values
    assert "NEW-TRK-999" in values


def test_duplicate_tracking_not_added():
    r = _rules(
        status=ShipmentStatus.IN_TRANSIT,
        confidence=0.85,
        is_shipping=True,
        tracking=[TrackingIdentifier(value="ECSA1234567", confidence=0.95)],
    )
    m = _model(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        confidence=0.80,
        tracking=["ecsa1234567"],  # lowercase duplicate
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_AUDIT))
    assert len(result.tracking_candidates) == 1


# ── Observability fields ──────────────────────────────────────────────────────


def test_observability_fields_populated():
    r = _rules(status=ShipmentStatus.IN_TRANSIT, confidence=0.85, is_shipping=True)
    m = _model(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        confidence=0.80,
    )
    obs = ModelCallObservability(
        mode=ModelExecutionMode.MODEL_AUDIT,
        called=True,
        latency_ms=312.5,
        prompt_tokens=450,
        completion_tokens=80,
    )
    result = _reconcile(r, m, obs)
    assert result.model_called is True
    assert result.model_mode == "model_audit"
    assert result.model_latency_ms == pytest.approx(312.5)
    assert result.prompt_tokens == 450
    assert result.completion_tokens == 80
    assert result.confidence_delta == pytest.approx(0.05)


def test_confidence_delta_computed():
    r = _rules(status=ShipmentStatus.SHIPPED, confidence=0.80, is_shipping=True)
    m = _model(email_type=EmailType.SHIPPING_UPDATE, status=ShipmentStatus.SHIPPED, confidence=0.95)
    result = _reconcile(r, m, _obs(called=True))
    assert result.confidence_delta == pytest.approx(0.15)


# ── Evidence clipping ─────────────────────────────────────────────────────────


def test_evidence_clipped_to_max():
    long_evidence = "x" * 300
    r = _rules(status=ShipmentStatus.IN_TRANSIT, confidence=0.80, is_shipping=True, evidence=long_evidence)
    result = _reconcile(r, model=None)
    assert len(result.status_evidence) <= 240


# ── Explicit reconciliation cases ─────────────────────────────────────────────


def test_model_override_when_rules_missed_semantic_type():
    r = _rules(status=None, confidence=0.0, is_shipping=False)
    m = _model(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        confidence=0.92,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_REQUIRED))
    assert result.decision_source == DecisionSource.MODEL_OVERRIDE
    assert result.conflict_reason == "rules_missed_semantic_email_type"
    assert result.needs_review is False
    assert result.email_type == EmailType.SHIPPING_UPDATE
    assert result.status == ShipmentStatus.IN_TRANSIT


def test_rule_override_when_model_low_confidence():
    r = _rules(status=ShipmentStatus.IN_TRANSIT, confidence=0.93, is_shipping=True)
    m = _model(
        email_type=EmailType.ORDER_CONFIRMATION,
        status=ShipmentStatus.ORDER_CONFIRMED,
        confidence=0.55,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_AUDIT))
    assert result.decision_source == DecisionSource.RULE_OVERRIDE
    assert result.conflict_reason == "low_model_confidence"
    assert result.needs_review is False
    assert result.status == ShipmentStatus.IN_TRANSIT
    assert result.email_type == EmailType.SHIPPING_UPDATE


def test_semantic_guard_order_confirmation_no_shipping_evidence():
    r = _rules(status=ShipmentStatus.ORDER_CONFIRMED, confidence=0.75, is_shipping=True)
    m = _model(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        confidence=0.82,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_REQUIRED))
    assert result.decision_source == DecisionSource.SEMANTIC_GUARD
    assert result.email_type == EmailType.ORDER_CONFIRMATION
    assert result.conflict_reason == "model_inferred_shipping_without_shipping_evidence"
    assert result.needs_review is False
    assert result.status == ShipmentStatus.ORDER_CONFIRMED


def test_semantic_guard_bypassed_when_tracking_present():
    r = _rules(
        status=ShipmentStatus.ORDER_CONFIRMED,
        confidence=0.75,
        is_shipping=True,
        tracking=[TrackingIdentifier(value="1Z999AA10123456784", confidence=0.95)],
    )
    m = _model(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        confidence=0.82,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_REQUIRED))
    # Tracking present → shipping evidence exists → semantic guard does NOT fire
    assert result.decision_source != DecisionSource.SEMANTIC_GUARD


def test_model_fallback_ambiguous_conflict():
    r = _rules(status=ShipmentStatus.SHIPPED, confidence=0.75, is_shipping=True)
    m = _model(
        email_type=EmailType.ORDER_CONFIRMATION,
        status=ShipmentStatus.ORDER_CONFIRMED,
        confidence=0.80,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_REQUIRED))
    assert result.decision_source == DecisionSource.MODEL_FALLBACK
    assert result.needs_review is True
    assert result.status == ShipmentStatus.ORDER_CONFIRMED


def test_review_needed_when_both_low_confidence():
    r = _rules(status=ShipmentStatus.SHIPPED, confidence=0.40, is_shipping=True)
    m = _model(
        email_type=EmailType.ORDER_CONFIRMATION,
        status=ShipmentStatus.ORDER_CONFIRMED,
        confidence=0.35,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_REQUIRED))
    assert result.decision_source == DecisionSource.REVIEW_NEEDED
    assert result.needs_review is True


# ── _has_shipping_evidence helper ─────────────────────────────────────────────


def test_has_shipping_evidence_with_tracking():
    r = _rules(
        status=ShipmentStatus.ORDER_CONFIRMED,
        tracking=[TrackingIdentifier(value="TRACK123", confidence=0.9)],
    )
    assert _has_shipping_evidence(r, None) is True


def test_has_shipping_evidence_with_carrier_handoff_status():
    r = _rules(status=ShipmentStatus.IN_TRANSIT, confidence=0.8)
    assert _has_shipping_evidence(r, None) is True


def test_has_no_shipping_evidence_for_order_confirmed_only():
    r = _rules(status=ShipmentStatus.ORDER_CONFIRMED, confidence=0.75)
    assert _has_shipping_evidence(r, None) is False


# ── rule_confidence / model_confidence fields ─────────────────────────────────


def test_rule_confidence_and_model_confidence_populated():
    r = _rules(status=ShipmentStatus.IN_TRANSIT, confidence=0.85, is_shipping=True)
    m = _model(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        confidence=0.78,
    )
    result = _reconcile(r, m, _obs(called=True, mode=ModelExecutionMode.MODEL_AUDIT))
    assert result.rule_confidence == pytest.approx(0.85)
    assert result.model_confidence == pytest.approx(0.78)


def test_model_confidence_none_when_no_model():
    r = _rules(status=ShipmentStatus.IN_TRANSIT, confidence=0.85, is_shipping=True)
    result = _reconcile(r, model=None)
    assert result.rule_confidence == pytest.approx(0.85)
    assert result.model_confidence is None
