"""Tests for model classifier, prompt selection, and LM Studio client."""

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from parsli.config import ModelConfig, PrivacyConfig
from parsli.domain.email_types import EmailType
from parsli.domain.identifiers import TrackingIdentifier
from parsli.domain.statuses import ShipmentStatus
from parsli.model.base import ModelAuditResult, ModelClassificationResult
from parsli.model.lmstudio_client import LMStudioClient
from parsli.model.prompts import (
    build_model_text_preview,
    format_audit_prompt,
    format_required_prompt,
)
from parsli.processing.cleaner import CleanedEmail
from parsli.processing.model_classifier import (
    ModelCallObservability,
    ModelClassifier,
    ModelExecutionMode,
)
from parsli.processing.reconciler import ClassificationReconciler
from parsli.processing.rule_engine import RuleExtractionResult
from parsli.privacy.debug_store import DebugStore


# ── Helpers ────────────────────────────────────────────────────────────────────


def _model_config(**kwargs: object) -> ModelConfig:
    return ModelConfig(
        provider="lmstudio",
        model_name="test-model",
        required_max_chars=4000,
        audit_max_chars=1500,
        **kwargs,
    )


def _debug() -> DebugStore:
    return DebugStore(app_dir=Path("/tmp"), enabled=False)


def _cleaned(
    text: str = "Your package is on the way.",
    subject: str = "Order shipped",
    sender_domain: str | None = "amazon.com",
) -> CleanedEmail:
    return CleanedEmail(
        email_id="test-id",
        cleaned_text=text,
        cleaned_text_hash="abc",
        cleaned_full_len=len(text),
        is_shipping_shaped=True,
        subject=subject,
        sender_domain=sender_domain,
    )


def _rules(
    *,
    status: ShipmentStatus | None = ShipmentStatus.IN_TRANSIT,
    confidence: float = 0.85,
    is_shipping: bool = True,
    tracking: list[TrackingIdentifier] | None = None,
) -> RuleExtractionResult:
    return RuleExtractionResult(
        is_shipping_email=is_shipping,
        is_invoice=False,
        status=status,
        status_confidence=confidence,
        status_evidence="package is on the way",
        tracking_candidates=tracking or [],
        order_candidates=[],
        merchant=None,
        pickup_code=None,
        amount=None,
        currency=None,
    )


def _mock_client(return_value: object) -> MagicMock:
    client = MagicMock()
    client.extract.return_value = return_value
    client.last_usage = {"prompt_tokens": 100, "completion_tokens": 30}
    return client


def _classifier(mock_client: object) -> ModelClassifier:
    return ModelClassifier(
        model_client=mock_client,
        model_provider="lmstudio",
        model_name="test-model",
        model_config=_model_config(),
        debug_store=_debug(),
    )


# ── build_model_text_preview ──────────────────────────────────────────────────


def test_preview_clips_to_max_chars():
    text = "a" * 6000
    assert len(build_model_text_preview(text, max_chars=4000)) == 4000


def test_preview_does_not_clip_short_text():
    text = "hello world"
    assert build_model_text_preview(text, max_chars=4000) == text


def test_audit_preview_smaller_than_required_preview():
    text = "x" * 5000
    required = build_model_text_preview(text, max_chars=4000)
    audit = build_model_text_preview(text, max_chars=1500)
    assert len(audit) < len(required)


# ── format_required_prompt ────────────────────────────────────────────────────


def test_required_prompt_includes_subject_and_sender():
    prompt = format_required_prompt(
        subject="Your order shipped",
        sender_domain="amazon.com",
        email_text="Package on its way.",
    )
    assert "Your order shipped" in prompt
    assert "amazon.com" in prompt
    assert "Package on its way." in prompt


def test_required_prompt_includes_full_schema_fields():
    prompt = format_required_prompt("s", "d", "body")
    assert "email_type" in prompt
    assert "tracking_numbers" in prompt
    assert "carrier" in prompt
    assert "reasoning" in prompt


# ── format_audit_prompt ───────────────────────────────────────────────────────


