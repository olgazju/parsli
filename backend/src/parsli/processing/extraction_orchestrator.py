"""ExtractionOrchestrator — thin coordinator that wires ModelClassifier → ClassificationReconciler.

The orchestrator never makes merge decisions about shipment identity (that is
ShipmentResolutionService's job) and never implements reconciliation logic
itself (that is ClassificationReconciler's job). It owns only the top-level
call sequence and persistence.
"""

import json

from ..config import ModelConfig, PrivacyConfig, ProcessingConfig
from ..db.models import EmailExtraction, ProcessedEmail
from ..db.repositories import EmailExtractionRepository, ProcessedEmailRepository
from ..model.base import LocalModelClient
from ..privacy.debug_store import DebugStore
from .cleaner import CleanedEmail
from .model_classifier import ModelClassifier, ModelExecutionMode
from .reconciler import ClassificationReconciler, FinalClassificationResult
from .rule_engine import RuleExtractionResult

# Public re-export so existing callers (pipeline, services) need no change.
FinalExtraction = FinalClassificationResult


class ExtractionOrchestrator:
    """Coordinates rule results → model classifier → reconciler → persistence.

    Args:
        processed_repo: Repository for processed_emails table.
        extraction_repo: Repository for email_extractions table.
        model_client: Local model client (may be None to run rules-only).
        model_config_name: Provider name string for provenance tracking.
        model_name: Model name string for provenance tracking.
        model_config: ModelConfig with required_max_chars and audit_max_chars.
        privacy: PrivacyConfig controlling evidence clipping.
        processing: ProcessingConfig for version stamps.
        debug_store: DebugStore for optional model output artifacts.
    """

    def __init__(
        self,
        processed_repo: ProcessedEmailRepository,
        extraction_repo: EmailExtractionRepository,
        model_client: LocalModelClient | None,
        model_config_name: str | None,
        model_name: str | None,
        model_config: ModelConfig,
        privacy: PrivacyConfig,
        processing: ProcessingConfig,
        debug_store: DebugStore,
    ) -> None:
        self._processed_repo = processed_repo
        self._extraction_repo = extraction_repo
        self._model_provider = model_config_name
        self._model_name = model_name
        self._privacy = privacy
        self._processing = processing

        self._classifier = ModelClassifier(
            model_client=model_client,
            model_provider=model_config_name,
            model_name=model_name,
            model_config=model_config,
            debug_store=debug_store,
        )
        self._reconciler = ClassificationReconciler()

    def orchestrate(
        self,
        cleaned: CleanedEmail,
        rules: RuleExtractionResult,
        sender_trust_level: str | None = None,
    ) -> FinalClassificationResult:
        """Produce a FinalClassificationResult from cleaned email + rule results.

        Args:
            cleaned: Cleaned email DTO from EmailCleaner.
            rules: Extraction result from RuleEngine.
            sender_trust_level: Optional trust level from email_messages metadata.

        Returns:
            A fully reconciled FinalClassificationResult, already persisted.
        """
        version = self._processing.processing_version()

        mode = self._classifier.select_mode(rules, cleaned, sender_trust_level)
        model_result, obs = self._classifier.classify(cleaned, mode, rules=rules)

        final = self._reconciler.reconcile(
            rules=rules,
            model=model_result,
            obs=obs,
            cleaned=cleaned,
            email_id=cleaned.email_id,
            processing_version=version,
            model_provider=self._model_provider,
            model_name=self._model_name,
            privacy=self._privacy,
        )

        self._persist(cleaned, final, version)
        return final

    def _persist(
        self,
        cleaned: CleanedEmail,
        final: FinalClassificationResult,
        version: str,
    ) -> None:
        processed = ProcessedEmail(
            email_id=cleaned.email_id,
            processing_version=version,
            cleaned_text_hash=cleaned.cleaned_text_hash,
            model_input_len=min(len(cleaned.cleaned_text), 1500),
            cleaned_full_len=cleaned.cleaned_full_len,
            classification_method=final.classification_method,
            is_shipping_shaped=cleaned.is_shipping_shaped,
            is_relevant=final.is_relevant,
            ignore_reason=final.ignore_reason,
            model_mode=final.model_mode,
        )
        self._processed_repo.upsert(processed)

        extraction = EmailExtraction(
            email_id=cleaned.email_id,
            processing_version=version,
            email_type=final.email_type.value,
            status=final.status.value,
            rule_status=final.rule_status.value if final.rule_status else None,
            model_status=final.model_status.value if final.model_status else None,
            status_confidence=final.status_confidence,
            status_evidence=final.status_evidence,
            merchant=final.merchant,
            carrier=final.carrier,
            selected_tracking_number=final.selected_tracking_number,
            tracking_candidates_json=json.dumps(
                [t.model_dump() for t in final.tracking_candidates]
            ),
            selected_order_number=final.selected_order_number,
            order_candidates_json=json.dumps(
                [o.model_dump() for o in final.order_candidates]
            ),
            pickup_code=final.pickup_code,
            amount=final.amount,
            currency=final.currency,
            decision_source=final.decision_source.value,
            conflict_reason=final.conflict_reason,
            model_provider=final.model_provider,
            model_name=final.model_name,
            model_mode=final.model_mode,
            model_latency_ms=final.model_latency_ms,
            prompt_tokens=final.prompt_tokens,
            completion_tokens=final.completion_tokens,
            rule_model_agreed=final.rule_model_agreed,
            confidence_delta=final.confidence_delta,
            needs_review=final.needs_review,
            prompt_version=self._processing.prompt_version,
            rules_version=self._processing.rules_version,
            extraction_error=None,
        )
        self._extraction_repo.upsert(extraction)
