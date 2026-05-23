"""EmailProcessingService — processes new and existing email messages."""

import logging

from sqlalchemy.orm import Session

from ..config import AppConfig
from ..db.repositories import (
    EmailExtractionRepository,
    EmailMessageRepository,
    ProcessedEmailRepository,
)
from ..gmail.client import GmailClient
from ..privacy.sanitizer import extract_sender_domain
from ..model.factory import ModelClientFactory
from ..privacy.debug_store import DebugStore
from ..processing.cleaner import EmailCleaner
from ..processing.extraction_orchestrator import ExtractionOrchestrator, FinalExtraction
from ..processing.pipeline import EmailProcessingPipeline
from ..processing.rule_engine import RuleEngine

logger = logging.getLogger(__name__)


class EmailProcessingService:
    """Coordinates the extraction pipeline over a batch of email messages.

    Args:
        session: SQLAlchemy session (caller manages commit/rollback).
        gmail_client: Authenticated GmailClient used to fetch raw bodies.
        config: AppConfig driving privacy and processing settings.
    """

    def __init__(
        self,
        session: Session,
        gmail_client: GmailClient,
        config: AppConfig,
    ) -> None:
        self._session = session
        self._gmail = gmail_client
        self._config = config

        debug_store = DebugStore(
            app_dir=config.app_dir,
            enabled=config.privacy.debug_store_email_artifacts,
        )

        model_client = None
        model_name = None
        if config.model.model_name:
            try:
                model_client = ModelClientFactory.create(config.model)
                model_name = config.model.model_name
            except Exception as exc:
                logger.warning("Could not initialise model client: %s", exc)

        processed_repo = ProcessedEmailRepository(session)
        extraction_repo = EmailExtractionRepository(session)

        orchestrator = ExtractionOrchestrator(
            processed_repo=processed_repo,
            extraction_repo=extraction_repo,
            model_client=model_client,
            model_config_name=config.model.provider,
            model_name=model_name,
            privacy=config.privacy,
            processing=config.processing,
            debug_store=debug_store,
        )

        self._pipeline = EmailProcessingPipeline(
            cleaner=EmailCleaner(),
            rule_engine=RuleEngine(),
            orchestrator=orchestrator,
            debug_store=debug_store,
        )
        self._msg_repo = EmailMessageRepository(session)

    def process_new_emails(self) -> list[FinalExtraction]:
        """Process all emails not yet processed at the current version."""
        version = self._config.processing.processing_version()
        batch_size = self._config.processing.incremental_batch_size
        ids = self._msg_repo.get_unprocessed_ids(version, batch_size)
        return [self._process_one(email_id) for email_id in ids]

    def reprocess_email(self, email_id: str) -> FinalExtraction | None:
        """Re-run the pipeline for a single email regardless of prior version."""
        msg = self._msg_repo.get(email_id)
        if msg is None:
            logger.warning("reprocess_email: %s not found in email_messages", email_id)
            return None
        return self._process_one(email_id)

    def _process_one(self, email_id: str) -> FinalExtraction:
        raw = self._gmail.fetch_raw(email_id)
        body = self._gmail.extract_body(raw.get("payload", {}))
        headers = self._gmail.extract_headers(raw)
        sender_domain = extract_sender_domain(headers.get("From", ""))
        subject = headers.get("Subject", "")
        result = self._pipeline.process(
            email_id, body, sender_domain=sender_domain, subject=subject
        )
        logger.debug(
            "Processed %s → status=%s relevant=%s",
            email_id,
            result.status.value,
            result.is_relevant,
        )
        return result