def test_audit_prompt_includes_rule_context():
    prompt = format_audit_prompt(
        subject="Order shipped",
        sender_domain="amazon.com",
        preview="short preview",
        rule_email_type="shipping_update",
        rule_status="in_transit",
        rule_confidence=0.88,
        rule_evidence="package is on the way",
        tracking_candidates=["1ZTRACK123"],
        order_candidates=["ORD-456"],
    )
    assert "shipping_update" in prompt
    assert "in_transit" in prompt
    assert "0.88" in prompt
    assert "1ZTRACK123" in prompt
    assert "ORD-456" in prompt
    assert "Order shipped" in prompt
    assert "amazon.com" in prompt


def test_audit_prompt_contains_preview_not_full_body():
    long_body = "z" * 5000
    preview = build_model_text_preview(long_body, max_chars=1500)
    prompt = format_audit_prompt(
        subject="s",
        sender_domain="d",
        preview=preview,
        rule_email_type="shipping_update",
        rule_status="in_transit",
        rule_confidence=0.85,
        rule_evidence="",
        tracking_candidates=[],
        order_candidates=[],
    )
    # The full body should not appear in the audit prompt
    assert long_body not in prompt
    assert len(prompt) < len(long_body)


def test_audit_prompt_asks_for_agreement():
    prompt = format_audit_prompt("s", "d", "preview", "shipping_update", "in_transit",
                                 0.85, "", [], [])
    assert "agrees" in prompt


# ── ModelClassifier.classify — prompt_type in observability ──────────────────


def test_required_mode_uses_required_prompt():
    full_result = ModelClassificationResult(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        status_confidence=0.90,
    )
    mock = _mock_client(full_result)
    clf = _classifier(mock)

    _, obs = clf.classify(_cleaned(), ModelExecutionMode.MODEL_REQUIRED, rules=_rules())

    assert obs.prompt_type == "required"
    assert obs.called is True
    mock.extract.assert_called_once()
    # Confirm it was called with ModelClassificationResult, not ModelAuditResult
    _, kwargs = mock.extract.call_args
    assert kwargs["response_model"] is ModelClassificationResult


def test_audit_mode_uses_audit_prompt():
    audit_result = ModelAuditResult(
        agrees=True,
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        status_confidence=0.88,
    )
    mock = _mock_client(audit_result)
    clf = _classifier(mock)

    _, obs = clf.classify(_cleaned(), ModelExecutionMode.MODEL_AUDIT, rules=_rules())

    assert obs.prompt_type == "audit"
    assert obs.called is True
    mock.extract.assert_called_once()
    _, kwargs = mock.extract.call_args
    assert kwargs["response_model"] is ModelAuditResult


def test_skip_mode_makes_zero_calls():
    mock = _mock_client(None)
    clf = _classifier(mock)

    result, obs = clf.classify(_cleaned(), ModelExecutionMode.SKIP_MODEL)

    assert result is None
    assert obs.called is False
    assert obs.prompt_type is None
    mock.extract.assert_not_called()


def test_none_client_makes_zero_calls():
    clf = ModelClassifier(
        model_client=None,
        model_provider=None,
        model_name=None,
        model_config=_model_config(),
        debug_store=_debug(),
    )
    result, obs = clf.classify(_cleaned(), ModelExecutionMode.MODEL_REQUIRED)
    assert result is None
    assert obs.called is False


# ── Exactly one call per email ────────────────────────────────────────────────


def test_classify_makes_exactly_one_call_for_required():
    mock = _mock_client(ModelClassificationResult(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        status_confidence=0.85,
    ))
    clf = _classifier(mock)

    clf.classify(_cleaned(), ModelExecutionMode.MODEL_REQUIRED, rules=_rules())
    assert mock.extract.call_count == 1


def test_classify_makes_exactly_one_call_for_audit():
    mock = _mock_client(ModelAuditResult(
        agrees=True,
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        status_confidence=0.88,
    ))
    clf = _classifier(mock)

    clf.classify(_cleaned(), ModelExecutionMode.MODEL_AUDIT, rules=_rules())
    assert mock.extract.call_count == 1


