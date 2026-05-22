"""GmailIngestor — fetches messages, extracts minimal metadata, persists rows.

Raw email bodies and full text are never written to the database.
Body hashes are computed in memory from the extracted plain text.
"""

import json
from datetime import datetime, timezone

from ..db.models import EmailMessage
from ..db.repositories import EmailMessageRepository
from ..privacy.debug_store import DebugStore
from ..privacy.hashing import body_hash, subject_hash
from ..privacy.sanitizer import extract_sender_domain
from .client import GmailClient
from .models import CandidateFetchResult
from .sender_trust import SenderTrustScorer


class IngestedEmailMeta:
    """Lightweight result returned by the ingestor for each processed message."""

    __slots__ = ("email_id", "was_new", "is_relevant_shape")

    def __init__(self, email_id: str, was_new: bool) -> None:
        self.email_id = email_id
        self.was_new = was_new


class GmailIngestor:
    """Fetches Gmail messages and writes minimal metadata rows.

    Args:
        client: Authenticated GmailClient.
        repo: EmailMessageRepository for the active session.
        account_id: DB account ID for the authenticated account.
        debug_store: DebugStore instance (writes only if debug mode is on).
        store_subject_debug: Whether to persist the raw subject string.
    """

    def __init__(
        self,
        client: GmailClient,
        repo: EmailMessageRepository,
        account_id: int,
        debug_store: DebugStore,
        store_subject_debug: bool = False,
        trust_scorer: SenderTrustScorer | None = None,
    ) -> None:
        self._client = client
        self._repo = repo
        self._account_id = account_id
        self._debug = debug_store
        self._store_subject_debug = store_subject_debug
        self._trust_scorer = trust_scorer or SenderTrustScorer()

    def ingest_many(
        self,
        message_ids: list[str],
        query_source: str | None = None,
    ) -> list[IngestedEmailMeta]:
        """Ingest a batch of message IDs.

        Already-seen IDs are touched (last_seen_at updated) but not re-fetched.
        Returns one IngestedEmailMeta per ID.
        """
        results: list[IngestedEmailMeta] = []
        for msg_id in message_ids:
            meta = self._ingest_one(msg_id, query_source)
            results.append(meta)
        return results

    def ingest_from_candidates(
        self, result: CandidateFetchResult
    ) -> list[IngestedEmailMeta]:
        """Ingest every message in a CandidateFetchResult.

        Each message is stored with a comma-joined query_source reflecting
        all named queries that matched it, e.g. ``"strong_shipping,order_lifecycle"``.
        """
        metas: list[IngestedEmailMeta] = []
        for msg_id, sources in result.query_sources_by_message_id.items():
            query_source = ",".join(sources)
            meta = self._ingest_one(msg_id, query_source)
            metas.append(meta)
        return metas

    def _ingest_one(
        self, message_id: str, query_source: str | None
    ) -> IngestedEmailMeta:
        if self._repo.exists(message_id):
            # Touch last_seen_at via upsert (conflict handler updates it)
            existing = self._repo.get(message_id)
            if existing:
                self._repo.upsert(existing)
            return IngestedEmailMeta(message_id, was_new=False)

        raw = self._client.fetch_raw(message_id)
        self._debug.store_raw_email(message_id, raw)

        headers = self._client.extract_headers(raw)
        subject = headers.get("Subject", "")
        sender = headers.get("From", "")
        internal_date_ms = int(raw.get("internalDate", 0))
        thread_id = raw.get("threadId")

        received_at = datetime.fromtimestamp(
            internal_date_ms / 1000, tz=timezone.utc
        )
        domain = extract_sender_domain(sender)

        body_text = self._client.extract_body(raw.get("payload", {}))
        bh = body_hash(body_text) if body_text else None

        trust = self._trust_scorer.score(domain)

        msg = EmailMessage(
            email_id=message_id,
            account_id=self._account_id,
            thread_id=thread_id,
            received_at=received_at,
            sender_domain=domain,
            subject_hash=subject_hash(subject) if subject else None,
            subject_debug=subject[:255] if self._store_subject_debug else None,
            body_hash=bh,
            query_source=query_source,
            sender_trust_level=trust.trust_level.value,
            sender_trust_score=trust.trust_score,
            sender_trust_reasons_json=json.dumps(trust.reasons),
        )
        self._repo.upsert(msg)
        return IngestedEmailMeta(message_id, was_new=True)
