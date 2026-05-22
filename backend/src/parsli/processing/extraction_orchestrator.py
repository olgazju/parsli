"""ExtractionOrchestrator — merges rule and model outputs into a FinalExtraction.

The orchestrator never makes merge decisions about shipment identity — that is
handled by ShipmentResolutionService. It only decides the best status and
identifiers for a single email.
"""

import json

from pydantic import BaseModel

from ..config import PrivacyConfig, ProcessingConfig
from ..db.models import EmailExtraction, ProcessedEmail
from ..db.repositories import EmailExtractionRepository, ProcessedEmailRepository
from ..domain.identifiers import OrderIdentifier, TrackingIdentifier
from ..domain.statuses import ShipmentStatus
from ..model.base import LocalModelClient, ModelExtractionResult
from ..model.prompts import format_prompt
from ..privacy.debug_store import DebugStore
from ..privacy.sanitizer import clip_text
from .cleaner import CleanedEmail
from .rule_engine import RuleExtractionResult


class FinalExtraction(BaseModel):
    email_id: str
    processing_version: str
    is_relevant: bool
    ignore_reason: str | None
    is_invoice: bool
    status: ShipmentStatus
    status_confidence: float
    status_evidence: str
    merchant: str | None
    selected_tracking_number: str | None
    tracking_candidates: list[TrackingIdentifier]
    selected_order_number: str | None
    order_candidates: list[OrderIdentifier]
    pickup_code: str | None
    amount: float | None
    currency: str | None
    model_provider: str | None
    model_name: str | None
    classification_method: str  # "rules_only" | "model_only" | "rules+model"


class ExtractionOrchestrator:
    """Combines rule-engine and model outputs into a single FinalExtraction.

    Args:
        processed_repo: Repository for processed_emails table.
        extraction_repo: Repository for email_extractions table.
        model_client: Local model client (may be None to run rules-only).
        model_config_name: Provider name string for provenance tracking.
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
        privacy: PrivacyConfig,
        processing: ProcessingConfig,
        debug_store: DebugStore,
    ) -> None:
        self._processed_repo = processed_repo
        self._extraction_repo = extraction_repo
        self._model = model_client
        self._model_provider = model_config_name
        self._model_name = model_name
        self._privacy = privacy
        self._processing = processing
        self._debug = debug_store

    def orchestrate(
        self,
        cleaned: CleanedEmail,
        rules: RuleExtractionResult,
    ) -> FinalExtraction:
        """Produce a FinalExtraction from cleaned email + rule results.

        Optionally calls the local model when rules are inconclusive or the
        email is shipping-shaped but no status was matched.
        """
        version = self._processing.processing_version()
        model_result: ModelExtractionResult | None = None
        method = "rules_only"

        should_call_model = (
            self._model is not None
            and cleaned.is_shipping_shaped
            and not rules.is_invoice
            and (rules.status is None or rules.status_confidence < 0.80)
        )

        if should_call_model and self._model is not None:
            clipped = clip_text(cleaned.cleaned_text, self._processing.rules_version and 1500)
            # Use the configured max_input_chars if we can access it; otherwise 1500 chars
            clipped = cleaned.cleaned_text[:1500]
            prompt = format_prompt(clipped, version=self._processing.prompt_version)
            try:
                model_result = self._model.extract(prompt, response_model=ModelExtractionResult)
                self._debug.store_model_output(
                    cleaned.email_id,
                    self._model_provider or "unknown",
                    model_result.model_dump(),
                )
                method = "rules+model"
            except Exception as exc:
                model_result = None
                method = "rules_only"

        final = self._merge(cleaned, rules, model_result, method)

        self._persist(cleaned, rules, final, version)
        return final

    def _merge(
        self,
        cleaned: CleanedEmail,
        rules: RuleExtractionResult,
        model: ModelExtractionResult | None,
        method: str,
    ) -> FinalExtraction:
        # Status: prefer higher-confidence source
        status = rules.status or ShipmentStatus.UNKNOWN
        confidence = rules.status_confidence
        evidence = rules.status_evidence

        if model is not None and model.status != ShipmentStatus.UNKNOWN:
            if model.status_confidence > confidence:
                status = model.status
                confidence = model.status_confidence
                evidence = model.status_evidence
                method = "rules+model" if rules.status else "model_only"

        # Clip evidence to configured max
        max_ev = self._privacy.evidence_max_chars
        evidence = evidence[:max_ev] if len(evidence) > max_ev else evidence

        # Identifiers: merge from both sources
        tracking_vals: list[TrackingIdentifier] = list(rules.tracking_candidates)
        if model:
            seen = {t.value.upper() for t in tracking_vals}
            for val in model.tracking_numbers:
                if val.upper() not in seen:
                    tracking_vals.append(TrackingIdentifier(value=val.upper(), confidence=0.7))

        order_vals: list[OrderIdentifier] = list(rules.order_candidates)
        if model:
            seen_o = {o.value.upper() for o in order_vals}
            for val in model.order_numbers:
                if val.upper() not in seen_o:
                    order_vals.append(OrderIdentifier(value=val.upper(), confidence=0.7))

        merchant = rules.merchant or (model.merchant if model else None)
        pickup_code = rules.pickup_code or (model.pickup_code if model else None)
        amount = rules.amount or (model.amount if model else None)
        currency = rules.currency or (model.currency if model else None)

        is_relevant = (
            (rules.is_shipping_email or (model.is_relevant if model else False))
            and not rules.is_invoice
            and status != ShipmentStatus.UNKNOWN
        )
        ignore_reason: str | None = None
        if not is_relevant:
            if rules.is_invoice:
                ignore_reason = "invoice"
            elif not cleaned.is_shipping_shaped:
                ignore_reason = "not_shipping_shaped"
            elif model and not model.is_relevant and model.ignore_reason:
                ignore_reason = model.ignore_reason
            else:
                ignore_reason = "no_status_matched"

        return FinalExtraction(
            email_id=cleaned.email_id,
            processing_version=self._processing.processing_version(),
            is_relevant=is_relevant,
            ignore_reason=ignore_reason,
            is_invoice=rules.is_invoice,
            status=status,
            status_confidence=confidence,
            status_evidence=evidence,
            merchant=merchant,
            selected_tracking_number=tracking_vals[0].value if tracking_vals else None,
            tracking_candidates=tracking_vals,
            selected_order_number=order_vals[0].value if order_vals else None,
            order_candidates=order_vals,
            pickup_code=pickup_code,
            amount=amount,
            currency=currency,
            model_provider=self._model_provider,
            model_name=self._model_name,
            classification_method=method,
        )

    def _persist(
        self,
        cleaned: CleanedEmail,
        rules: RuleExtractionResult,
        final: FinalExtraction,
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
        )
        self._processed_repo.upsert(processed)

        extraction = EmailExtraction(
            email_id=cleaned.email_id,
            processing_version=version,
            status=final.status.value,
            status_confidence=final.status_confidence,
            status_evidence=final.status_evidence,
            merchant=final.merchant,
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
            model_provider=final.model_provider,
            model_name=final.model_name,
            prompt_version=self._processing.prompt_version,
            rules_version=self._processing.rules_version,
            extraction_error=None,
        )
        self._extraction_repo.upsert(extraction)
