"""ModelClassifier — decides model execution mode and runs model classification.

Each email results in at most one model call. The mode (required vs audit)
determines which prompt is used and how much text is sent.
"""

import time
from enum import Enum

from pydantic import BaseModel

from ..config import ModelConfig
from ..domain.email_types import EmailType, email_type_from_status
from ..domain.statuses import ShipmentStatus
from ..model.base import (
    LocalModelClient,
    ModelAuditResult,
    ModelClassificationResult,
    ModelUnavailableError,
)
from ..model.prompts import (
    build_model_text_preview,
    format_audit_prompt,
    format_required_prompt,
)
from ..privacy.debug_store import DebugStore
from .cleaner import CleanedEmail
from .rule_engine import RuleExtractionResult


class ModelExecutionMode(str, Enum):
    MODEL_REQUIRED = "model_required"
    MODEL_AUDIT = "model_audit"
    SKIP_MODEL = "skip_model"


class ModelCallObservability(BaseModel):
    """Timing and token metadata for a single model invocation attempt."""

    mode: ModelExecutionMode
    called: bool
    prompt_type: str | None = None  # "required" | "audit" | None
    latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ModelClassifier:
    """Selects the model execution mode and runs model classification.

    Each call to classify() results in exactly one model call (or zero if
    the mode is SKIP_MODEL). The reconciler must use the returned result —
    it must never call the model again.

    Args:
        model_client: Configured local model client, or None (rules-only mode).
        model_provider: Provider name string for provenance tracking.
        model_name: Model name string for provenance tracking.
        model_config: ModelConfig with required_max_chars and audit_max_chars.
        debug_store: DebugStore for optional model output artifacts.
    """

    def __init__(
        self,
        model_client: LocalModelClient | None,
        model_provider: str | None,
        model_name: str | None,
        model_config: ModelConfig,
        debug_store: DebugStore,
    ) -> None:
        self._model = model_client
        self._model_provider = model_provider
        self._model_name = model_name
        self._required_max_chars = model_config.required_max_chars
        self._audit_max_chars = model_config.audit_max_chars
        self._debug = debug_store

    def select_mode(
        self,
        rules: RuleExtractionResult,
        cleaned: CleanedEmail,
        sender_trust_level: str | None = None,
    ) -> ModelExecutionMode:
        """Choose how (or whether) to invoke the model for this email.

        Args:
            rules: Output of the deterministic rule engine.
            cleaned: Cleaned email with shipping-shape signal.
            sender_trust_level: Optional trust level from ingestion metadata.

        Returns:
            SKIP_MODEL for obvious noise; MODEL_AUDIT for high-confidence rule
            results; MODEL_REQUIRED for everything ambiguous.
        """
        if self._model is None:
            return ModelExecutionMode.SKIP_MODEL

        if sender_trust_level == "blocked":
            return ModelExecutionMode.SKIP_MODEL
        if rules.is_invoice and not cleaned.is_shipping_shaped:
            return ModelExecutionMode.SKIP_MODEL

        if rules.is_shipping_email and rules.status_confidence >= 0.80:
            return ModelExecutionMode.MODEL_AUDIT

        return ModelExecutionMode.MODEL_REQUIRED

    def classify(
        self,
        cleaned: CleanedEmail,
        mode: ModelExecutionMode,
        rules: RuleExtractionResult | None = None,
    ) -> tuple[ModelClassificationResult | None, ModelCallObservability]:
        """Run model classification and return the result with observability data.

        Exactly one model call is made (or zero for SKIP_MODEL). The mode
        determines which prompt is used:
          MODEL_REQUIRED — full extraction prompt, up to required_max_chars text.
          MODEL_AUDIT    — lightweight agreement prompt, up to audit_max_chars text.
                           Requires rules to be provided for the rule context block.

        Args:
            cleaned: Cleaned email whose text will be sent to the model.
            mode: The execution mode selected by select_mode().
            rules: Rule-engine output, required when mode is MODEL_AUDIT.

        Returns:
            A tuple of (ModelClassificationResult or None, ModelCallObservability).
            Returns (None, obs) when the model is skipped or errors out.
        """
        if self._model is None or mode == ModelExecutionMode.SKIP_MODEL:
            return None, ModelCallObservability(mode=mode, called=False)

        if mode == ModelExecutionMode.MODEL_AUDIT:
            return self._classify_audit(cleaned, rules)
        return self._classify_required(cleaned)

    # ── private ────────────────────────────────────────────────────────────────

    def _classify_required(
        self,
        cleaned: CleanedEmail,
    ) -> tuple[ModelClassificationResult | None, ModelCallObservability]:
        preview = build_model_text_preview(cleaned.cleaned_text, self._required_max_chars)
        prompt = format_required_prompt(
            subject=cleaned.subject,
            sender_domain=cleaned.sender_domain,
            email_text=preview,
        )

        t0 = time.monotonic()
        try:
            result = self._model.extract(prompt, response_model=ModelClassificationResult)  # type: ignore[union-attr]
        except ModelUnavailableError:
            raise
        except Exception:
            latency_ms = (time.monotonic() - t0) * 1000
            return None, ModelCallObservability(
                mode=ModelExecutionMode.MODEL_REQUIRED,
                called=True,
                prompt_type="required",
                latency_ms=latency_ms,
            )

        latency_ms = (time.monotonic() - t0) * 1000
        usage: dict[str, int] = getattr(self._model, "last_usage", None) or {}
        self._debug.store_model_output(
            cleaned.email_id, self._model_provider or "unknown", result.model_dump()
        )
        return result, ModelCallObservability(
            mode=ModelExecutionMode.MODEL_REQUIRED,
            called=True,
            prompt_type="required",
            latency_ms=latency_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )

    def _classify_audit(
        self,
        cleaned: CleanedEmail,
        rules: RuleExtractionResult | None,
    ) -> tuple[ModelClassificationResult | None, ModelCallObservability]:
        if rules is None:
            # Fallback: no rule context available → use required mode instead
            return self._classify_required(cleaned)

        rule_email_type = email_type_from_status(rules.status, rules.is_invoice)
        preview = build_model_text_preview(cleaned.cleaned_text, self._audit_max_chars)
        prompt = format_audit_prompt(
            subject=cleaned.subject,
            sender_domain=cleaned.sender_domain,
            preview=preview,
            rule_email_type=rule_email_type.value,
            rule_status=rules.status.value if rules.status else "none",
            rule_confidence=rules.status_confidence,
            rule_evidence=rules.status_evidence,
            tracking_candidates=[t.value for t in rules.tracking_candidates],
            order_candidates=[o.value for o in rules.order_candidates],
        )

        t0 = time.monotonic()
        try:
            audit = self._model.extract(prompt, response_model=ModelAuditResult)  # type: ignore[union-attr]
        except ModelUnavailableError:
            raise
        except Exception:
            latency_ms = (time.monotonic() - t0) * 1000
            return None, ModelCallObservability(
                mode=ModelExecutionMode.MODEL_AUDIT,
                called=True,
                prompt_type="audit",
                latency_ms=latency_ms,
            )

        latency_ms = (time.monotonic() - t0) * 1000
        usage: dict[str, int] = getattr(self._model, "last_usage", None) or {}

        result = _audit_to_classification(audit, rule_email_type, rules)
        self._debug.store_model_output(
            cleaned.email_id, self._model_provider or "unknown", audit.model_dump()
        )
        return result, ModelCallObservability(
            mode=ModelExecutionMode.MODEL_AUDIT,
            called=True,
            prompt_type="audit",
            latency_ms=latency_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )


def _audit_to_classification(
    audit: ModelAuditResult,
    rule_email_type: EmailType,
    rules: RuleExtractionResult,
) -> ModelClassificationResult:
    """Convert a ModelAuditResult to the common ModelClassificationResult interface.

    When the model agrees with the rules, we reflect the rule values back so
    the reconciler can record agreement. When it disagrees, we use the
    model's corrected values.
    """
    if audit.agrees:
        return ModelClassificationResult(
            email_type=rule_email_type,
            status=rules.status or ShipmentStatus.UNKNOWN,
            status_confidence=audit.status_confidence,
            status_evidence="[audit: agrees with rules]",
        )
    return ModelClassificationResult(
        email_type=audit.email_type,
        status=audit.status,
        status_confidence=audit.status_confidence,
        status_evidence=f"[audit] {audit.reason or 'disagrees with rules'}",
        reasoning=audit.reason,
    )
