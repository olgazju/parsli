"""Repository classes for all database tables.

Each repository receives a SQLAlchemy Session and executes typed queries.
No business logic lives here — only storage operations.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from sqlalchemy import func

from ..domain.events import ShipmentEventDTO
from ..domain.shipments import ShipmentAliasDTO, ShipmentDTO
from ..domain.statuses import ShipmentStatus, STATUS_LABELS
from ..gmail.models import CandidateMatchDTO, QueryRunDTO
from .models import (
    DomainPreference,
    EmailAccount,
    EmailExtraction,
    EmailMessage,
    GmailCandidateMatch,
    GmailQueryRun,
    GmailSyncState,
    ProcessedEmail,
    Shipment,
    ShipmentAlias,
    ShipmentEvent,
)


class EmailAccountRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def find_by_hash(self, email_hash: str) -> EmailAccount | None:
        return self._s.execute(
            select(EmailAccount).where(EmailAccount.email_address_hash == email_hash)
        ).scalar_one_or_none()

    def find_by_id(self, account_id: int) -> EmailAccount | None:
        return self._s.get(EmailAccount, account_id)

    def create(self, email_hash: str, provider: str = "gmail") -> EmailAccount:
        account = EmailAccount(email_address_hash=email_hash, provider=provider)
        self._s.add(account)
        self._s.flush()
        return account

    def list_all(self) -> list[EmailAccount]:
        return list(
            self._s.execute(select(EmailAccount).order_by(EmailAccount.created_at)).scalars()
        )


class GmailSyncStateRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, account_id: int) -> GmailSyncState | None:
        return self._s.get(GmailSyncState, account_id)

    def upsert(
        self,
        account_id: int,
        *,
        last_history_id: str | None = None,
        last_successful_sync_at: datetime | None = None,
        initial_sync_completed: bool | None = None,
        lookback_days: int | None = None,
    ) -> GmailSyncState:
        state = self._s.get(GmailSyncState, account_id)
        if state is None:
            state = GmailSyncState(account_id=account_id)
            self._s.add(state)
        if last_history_id is not None:
            state.last_history_id = last_history_id
        if last_successful_sync_at is not None:
            state.last_successful_sync_at = last_successful_sync_at
        if initial_sync_completed is not None:
            state.initial_sync_completed = initial_sync_completed
        if lookback_days is not None:
            state.lookback_days = lookback_days
        self._s.flush()
        return state


class EmailMessageRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def exists(self, email_id: str) -> bool:
        return self._s.get(EmailMessage, email_id) is not None

    def upsert(self, msg: EmailMessage) -> None:
        stmt = (
            sqlite_insert(EmailMessage)
            .values(
                email_id=msg.email_id,
                account_id=msg.account_id,
                thread_id=msg.thread_id,
                received_at=msg.received_at,
                sender_domain=msg.sender_domain,
                sender_display_name=msg.sender_display_name,
                subject_hash=msg.subject_hash,
                subject_debug=msg.subject_debug,
                body_hash=msg.body_hash,
                query_source=msg.query_source,
                sender_trust_level=msg.sender_trust_level,
                sender_trust_score=msg.sender_trust_score,
                sender_trust_reasons_json=msg.sender_trust_reasons_json,
            )
            .on_conflict_do_update(
                index_elements=["email_id"],
                set_={
                    "last_seen_at": datetime.now(timezone.utc),
                    "sender_display_name": msg.sender_display_name,
                },
            )
        )
        self._s.execute(stmt)

    def get_unprocessed_ids(
        self, processing_version: str, batch_size: int
    ) -> list[str]:
        """Return email IDs not yet in processed_emails for this version."""
        processed_subq = select(ProcessedEmail.email_id).where(
            ProcessedEmail.processing_version == processing_version
        )
        rows = self._s.execute(
            select(EmailMessage.email_id)
            .where(EmailMessage.email_id.not_in(processed_subq))
            .limit(batch_size)
        ).scalars()
        return list(rows)

    def get(self, email_id: str) -> EmailMessage | None:
        return self._s.get(EmailMessage, email_id)


class ProcessedEmailRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, record: ProcessedEmail) -> None:
        stmt = (
            sqlite_insert(ProcessedEmail)
            .values(
                email_id=record.email_id,
                processing_version=record.processing_version,
                cleaned_text_hash=record.cleaned_text_hash,
                model_input_len=record.model_input_len,
                cleaned_full_len=record.cleaned_full_len,
                classification_method=record.classification_method,
                is_shipping_shaped=record.is_shipping_shaped,
                is_relevant=record.is_relevant,
                ignore_reason=record.ignore_reason,
                model_mode=record.model_mode,
            )
            .on_conflict_do_update(
                index_elements=["email_id", "processing_version"],
                set_={
                    "is_relevant": record.is_relevant,
                    "ignore_reason": record.ignore_reason,
                    "model_mode": record.model_mode,
                    "processed_at": datetime.now(timezone.utc),
                },
            )
        )
        self._s.execute(stmt)


class EmailExtractionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, record: EmailExtraction) -> None:
        values = {
            "email_id": record.email_id,
            "processing_version": record.processing_version,
            "email_type": record.email_type,
            "status": record.status,
            "rule_status": record.rule_status,
            "model_status": record.model_status,
            "status_confidence": record.status_confidence,
            "status_evidence": record.status_evidence,
            "merchant": record.merchant,
            "carrier": record.carrier,
            "selected_tracking_number": record.selected_tracking_number,
            "tracking_candidates_json": record.tracking_candidates_json,
            "selected_order_number": record.selected_order_number,
            "order_candidates_json": record.order_candidates_json,
            "pickup_code": record.pickup_code,
            "amount": record.amount,
            "currency": record.currency,
            "decision_source": record.decision_source,
            "conflict_reason": record.conflict_reason,
            "model_provider": record.model_provider,
            "model_name": record.model_name,
            "model_mode": record.model_mode,
            "model_latency_ms": record.model_latency_ms,
            "prompt_tokens": record.prompt_tokens,
            "completion_tokens": record.completion_tokens,
            "rule_model_agreed": record.rule_model_agreed,
            "confidence_delta": record.confidence_delta,
            "needs_review": record.needs_review,
            "prompt_version": record.prompt_version,
            "rules_version": record.rules_version,
            "extraction_error": record.extraction_error,
        }
        stmt = sqlite_insert(EmailExtraction).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["email_id", "processing_version"],
            set_={k: v for k, v in values.items() if k not in ("email_id", "processing_version")},
        )
        self._s.execute(stmt)

    def get(self, email_id: str, processing_version: str) -> EmailExtraction | None:
        return self._s.get(EmailExtraction, (email_id, processing_version))


class ShipmentAliasRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def find_canonical(self, alias_type: str, alias_value: str) -> str | None:
        """Return the canonical_shipment_id for an alias, if known."""
        row = self._s.execute(
            select(ShipmentAlias.canonical_shipment_id).where(
                ShipmentAlias.alias_type == alias_type,
                ShipmentAlias.alias_value == alias_value.upper(),
            )
        ).scalar_one_or_none()
        return row

    def upsert(self, alias: ShipmentAliasDTO) -> None:
        stmt = (
            sqlite_insert(ShipmentAlias)
            .values(
                alias_type=alias.alias_type,
                alias_value=alias.alias_value.upper(),
                canonical_shipment_id=alias.canonical_shipment_id,
                confidence=alias.confidence,
                evidence_email_id=alias.evidence_email_id,
            )
            .on_conflict_do_update(
                index_elements=["alias_type", "alias_value"],
                set_={
                    "confidence": alias.confidence,
                    "evidence_email_id": alias.evidence_email_id,
                },
            )
        )
        self._s.execute(stmt)

    def list_for_shipment(self, canonical_shipment_id: str) -> list[ShipmentAlias]:
        return list(
            self._s.execute(
                select(ShipmentAlias).where(
                    ShipmentAlias.canonical_shipment_id == canonical_shipment_id
                )
            ).scalars()
        )


class ShipmentEventRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def insert_if_new(self, event: ShipmentEventDTO) -> bool:
        """Insert the event; return True if inserted, False if duplicate.

        SQLite treats NULL as distinct in unique constraints, so two rows with
        (email_id, date, status, NULL, NULL) would both be inserted despite the
        constraint. We guard with an explicit existence check instead.
        """
        exists_q = select(ShipmentEvent.id).where(
            ShipmentEvent.email_id == event.email_id,
            ShipmentEvent.event_date == event.event_date,
            ShipmentEvent.status == event.status.value,
            (
                ShipmentEvent.tracking_number == event.tracking_number
                if event.tracking_number is not None
                else ShipmentEvent.tracking_number.is_(None)
            ),
            (
                ShipmentEvent.order_number == event.order_number
                if event.order_number is not None
                else ShipmentEvent.order_number.is_(None)
            ),
        )
        existing_id = self._s.execute(exists_q).scalar_one_or_none()
        if existing_id is not None:
            # Backfill sender info if the existing row has NULLs and we now have values.
            if event.sender_display_name or event.sender_domain:
                self._s.execute(
                    update(ShipmentEvent)
                    .where(ShipmentEvent.id == existing_id)
                    .where(ShipmentEvent.sender_display_name.is_(None))
                    .values(
                        sender_display_name=event.sender_display_name,
                        sender_domain=event.sender_domain,
                    )
                )
            return False

        new_row = ShipmentEvent(
            canonical_shipment_id=event.canonical_shipment_id,
            email_id=event.email_id,
            event_date=event.event_date,
            status=event.status.value,
            status_confidence=event.status_confidence,
            status_evidence=event.status_evidence,
            sender_domain=event.sender_domain,
            sender_display_name=event.sender_display_name,
            tracking_number=event.tracking_number,
            order_number=event.order_number,
            merchant=event.merchant,
            processing_version=event.processing_version,
        )
        self._s.add(new_row)
        return True

    def list_for_shipment(self, canonical_shipment_id: str) -> list[ShipmentEventDTO]:
        rows = list(
            self._s.execute(
                select(ShipmentEvent)
                .where(ShipmentEvent.canonical_shipment_id == canonical_shipment_id)
                .order_by(ShipmentEvent.event_date)
            ).scalars()
        )
        return [_event_row_to_dto(r) for r in rows]

    def affected_shipment_ids(self, email_ids: list[str]) -> list[str]:
        rows = self._s.execute(
            select(ShipmentEvent.canonical_shipment_id)
            .where(ShipmentEvent.email_id.in_(email_ids))
            .distinct()
        ).scalars()
        return list(rows)


class ShipmentRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, shipment: ShipmentDTO) -> None:
        stmt = (
            sqlite_insert(Shipment)
            .values(
                canonical_shipment_id=shipment.canonical_shipment_id,
                merchant=shipment.merchant,
                primary_tracking_number=shipment.primary_tracking_number,
                primary_order_number=shipment.primary_order_number,
                current_status=shipment.current_status.value,
                current_status_label=shipment.current_status_label,
                current_status_date=shipment.current_status_date,
                current_status_evidence=shipment.current_status_evidence,
                merge_confidence=shipment.merge_confidence,
                chronology_ok=shipment.chronology_ok,
                chronology_severity=shipment.chronology_severity,
                chronology_notes_json=json.dumps(shipment.chronology_notes),
                chronology_reason_code=shipment.chronology_reason_code,
                event_count=shipment.event_count,
                first_seen_at=shipment.first_seen_at,
                last_seen_at=shipment.last_seen_at,
                updated_at=datetime.now(timezone.utc),
            )
            .on_conflict_do_update(
                index_elements=["canonical_shipment_id"],
                set_={
                    "merchant": shipment.merchant,
                    "primary_tracking_number": shipment.primary_tracking_number,
                    "primary_order_number": shipment.primary_order_number,
                    "current_status": shipment.current_status.value,
                    "current_status_label": shipment.current_status_label,
                    "current_status_date": shipment.current_status_date,
                    "current_status_evidence": shipment.current_status_evidence,
                    "merge_confidence": shipment.merge_confidence,
                    "chronology_ok": shipment.chronology_ok,
                    "chronology_severity": shipment.chronology_severity,
                    "chronology_notes_json": json.dumps(shipment.chronology_notes),
                    "chronology_reason_code": shipment.chronology_reason_code,
                    "event_count": shipment.event_count,
                    "last_seen_at": shipment.last_seen_at,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
        )
        self._s.execute(stmt)

    def list_all(self) -> list[ShipmentDTO]:
        rows = list(
            self._s.execute(
                select(Shipment).order_by(Shipment.current_status_date.desc())
            ).scalars()
        )
        return [_shipment_row_to_dto(r) for r in rows]

    def get(self, canonical_shipment_id: str) -> ShipmentDTO | None:
        row = self._s.get(Shipment, canonical_shipment_id)
        return _shipment_row_to_dto(row) if row else None


class QueryRunRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def insert(self, dto: QueryRunDTO) -> int:
        """Insert a query run record and return the assigned DB id."""
        run = GmailQueryRun(
            fetch_batch_id=dto.fetch_batch_id,
            query_name=dto.query_name,
            query_string=dto.query_string,
            started_at=dto.started_at,
            finished_at=dto.finished_at,
            result_count=dto.result_count,
        )
        self._s.add(run)
        self._s.flush()
        return run.id

    def latest_batch_id(self) -> str | None:
        row = self._s.execute(
            select(GmailQueryRun.fetch_batch_id)
            .order_by(GmailQueryRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return row

    def list_by_batch(self, batch_id: str) -> list[GmailQueryRun]:
        return list(
            self._s.execute(
                select(GmailQueryRun)
                .where(GmailQueryRun.fetch_batch_id == batch_id)
                .order_by(GmailQueryRun.started_at)
            ).scalars()
        )


class CandidateMatchRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def insert_many(self, dtos: list[CandidateMatchDTO]) -> None:
        for dto in dtos:
            stmt = (
                sqlite_insert(GmailCandidateMatch)
                .values(
                    email_id=dto.email_id,
                    query_run_id=dto.query_run_id,
                    fetch_batch_id=dto.fetch_batch_id,
                    query_name=dto.query_name,
                    matched_at=dto.matched_at,
                )
                .on_conflict_do_nothing()
            )
            self._s.execute(stmt)

    def queries_for_email(self, email_id: str) -> list[str]:
        """All distinct query names that ever matched this email across all runs."""
        rows = self._s.execute(
            select(GmailCandidateMatch.query_name)
            .where(GmailCandidateMatch.email_id == email_id)
            .distinct()
        ).scalars()
        return list(rows)

    def emails_exclusive_to_query(self, query_name: str, batch_id: str) -> list[str]:
        """Email IDs that matched only this query (and no other) in the given batch."""
        other_subq = (
            select(GmailCandidateMatch.email_id)
            .where(
                GmailCandidateMatch.fetch_batch_id == batch_id,
                GmailCandidateMatch.query_name != query_name,
            )
        )
        rows = self._s.execute(
            select(GmailCandidateMatch.email_id)
            .where(
                GmailCandidateMatch.fetch_batch_id == batch_id,
                GmailCandidateMatch.query_name == query_name,
                GmailCandidateMatch.email_id.not_in(other_subq),
            )
            .distinct()
        ).scalars()
        return list(rows)

    def emails_matching_multiple_queries(self, batch_id: str) -> list[str]:
        """Email IDs that matched more than one distinct query in the given batch."""
        rows = self._s.execute(
            select(GmailCandidateMatch.email_id)
            .where(GmailCandidateMatch.fetch_batch_id == batch_id)
            .group_by(GmailCandidateMatch.email_id)
            .having(func.count(GmailCandidateMatch.query_name.distinct()) > 1)
        ).scalars()
        return list(rows)


class DomainPreferenceRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def list_all(self) -> list[DomainPreference]:
        return list(self._s.execute(select(DomainPreference)).scalars())

    def find(self, domain: str) -> DomainPreference | None:
        return self._s.execute(
            select(DomainPreference).where(DomainPreference.domain == domain.lower())
        ).scalar_one_or_none()

    def upsert(self, domain: str, preference_type: str) -> None:
        stmt = (
            sqlite_insert(DomainPreference)
            .values(domain=domain.lower(), preference_type=preference_type)
            .on_conflict_do_update(
                index_elements=["domain"],
                set_={"preference_type": preference_type},
            )
        )
        self._s.execute(stmt)

    def remove(self, domain: str) -> bool:
        row = self.find(domain)
        if row is None:
            return False
        self._s.delete(row)
        return True


# ── Converters ─────────────────────────────────────────────────────────────────


def _event_row_to_dto(row: ShipmentEvent) -> ShipmentEventDTO:
    return ShipmentEventDTO(
        id=row.id,
        canonical_shipment_id=row.canonical_shipment_id,
        email_id=row.email_id,
        event_date=row.event_date,
        status=ShipmentStatus(row.status),
        status_confidence=row.status_confidence,
        status_evidence=row.status_evidence,
        sender_domain=row.sender_domain,
        sender_display_name=row.sender_display_name,
        tracking_number=row.tracking_number,
        order_number=row.order_number,
        merchant=row.merchant,
        processing_version=row.processing_version,
        created_at=row.created_at,
    )


def _shipment_row_to_dto(row: Shipment) -> ShipmentDTO:
    return ShipmentDTO(
        canonical_shipment_id=row.canonical_shipment_id,
        merchant=row.merchant,
        primary_tracking_number=row.primary_tracking_number,
        primary_order_number=row.primary_order_number,
        current_status=ShipmentStatus(row.current_status),
        current_status_label=row.current_status_label,
        current_status_date=row.current_status_date,
        current_status_evidence=row.current_status_evidence,
        merge_confidence=row.merge_confidence,
        chronology_ok=row.chronology_ok,
        chronology_severity=row.chronology_severity,
        chronology_notes=json.loads(row.chronology_notes_json or "[]"),
        chronology_reason_code=row.chronology_reason_code,
        event_count=row.event_count,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        updated_at=row.updated_at,
    )
