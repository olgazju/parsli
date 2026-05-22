"""CandidateObservabilityService — query helpers for Gmail candidate retrieval data."""

from sqlalchemy.orm import Session

from ..db.repositories import CandidateMatchRepository, QueryRunRepository
from ..gmail.models import CandidateFetchResult


def persist_fetch_result(session: Session, result: CandidateFetchResult) -> None:
    """Insert query runs and candidate matches from a fetch() result.

    ``candidate_matches[i].query_run_id`` holds a run index (0, 1, 2…) before
    this call; this function resolves it to the real DB id.
    """
    qr_repo = QueryRunRepository(session)
    cm_repo = CandidateMatchRepository(session)

    run_db_ids: list[int] = [qr_repo.insert(run) for run in result.query_runs]

    resolved = [
        m.model_copy(update={"query_run_id": run_db_ids[m.query_run_id]})
        for m in result.candidate_matches
    ]
    cm_repo.insert_many(resolved)


class CandidateObservabilityService:
    """Read-only helpers for inspecting Gmail candidate retrieval history.

    Args:
        session: SQLAlchemy session.
    """

    def __init__(self, session: Session) -> None:
        self._qr_repo = QueryRunRepository(session)
        self._cm_repo = CandidateMatchRepository(session)

    def latest_batch_id(self) -> str | None:
        """Return the fetch_batch_id of the most recent fetch() run."""
        return self._qr_repo.latest_batch_id()

    def queries_for_email(self, email_id: str) -> list[str]:
        """All distinct query names that ever matched this email across all runs."""
        return self._cm_repo.queries_for_email(email_id)

    def emails_exclusive_to_query(
        self, query_name: str, batch_id: str | None = None
    ) -> list[str]:
        """Email IDs that matched ONLY this query in the given batch.

        Uses the latest batch when batch_id is None.
        """
        bid = batch_id or self.latest_batch_id()
        if bid is None:
            return []
        return self._cm_repo.emails_exclusive_to_query(query_name, bid)

    def emails_matching_multiple_queries(
        self, batch_id: str | None = None
    ) -> list[str]:
        """Email IDs that matched more than one distinct query in the given batch."""
        bid = batch_id or self.latest_batch_id()
        if bid is None:
            return []
        return self._cm_repo.emails_matching_multiple_queries(bid)