def test_reconciliation_does_not_call_model():
    """The reconciler must use the already-returned model_result, never call the model."""
    full_result = ModelClassificationResult(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        status_confidence=0.85,
    )
    mock = _mock_client(full_result)
    clf = _classifier(mock)
    reconciler = ClassificationReconciler()

    from parsli.processing.model_classifier import ModelCallObservability as Obs
    from parsli.processing.cleaner import CleanedEmail

    cleaned = _cleaned()
    rules = _rules()
    model_result, obs = clf.classify(cleaned, ModelExecutionMode.MODEL_REQUIRED, rules=rules)

    call_count_before = mock.extract.call_count

    reconciler.reconcile(
        rules=rules,
        model=model_result,
        obs=obs,
        cleaned=cleaned,
        email_id="test-id",
        processing_version="rules:v1;prompt:v2",
        model_provider="lmstudio",
        model_name="test-model",
        privacy=PrivacyConfig(),
    )

    assert mock.extract.call_count == call_count_before  # reconciler made no extra calls


# ── Audit result conversion ───────────────────────────────────────────────────


def test_audit_agrees_reflects_rule_values():
    audit_result = ModelAuditResult(
        agrees=True,
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        status_confidence=0.92,
    )
    mock = _mock_client(audit_result)
    clf = _classifier(mock)
    rules = _rules(status=ShipmentStatus.IN_TRANSIT, confidence=0.88)

    result, _ = clf.classify(_cleaned(), ModelExecutionMode.MODEL_AUDIT, rules=rules)

    assert result is not None
    assert result.email_type == EmailType.SHIPPING_UPDATE
    assert result.status == ShipmentStatus.IN_TRANSIT
    assert "[audit: agrees" in result.status_evidence


def test_audit_disagrees_uses_corrected_values():
    audit_result = ModelAuditResult(
        agrees=False,
        email_type=EmailType.ORDER_CONFIRMATION,
        status=ShipmentStatus.ORDER_CONFIRMED,
        status_confidence=0.80,
        reason="Email is an order confirmation, not a shipping update",
    )
    mock = _mock_client(audit_result)
    clf = _classifier(mock)

    result, _ = clf.classify(_cleaned(), ModelExecutionMode.MODEL_AUDIT, rules=_rules())

    assert result is not None
    assert result.email_type == EmailType.ORDER_CONFIRMATION
    assert result.status == ShipmentStatus.ORDER_CONFIRMED
    assert "disagrees" not in result.status_evidence or "audit" in result.status_evidence
    assert result.reasoning == "Email is an order confirmation, not a shipping update"


# ── LMStudioClient — persistent httpx.Client ──────────────────────────────────


def test_lmstudio_creates_persistent_http_client():
    config = ModelConfig(provider="lmstudio", model_name="test")
    client = LMStudioClient(config)
    assert hasattr(client, "_client")
    assert isinstance(client._client, httpx.Client)
    client.close()


def test_lmstudio_close_does_not_raise():
    config = ModelConfig(provider="lmstudio", model_name="test")
    client = LMStudioClient(config)
    client.close()  # must not raise


def test_lmstudio_context_manager_closes_on_exit():
    config = ModelConfig(provider="lmstudio", model_name="test")
    with LMStudioClient(config) as client:
        assert isinstance(client._client, httpx.Client)
    # After __exit__, the underlying client should be closed
    assert client._client.is_closed


def test_llamacpp_creates_persistent_http_client():
    from parsli.model.llamacpp_client import LlamaCppClient
    config = ModelConfig(provider="llamacpp", model_name="test")
    client = LlamaCppClient(config)
    assert hasattr(client, "_client")
    assert isinstance(client._client, httpx.Client)
    client.close()


# ── Observability fields populated ────────────────────────────────────────────


def test_observability_includes_token_counts():
    mock = _mock_client(ModelClassificationResult(
        email_type=EmailType.SHIPPING_UPDATE,
        status=ShipmentStatus.IN_TRANSIT,
        status_confidence=0.85,
    ))
    mock.last_usage = {"prompt_tokens": 450, "completion_tokens": 80}
    clf = _classifier(mock)

    _, obs = clf.classify(_cleaned(), ModelExecutionMode.MODEL_REQUIRED, rules=_rules())

    assert obs.prompt_tokens == 450
    assert obs.completion_tokens == 80
    assert obs.latency_ms is not None
    assert obs.latency_ms >= 0


def test_observability_includes_prompt_type_for_audit():
    mock = _mock_client(ModelAuditResult(agrees=True, status_confidence=0.90))
    clf = _classifier(mock)

    _, obs = clf.classify(_cleaned(), ModelExecutionMode.MODEL_AUDIT, rules=_rules())
    assert obs.prompt_type == "audit"
