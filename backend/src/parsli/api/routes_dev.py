"""Developer / observability API routes — only useful for local debugging."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import EmailExtraction, EmailMessage, GmailQueryRun, ProcessedEmail


class RecentProcessingRow(BaseModel):
    email_id: str
    classification_method: str | None
    is_relevant: bool
    ignore_reason: str | None
    model_mode: str | None
    status: str | None
    decision_source: str | None
    model_latency_ms: float | None
    needs_review: bool
    processed_at: datetime | None


class QueryRunRow(BaseModel):
    fetch_batch_id: str
    query_name: str
    result_count: int
    duration_ms: float | None
    started_at: datetime


class ObservabilityData(BaseModel):
    total_ingested: int
    total_processed: int
    total_relevant: int
    total_ignored: int
    recent_processing: list[RecentProcessingRow]
    recent_query_runs: list[QueryRunRow]


def make_dev_router(session_factory: sessionmaker[Session]) -> APIRouter:
    router = APIRouter(tags=["dev"])

    @router.get("/dev/observability", response_model=ObservabilityData)
    def get_observability() -> ObservabilityData:
        """Return lightweight processing stats for the developer screen."""
        with session_factory() as session:
            total_ingested = session.execute(
                select(func.count()).select_from(EmailMessage)
            ).scalar_one()

            total_processed = session.execute(
                select(func.count(distinct(ProcessedEmail.email_id))).select_from(ProcessedEmail)
            ).scalar_one()

            total_relevant = session.execute(
                select(func.count())
                .select_from(ProcessedEmail)
                .where(ProcessedEmail.is_relevant == True)  # noqa: E712
            ).scalar_one()

            rows = session.execute(
                select(
                    ProcessedEmail.email_id,
                    ProcessedEmail.classification_method,
                    ProcessedEmail.is_relevant,
                    ProcessedEmail.ignore_reason,
                    ProcessedEmail.model_mode,
                    ProcessedEmail.processed_at,
                    EmailExtraction.status,
                    EmailExtraction.decision_source,
                    EmailExtraction.model_latency_ms,
                    EmailExtraction.needs_review,
                )
                .outerjoin(
                    EmailExtraction,
                    EmailExtraction.email_id == ProcessedEmail.email_id,
                )
                .order_by(ProcessedEmail.processed_at.desc())
                .limit(30)
            ).all()

            query_runs = session.execute(
                select(GmailQueryRun).order_by(GmailQueryRun.started_at.desc()).limit(15)
            ).scalars().all()

        recent_processing = [
            RecentProcessingRow(
                email_id=r.email_id,
                classification_method=r.classification_method,
                is_relevant=r.is_relevant,
                ignore_reason=r.ignore_reason,
                model_mode=r.model_mode,
                status=r.status,
                decision_source=r.decision_source,
                model_latency_ms=r.model_latency_ms,
                needs_review=bool(r.needs_review),
                processed_at=r.processed_at,
            )
            for r in rows
        ]

        recent_query_runs = [
            QueryRunRow(
                fetch_batch_id=qr.fetch_batch_id,
                query_name=qr.query_name,
                result_count=qr.result_count,
                duration_ms=(
                    (qr.finished_at - qr.started_at).total_seconds() * 1000
                    if qr.finished_at and qr.started_at
                    else None
                ),
                started_at=qr.started_at,
            )
            for qr in query_runs
        ]

        return ObservabilityData(
            total_ingested=total_ingested,
            total_processed=total_processed,
            total_relevant=total_relevant,
            total_ignored=total_processed - total_relevant,
            recent_processing=recent_processing,
            recent_query_runs=recent_query_runs,
        )

    return router
