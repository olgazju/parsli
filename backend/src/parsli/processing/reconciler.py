"""ClassificationReconciler — merges rule and model outputs into a single result.

Rules and model outputs are kept separate until this step. The reconciler
makes the final decision and records every disagreement explicitly so conflicts
are visible for later inspection without losing either source's output.
"""

from enum import Enum

from pydantic import BaseModel

from ..config import PrivacyConfig
from ..domain.email_types import EmailType, email_type_from_status
from ..domain.identifiers import OrderIdentifier, TrackingIdentifier
from ..domain.statuses import ShipmentStatus
from ..model.base import ModelClassificationResult
from .cleaner import CleanedEmail
from .model_classifier import ModelCallObservability
from .rule_engine import RuleExtractionResult


class DecisionSource(str, Enum):
    RULE = "rule"
    MODEL = "model"
    RULE_MODEL_AGREE = "rule_model_agree"
    MODEL_OVERRIDE = "model_override"
    RULE_OVERRIDE = "rule_override"
    SEMANTIC_GUARD = "semantic_guard"
    REVIEW_NEEDED = "review_needed"
    MODEL_FALLBACK = "model_fallback"


class FinalClassificationResult(BaseModel):
    """Reconciled output from rules + optional model, ready for persistence.

    All raw per-source outputs are retained alongside the final decision so
    disagreements can be queried without re-running the pipeline.
    """

    # Identity
    email_id: str
    processing_version: str

    # Email type — coarse category (new concept, separate from ShipmentStatus)
    email_type: EmailType
    rule_email_type: EmailType
    model_email_type: EmailType | None

    # Shipment status — fine-grained, per source and final
    status: ShipmentStatus
    rule_status: ShipmentStatus | None
    model_status: ShipmentStatus | None
    status_confidence: float
    status_evidence: str

    # Per-source confidence for comparison and audit
    rule_confidence: float
    model_confidence: float | None

    # Identifiers — merged from both sources, deduped
    selected_tracking_number: str | None
    tracking_candidates: list[TrackingIdentifier]
    selected_order_number: str | None
    order_candidates: list[OrderIdentifier]

    # Extraction fields
    merchant: str | None
    carrier: str | None
    pickup_code: str | None
    amount: float | None
    currency: str | None

    # Relevance
    is_relevant: bool
    ignore_reason: str | None
    is_invoice: bool

    # Decision metadata
    decision_source: DecisionSource
    conflict_reason: str | None
    needs_review: bool

    # Observability
    model_called: bool
    model_mode: str
    model_latency_ms: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    rule_model_agreed: bool | None
    confidence_delta: float | None

    # Provenance
    model_provider: str | None
    model_name: str | None
    classification_method: str  # "rules_only" | "model_only" | "rules+model"


# Statuses that indicate carrier has physically taken custody of the parcel
_CARRIER_HANDOFF_STATUSES = frozenset({
    ShipmentStatus.SHIPPED,
    ShipmentStatus.RECEIVED_BY_CARRIER,
    ShipmentStatus.IN_TRANSIT,
    ShipmentStatus.OUT_FOR_DELIVERY,
})

_NON_PHYSICAL = (EmailType.DIGITAL_PRODUCT, EmailType.BILLING_ONLY)


