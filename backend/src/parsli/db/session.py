from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def make_engine(sqlite_path: Path) -> Engine:
    """Create a SQLite engine, ensuring the parent directory exists."""
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{sqlite_path}",
        connect_args={"check_same_thread": False},
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


# Columns added after initial schema creation.
# Each entry: (table, column, sqlite_type).
# Idempotent: ALTER TABLE is silently ignored if the column already exists.
_NEW_COLUMNS: list[tuple[str, str, str]] = [
    ("processed_emails", "model_mode", "VARCHAR(32)"),
    ("email_extractions", "email_type", "VARCHAR(32)"),
    ("email_extractions", "rule_status", "VARCHAR(64)"),
    ("email_extractions", "model_status", "VARCHAR(64)"),
    ("email_extractions", "carrier", "VARCHAR(64)"),
    ("email_extractions", "decision_source", "VARCHAR(32)"),
    ("email_extractions", "conflict_reason", "TEXT"),
    ("email_extractions", "model_mode", "VARCHAR(32)"),
    ("email_extractions", "model_latency_ms", "REAL"),
    ("email_extractions", "prompt_tokens", "INTEGER"),
    ("email_extractions", "completion_tokens", "INTEGER"),
    ("email_extractions", "rule_model_agreed", "BOOLEAN"),
    ("email_extractions", "confidence_delta", "REAL"),
    ("email_extractions", "needs_review", "BOOLEAN"),
    ("shipments", "chronology_reason_code", "VARCHAR(64)"),
    ("shipment_events", "sender_display_name", "VARCHAR(255)"),
    ("email_messages", "sender_display_name", "VARCHAR(255)"),
]


def ensure_schema(engine: Engine) -> None:
    """Create all tables and add any new columns to existing tables.

    Safe to call on a fresh DB (create_all) and on an existing DB
    (ALTER TABLE ADD COLUMN is a no-op when the column already exists).
    """
    from .models import Base

    Base.metadata.create_all(engine)

    with engine.connect() as conn:
        for table, col, col_type in _NEW_COLUMNS:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                conn.commit()
            except Exception:
                # Column already exists — SQLite raises OperationalError
                pass
