"""SQLAlchemy 2.x ORM models.

Only the minimum data required for incremental sync, deduplication,
extraction results, shipment timeline, and dashboard display is stored.
Raw email bodies, full cleaned text, and personal identifiers are never
persisted here by default.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EmailAccount(Base):
    __tablename__ = "email_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_address_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="gmail")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    sync_state: Mapped["GmailSyncState | None"] = relationship(
        "GmailSyncState", back_populates="account", uselist=False
    )


class GmailSyncState(Base):
    __tablename__ = "gmail_sync_state"

    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("email_accounts.id"), primary_key=True
    )
    last_history_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_successful_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    initial_sync_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    lookback_days: Mapped[int] = mapped_column(Integer, default=60)

    account: Mapped["EmailAccount"] = relationship(
        "EmailAccount", back_populates="sync_state"
    )


class EmailMessage(Base):
    __tablename__ = "email_messages"

    email_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("email_accounts.id"), nullable=False
    )
    thread_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sender_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # subject_debug is only populated when privacy.debug_store_email_artifacts is True
    subject_debug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    query_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Sender trust — computed during ingestion as a candidate quality signal
    sender_trust_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sender_trust_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sender_trust_reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ProcessedEmail(Base):
    __tablename__ = "processed_emails"

    email_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("email_messages.email_id"), primary_key=True
    )
    processing_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    cleaned_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_input_len: Mapped[int] = mapped_column(Integer, default=0)
    cleaned_full_len: Mapped[int] = mapped_column(Integer, default=0)
    classification_method: Mapped[str] = mapped_column(String(32), nullable=False)
    is_shipping_shaped: Mapped[bool] = mapped_column(Boolean, default=False)
    is_relevant: Mapped[bool] = mapped_column(Boolean, default=False)
    ignore_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EmailExtraction(Base):
    __tablename__ = "email_extractions"

    email_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("email_messages.email_id"), primary_key=True
    )
    processing_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Coarse email category (new)
    email_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Final reconciled status + per-source raw values
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status_evidence: Mapped[str] = mapped_column(Text, default="")
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    carrier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selected_tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_candidates_json: Mapped[str] = mapped_column(Text, default="[]")
    selected_order_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    order_candidates_json: Mapped[str] = mapped_column(Text, default="[]")
    pickup_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Decision metadata
    decision_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    conflict_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Model observability
    model_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_model_agreed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confidence_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(32), nullable=False)
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ShipmentAlias(Base):
    __tablename__ = "shipment_aliases"
    __table_args__ = (UniqueConstraint("alias_type", "alias_value"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False)
    alias_value: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_shipment_id: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_email_id: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"
    __table_args__ = (
        UniqueConstraint(
            "email_id", "event_date", "status", "tracking_number", "order_number"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_shipment_id: Mapped[str] = mapped_column(String(16), nullable=False)
    email_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("email_messages.email_id"), nullable=False
    )
    event_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    status_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status_evidence: Mapped[str] = mapped_column(Text, default="")
    sender_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    order_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processing_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Shipment(Base):
    __tablename__ = "shipments"

    canonical_shipment_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_tracking_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    primary_order_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_status: Mapped[str] = mapped_column(String(64), nullable=False)
    current_status_label: Mapped[str] = mapped_column(String(128), nullable=False)
    current_status_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    current_status_evidence: Mapped[str] = mapped_column(Text, default="")
    merge_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    chronology_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    chronology_severity: Mapped[str] = mapped_column(String(16), default="ok")
    chronology_notes_json: Mapped[str] = mapped_column(Text, default="[]")
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class DomainPreference(Base):
    __tablename__ = "domain_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # "allow" | "block"
    preference_type: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GmailQueryRun(Base):
    """One execution of a named Gmail search query."""

    __tablename__ = "gmail_query_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fetch_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    query_name: Mapped[str] = mapped_column(String(64), nullable=False)
    query_string: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)


class GmailCandidateMatch(Base):
    """One (email_id, query_run) pairing — which query found which message."""

    __tablename__ = "gmail_candidate_matches"
    __table_args__ = (UniqueConstraint("email_id", "query_run_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    query_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gmail_query_runs.id"), nullable=False
    )
    fetch_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    query_name: Mapped[str] = mapped_column(String(64), nullable=False)
    matched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