class ClassificationReconciler:
    """Combines rule and model outputs into a FinalClassificationResult.

    The reconciler never mutates rule results or model results — it reads
    them, decides, and constructs a new result object.
    """

    def reconcile(
        self,
        rules: RuleExtractionResult,
        model: ModelClassificationResult | None,
        obs: ModelCallObservability,
        cleaned: CleanedEmail,
        email_id: str,
        processing_version: str,
        model_provider: str | None,
        model_name: str | None,
        privacy: PrivacyConfig,
    ) -> FinalClassificationResult:
        """Produce the final classification by reconciling rule and model outputs.

        Args:
            rules: Deterministic rule-engine output (authoritative first pass).
            model: Model classification result, or None if model was skipped.
            obs: Observability data from the model invocation attempt.
            cleaned: Cleaned email for shipping-shape signal.
            email_id: Email identifier passed through to the result.
            processing_version: Pipeline version string.
            model_provider: Provider name for provenance.
            model_name: Model name for provenance.
            privacy: PrivacyConfig for evidence clipping.

        Returns:
            A fully populated FinalClassificationResult.
        """
        rule_status = rules.status
        rule_email_type = email_type_from_status(rule_status, rules.is_invoice)
        rule_conf = rules.status_confidence

        model_status: ShipmentStatus | None = None
        model_email_type: EmailType | None = None
        model_conf: float = 0.0
        if model is not None:
            model_status = model.status if model.status != ShipmentStatus.UNKNOWN else None
            model_email_type = model.email_type
            model_conf = model.status_confidence

        # Starting values — rule wins by default
        method = "rules_only"
        final_status = rule_status or ShipmentStatus.UNKNOWN
        final_confidence = rule_conf
        final_evidence = rules.status_evidence
        final_email_type = rule_email_type

        conflict_reason: str | None = None
        rule_model_agreed: bool | None = None
        confidence_delta: float | None = None
        needs_review = False

        if model is None:
            decision_source = DecisionSource.RULE
        else:
            method = "rules+model"
            confidence_delta = abs(model_conf - rule_conf)

            types_agree = rule_email_type == model_email_type
            statuses_agree = (rule_status == model_status) or (
                rule_status is None and model_status is None
            )
            rule_model_agreed = types_agree and statuses_agree

            if types_agree and statuses_agree:
                # Complete agreement — use higher-confidence source for the status
                decision_source = DecisionSource.RULE_MODEL_AGREE
                if model_status and model_conf > rule_conf:
                    final_status = model_status
                    final_confidence = model_conf
                    final_evidence = model.status_evidence

            elif rule_status == ShipmentStatus.DELIVERED:
                # DELIVERED is terminal — rule always wins
                decision_source = DecisionSource.RULE_OVERRIDE
                conflict_reason = "delivered_is_terminal"

            elif model_email_type in _NON_PHYSICAL:
                # Non-physical email type always overrides rule output
                final_email_type = model_email_type
                decision_source = DecisionSource.MODEL_OVERRIDE
                conflict_reason = "non_physical_email_type"

            else:
                # Deterministic reconciliation for all remaining disagreements
                final_email_type, decision_source, conflict_reason, needs_review = (
                    _reconcile_email_type(
                        rule_email_type=rule_email_type,
                        model_email_type=model_email_type,
                        rule_conf=rule_conf,
                        model_conf=model_conf,
                        rules=rules,
                        model=model,
                    )
                )

                # Status selection follows the email_type decision winner
                if decision_source in (DecisionSource.MODEL_OVERRIDE, DecisionSource.MODEL_FALLBACK):
                    if model_status:
                        final_status = model_status
                        final_confidence = model_conf
                        final_evidence = model.status_evidence
                        if not rule_status:
                            method = "model_only"
                elif decision_source in (DecisionSource.RULE_MODEL_AGREE, DecisionSource.REVIEW_NEEDED):
                    if model_status and model_conf > rule_conf:
                        final_status = model_status
                        final_confidence = model_conf
                        final_evidence = model.status_evidence
                # RULE_OVERRIDE, SEMANTIC_GUARD → rule status already set

        # Digital-product and billing emails are never physical shipments
        non_physical = final_email_type in _NON_PHYSICAL
        if non_physical:
            is_relevant = False
            ignore_reason: str | None = final_email_type.value
        else:
            is_relevant = (
                (
                    rules.is_shipping_email
                    or (
                        model is not None
                        and model.email_type
                        not in (
                            EmailType.NON_SHIPPING,
                            EmailType.BILLING_ONLY,
                            EmailType.DIGITAL_PRODUCT,
                        )
                    )
                )
                and not rules.is_invoice
                and final_status != ShipmentStatus.UNKNOWN
            )
            ignore_reason = _derive_ignore_reason(rules, cleaned, model, is_relevant)

        # Clip evidence to configured max
        final_evidence = final_evidence[: privacy.evidence_max_chars]

        # Merge identifiers from both sources, deduped by uppercase value
        tracking_vals = list(rules.tracking_candidates)
        if model:
            seen = {t.value.upper() for t in tracking_vals}
            for val in model.tracking_numbers:
                if val.upper() not in seen:
                    tracking_vals.append(
                        TrackingIdentifier(value=val.upper(), confidence=0.7)
                    )

        order_vals = list(rules.order_candidates)
        if model:
            seen_o = {o.value.upper() for o in order_vals}
            for val in model.order_numbers:
                if val.upper() not in seen_o:
                    order_vals.append(OrderIdentifier(value=val.upper(), confidence=0.7))

        merchant = rules.merchant or (model.merchant if model else None)
        carrier = model.carrier if model else None
        pickup_code = rules.pickup_code or (model.pickup_code if model else None)
        amount = rules.amount or (model.amount if model else None)
        currency = rules.currency or (model.currency if model else None)

        return FinalClassificationResult(
            email_id=email_id,
            processing_version=processing_version,
            email_type=final_email_type,
            rule_email_type=rule_email_type,
            model_email_type=model_email_type,
            status=final_status,
            rule_status=rule_status,
            model_status=model_status,
            status_confidence=final_confidence,
            status_evidence=final_evidence,
            rule_confidence=rule_conf,
            model_confidence=model_conf if model is not None else None,
            selected_tracking_number=tracking_vals[0].value if tracking_vals else None,
            tracking_candidates=tracking_vals,
            selected_order_number=order_vals[0].value if order_vals else None,
            order_candidates=order_vals,
            merchant=merchant,
            carrier=carrier,
            pickup_code=pickup_code,
            amount=amount,
            currency=currency,
            is_relevant=is_relevant,
            ignore_reason=ignore_reason,
            is_invoice=rules.is_invoice,
            decision_source=decision_source,
            conflict_reason=conflict_reason,
            needs_review=needs_review,
            model_called=obs.called,
            model_mode=obs.mode.value,
            model_latency_ms=obs.latency_ms,
            prompt_tokens=obs.prompt_tokens,
            completion_tokens=obs.completion_tokens,
            rule_model_agreed=rule_model_agreed,
            confidence_delta=confidence_delta,
            model_provider=model_provider,
            model_name=model_name,
            classification_method=method,
        )


