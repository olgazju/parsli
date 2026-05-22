"""SyncService — orchestrates initial and incremental Gmail syncs.

Sync lifecycle:
1. initial_sync: fetches message IDs via keyword query for lookback_days,
   ingests all new message rows, processes unprocessed emails, resolves shipments.
2. incremental_sync: uses Gmail History API from last_history_id to find new
   messages only, then runs the same ingest → process → resolve chain.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from ..config import AppConfig
from ..db.models import Base
from ..db.repositories import (
    EmailAccountRepository,
    EmailMessageRepository,
    GmailSyncStateRepository,
)
from ..db.session import make_engine, make_session_factory
from ..gmail.auth import GmailOAuthManager, TokenMissingError
from ..gmail.client import GmailClient
from ..gmail.candidate_fetcher import GmailCandidateFetcher
from ..gmail.ingestor import GmailIngestor
from ..gmail.query_builder import GmailQueryBuilder
from ..gmail.sender_trust import SenderTrustScorer
from ..privacy.debug_store import DebugStore
from ..privacy.hashing import sha256_hex
from .candidate_observability_service import persist_fetch_result
from .domain_preference_service import DomainPreferenceService
from .email_processing_service import EmailProcessingService
from .shipment_resolution_service import ShipmentResolutionService

logger = logging.getLogger(__name__)


class SyncService:
    """Top-level sync coordinator for one Gmail account.

    Args:
        config: AppConfig.
        oauth_manager: GmailOAuthManager for loading/refreshing tokens.
        session_factory: SQLAlchemy sessionmaker.
    """

    def __init__(
        self,
        config: AppConfig,
        oauth_manager: GmailOAuthManager,
        session_factory: sessionmaker[Session],
    ) -> None:
        self._config = config
        self._oauth = oauth_manager
        self._session_factory = session_factory

    @classmethod
    def from_config(cls, config: AppConfig) -> "SyncService":
        """Convenience factory that creates engine, schema, and OAuth manager."""
        engine = make_engine(config.database.sqlite_path)
        Base.metadata.create_all(engine)
        session_factory = make_session_factory(engine)
        oauth = GmailOAuthManager(
            credentials_path=config.credentials_path,
            tokens_dir=config.tokens_dir,
        )
        return cls(config, oauth, session_factory)

    def initial_sync(self, account_id_str: str) -> dict:
        """Full lookback sync for a given account (identified by its UUID string).

        Raises:
            TokenMissingError: If no valid token exists (caller should trigger OAuth).
        """
        creds = self._oauth.refresh_if_needed(account_id_str)

        client = GmailClient(creds)

        with self._session_factory() as session:
            domain_svc = DomainPreferenceService(session)
            domain_prefs = domain_svc.get_preferences()

            # Auto-exclude the account's own email so self-sent messages are
            # never returned by Gmail queries.
            account_email = client.get_account_email()
            if account_email and account_email not in domain_prefs.exclude_senders:
                domain_svc.add_exclude_sender(account_email)
                domain_prefs = domain_svc.get_preferences()
                session.commit()
                logger.info("Auto-added %s to exclude_senders", account_email)

        fetcher = GmailCandidateFetcher(
            client=client,
            builder=GmailQueryBuilder(self._config.gmail, domain_prefs),
        )
        candidates = fetcher.fetch()
        logger.info(
            "initial_sync: %d candidate messages for account %s",
            len(candidates.message_ids),
            account_id_str,
        )

        with self._session_factory() as session:
            account_repo = EmailAccountRepository(session)
            email_hash = sha256_hex(account_id_str)
            account = account_repo.find_by_hash(email_hash)
            if account is None:
                account = account_repo.create(email_hash)
            db_account_id = account.id

            debug_store = DebugStore(
                app_dir=self._config.app_dir,
                enabled=self._config.privacy.debug_store_email_artifacts,
            )
            msg_repo = EmailMessageRepository(session)
            ingestor = GmailIngestor(
                client=client,
                repo=msg_repo,
                account_id=db_account_id,
                debug_store=debug_store,
                store_subject_debug=self._config.privacy.debug_store_email_artifacts,
                trust_scorer=SenderTrustScorer(
                    user_blocklist=frozenset(domain_prefs.blocklist)
                ),
            )
            results = ingestor.ingest_from_candidates(candidates)
            new_count = sum(1 for r in results if r.was_new)

            persist_fetch_result(session, candidates)

            sync_repo = GmailSyncStateRepository(session)
            history_id = client.get_history_id()
            sync_repo.upsert(
                db_account_id,
                last_history_id=history_id,
                last_successful_sync_at=datetime.now(timezone.utc),
                initial_sync_completed=True,
                lookback_days=self._config.gmail.lookback_days,
            )
            session.commit()

        processed = self._process_and_resolve(account_id_str, client)
        return {
            "total_fetched": len(candidates.message_ids),
            "new_ingested": new_count,
            "processed": len(processed),
        }

    def incremental_sync(self, account_id_str: str) -> dict:
        """Fetch only messages added since last_history_id.

        Raises:
            TokenMissingError: If no valid token exists (caller should trigger OAuth).
        """
        creds = self._oauth.refresh_if_needed(account_id_str)

        client = GmailClient(creds)

        with self._session_factory() as session:
            account_repo = EmailAccountRepository(session)
            email_hash = sha256_hex(account_id_str)
            account = account_repo.find_by_hash(email_hash)
            if account is None:
                raise ValueError(f"Account {account_id_str} not found — run initial_sync first")

            sync_repo = GmailSyncStateRepository(session)
            state = sync_repo.get(account.id)
            if state is None or not state.initial_sync_completed:
                raise ValueError("initial_sync has not completed for this account")

            start_history_id = state.last_history_id
            if start_history_id is None:
                raise ValueError("No history ID stored — run initial_sync first")

            new_ids, new_history_id = client.get_history(start_history_id)
            logger.info("incremental_sync: %d new messages", len(new_ids))

            incr_domain_prefs = DomainPreferenceService(session).get_preferences()
            debug_store = DebugStore(
                app_dir=self._config.app_dir,
                enabled=self._config.privacy.debug_store_email_artifacts,
            )
            msg_repo = EmailMessageRepository(session)
            ingestor = GmailIngestor(
                client=client,
                repo=msg_repo,
                account_id=account.id,
                debug_store=debug_store,
                store_subject_debug=self._config.privacy.debug_store_email_artifacts,
                trust_scorer=SenderTrustScorer(
                    user_blocklist=frozenset(incr_domain_prefs.blocklist)
                ),
            )
            results = ingestor.ingest_many(new_ids, query_source="incremental_sync")
            new_count = sum(1 for r in results if r.was_new)

            sync_repo.upsert(
                account.id,
                last_history_id=new_history_id or start_history_id,
                last_successful_sync_at=datetime.now(timezone.utc),
            )
            session.commit()

        processed = self._process_and_resolve(account_id_str, client)
        return {
            "new_ingested": new_count,
            "processed": len(processed),
        }

    def _process_and_resolve(self, account_id_str: str, client: GmailClient) -> list:
        with self._session_factory() as session:
            processing_svc = EmailProcessingService(
                session=session,
                gmail_client=client,
                config=self._config,
            )
            extractions = processing_svc.process_new_emails()

            resolution_svc = ShipmentResolutionService(
                session=session,
                processing=self._config.processing,
            )

            with self._session_factory() as msg_session:
                msg_repo = EmailMessageRepository(msg_session)
                for extraction in extractions:
                    msg = msg_repo.get(extraction.email_id)
                    received_at = msg.received_at if msg else datetime.now(timezone.utc)
                    resolution_svc.resolve_and_insert(extraction, received_at)

            session.commit()
        return extractions
