"""Tests for idempotency and privacy constraints."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from parsli.db.models import Base, EmailMessage
from parsli.db.repositories import EmailMessageRepository
from parsli.privacy.hashing import body_hash, subject_hash
from parsli.privacy.sanitizer import extract_sender_domain, redact_pii
from datetime import datetime, timezone


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s


def test_email_message_upsert_idempotent(session):
    repo = EmailMessageRepository(session)
    now = datetime.now(timezone.utc)
    msg = EmailMessage(
        email_id="abc123",
        account_id=1,
        received_at=now,
        sender_domain="example.com",
        subject_hash="aabbccdd0011",
        body_hash=body_hash("Hello world"),
    )
    repo.upsert(msg)
    session.flush()
    # Second upsert must not raise
    repo.upsert(msg)
    session.flush()

    # Still only one row
    from sqlalchemy import select
    rows = list(session.execute(select(EmailMessage)).scalars())
    assert len(rows) == 1


def test_no_raw_body_in_email_message(session):
    repo = EmailMessageRepository(session)
    now = datetime.now(timezone.utc)
    msg = EmailMessage(
        email_id="xyz999",
        account_id=1,
        received_at=now,
    )
    repo.upsert(msg)
    session.flush()

    from sqlalchemy import select, inspect
    cols = {c.key for c in inspect(EmailMessage).mapper.column_attrs}
    assert "body" not in cols
    assert "raw_body" not in cols
    assert "full_text" not in cols


def test_sender_trust_fields_present_in_email_message(session):
    from sqlalchemy import inspect
    cols = {c.key for c in inspect(EmailMessage).mapper.column_attrs}
    assert "sender_trust_level" in cols
    assert "sender_trust_score" in cols
    assert "sender_trust_reasons_json" in cols


def test_sender_trust_stored_on_ingest():
    import json
    from parsli.gmail.sender_trust import SenderTrustLevel, SenderTrustScorer
    from parsli.gmail.ingestor import GmailIngestor
    from parsli.privacy.debug_store import DebugStore
    from parsli.db.repositories import EmailMessageRepository
    from unittest.mock import MagicMock
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    mock_client = MagicMock()
    mock_client.fetch_raw.return_value = {
        "internalDate": str(now_ms),
        "threadId": "t1",
        "payload": {"headers": [{"name": "From", "value": "noreply@amazon.com"}]},
    }
    mock_client.extract_headers.return_value = {"From": "noreply@amazon.com"}
    mock_client.extract_body.return_value = "Your package shipped"

    with factory() as session:
        from parsli.db.models import EmailAccount
        acct = EmailAccount(email_address_hash="h1", provider="gmail")
        session.add(acct)
        session.flush()

        ingestor = GmailIngestor(
            client=mock_client,
            repo=EmailMessageRepository(session),
            account_id=acct.id,
            debug_store=DebugStore(app_dir=__import__("pathlib").Path("/tmp"), enabled=False),
            trust_scorer=SenderTrustScorer(),
        )
        ingestor.ingest_many(["msg_abc123"])
        session.flush()

        msg = session.get(EmailMessage, "msg_abc123")
        assert msg is not None
        assert msg.sender_trust_level == "high"
        assert msg.sender_trust_score == 4
        reasons = json.loads(msg.sender_trust_reasons_json or "[]")
        assert any("shipping" in r for r in reasons)


def test_redact_pii():
    text = "Contact us at user@example.com or call 050-1234567 for help."
    redacted = redact_pii(text)
    assert "user@example.com" not in redacted
    assert "050-1234567" not in redacted
    assert "[EMAIL]" in redacted
    assert "[PHONE]" in redacted


def test_extract_sender_domain():
    assert extract_sender_domain("Israel Post <no-reply@israelpost.co.il>") == "israelpost.co.il"
    assert extract_sender_domain("ASOS <shipping@asos.com>") == "asos.com"
    assert extract_sender_domain("no-email-here") is None


def test_subject_hash_is_stable():
    h1 = subject_hash("Your order has shipped!")
    h2 = subject_hash("Your order has shipped!")
    assert h1 == h2
    assert len(h1) == 12


def test_incremental_sync_no_duplicate_events():
    """Inserting the same event twice must result in exactly one row."""
    from parsli.domain.events import ShipmentEventDTO
    from parsli.domain.statuses import ShipmentStatus
    from parsli.db.repositories import ShipmentEventRepository
    from parsli.db.models import EmailMessage, EmailAccount
    from sqlalchemy import select

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    now = datetime.now(timezone.utc)
    with factory() as session:
        acct = EmailAccount(email_address_hash="hash123", provider="gmail")
        session.add(acct)
        session.flush()
        msg = EmailMessage(email_id="msg1", account_id=acct.id, received_at=now)
        session.add(msg)
        session.flush()

        event = ShipmentEventDTO(
            canonical_shipment_id="abcd1234efgh5678",
            email_id="msg1",
            event_date=now,
            status=ShipmentStatus.DELIVERED,
            status_confidence=0.95,
            status_evidence="delivered",
            sender_domain="hfd.co.il",
            tracking_number=None,
            order_number=None,
            merchant=None,
            processing_version="rules:v1;prompt:v1",
        )
        repo = ShipmentEventRepository(session)
        inserted1 = repo.insert_if_new(event)
        inserted2 = repo.insert_if_new(event)
        session.flush()

        from parsli.db.models import ShipmentEvent
        rows = list(session.execute(select(ShipmentEvent)).scalars())
        assert len(rows) == 1
        assert inserted1 is True
        assert inserted2 is False