def _has_shipping_evidence(
    rules: RuleExtractionResult,
    model: ModelClassificationResult | None,
) -> bool:
    """Return True if any source provides physical shipping evidence."""
    if rules.tracking_candidates:
        return True
    if rules.status in _CARRIER_HANDOFF_STATUSES:
        return True
    if model and model.tracking_numbers:
        return True
    if model and model.carrier:
        return True
    return False


def _reconcile_email_type(
    rule_email_type: EmailType,
    model_email_type: EmailType | None,
    rule_conf: float,
    model_conf: float,
    rules: RuleExtractionResult,
    model: ModelClassificationResult | None,
) -> tuple[EmailType, DecisionSource, str | None, bool]:
    """Deterministic five-case reconciliation for email type disagreements.

    Returns:
        Tuple of (final_email_type, decision_source, conflict_reason, needs_review).
    """
    # Types agree — rule wins (higher-confidence status selected by caller)
    if model_email_type is None or rule_email_type == model_email_type:
        return rule_email_type, DecisionSource.RULE_MODEL_AGREE, None, False

    # Rule override — rule is very confident, model is not
    if rule_conf >= 0.9 and model_conf < 0.7:
        return rule_email_type, DecisionSource.RULE_OVERRIDE, "low_model_confidence", False

    # Semantic guard — prevent order_confirmation → shipping_update upgrade
    # without any physical shipping evidence
    if (
        rule_email_type == EmailType.ORDER_CONFIRMATION
        and model_email_type == EmailType.SHIPPING_UPDATE
        and not _has_shipping_evidence(rules, model)
    ):
        return (
            rule_email_type,
            DecisionSource.SEMANTIC_GUARD,
            "model_inferred_shipping_without_shipping_evidence",
            False,
        )

    # Model override — rules saw nothing meaningful, model is very confident
    if rule_email_type == EmailType.NON_SHIPPING and model_conf >= 0.9:
        return (
            model_email_type,
            DecisionSource.MODEL_OVERRIDE,
            "rules_missed_semantic_email_type",
            False,
        )

    # Review needed — both sources are too uncertain to trust
    if rule_conf < 0.5 and model_conf < 0.5:
        winner = rule_email_type if rule_conf >= model_conf else model_email_type
        return (
            winner,
            DecisionSource.REVIEW_NEEDED,
            f"low_confidence: rule={rule_conf:.2f} model={model_conf:.2f}",
            True,
        )

    # Model fallback — genuine ambiguous conflict, flag for review
    return (
        model_email_type,
        DecisionSource.MODEL_FALLBACK,
        f"conflict: rule={rule_email_type.value} model={model_email_type.value}",
        True,
    )


def _derive_ignore_reason(
    rules: RuleExtractionResult,
    cleaned: CleanedEmail,
    model: ModelClassificationResult | None,
    is_relevant: bool,
) -> str | None:
    if is_relevant:
        return None
    if rules.is_invoice:
        return "invoice"
    if not cleaned.is_shipping_shaped:
        return "not_shipping_shaped"
    if model and model.email_type == EmailType.NON_SHIPPING:
        return "non_shipping"
    return "no_status_matched"
