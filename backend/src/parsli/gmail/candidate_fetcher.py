"""GmailCandidateFetcher — runs all named queries and deduplicates results.

``fetch()`` is pure network I/O with no database access.  The returned
``CandidateFetchResult`` carries ``query_runs`` and ``candidate_matches``
ready for the caller to persist.

In ``candidate_matches``, ``query_run_id`` holds the *index* into
``query_runs`` (0, 1, 2…) as a pre-persistence placeholder.  The persistence
helper in ``sync_service`` maps these indices to real DB ids after inserting
the run rows.
"""

import logging
import uuid
from datetime import datetime, timezone

from .client import GmailClient
from .models import (
    CandidateFetchResult,
    CandidateFetchSummary,
    CandidateMatchDTO,
    QueryRunDTO,
)
from .query_builder import GmailQueryBuilder

logger = logging.getLogger(__name__)


class GmailCandidateFetcher:
    """Runs each named query, deduplicates, and collects observability data."""

    def __init__(self, client: GmailClient, builder: GmailQueryBuilder) -> None:
        self._client = client
        self._builder = builder

    def fetch(self) -> CandidateFetchResult:
        batch_id = str(uuid.uuid4())
        queries = self._builder.build_queries()

        sources_by_id: dict[str, list[str]] = {}
        query_runs: list[QueryRunDTO] = []
        candidate_matches: list[CandidateMatchDTO] = []

        for run_idx, built in enumerate(queries):
            started_at = datetime.now(timezone.utc)
            ids = self._client.list_message_ids(built.query)
            finished_at = datetime.now(timezone.utc)

            logger.info("[%s] results=%d", built.name, len(ids))

            query_runs.append(QueryRunDTO(
                fetch_batch_id=batch_id,
                query_name=built.name,
                query_string=built.query,
                started_at=started_at,
                finished_at=finished_at,
                result_count=len(ids),
            ))

            seen_in_run: set[str] = set()
            matched_at = datetime.now(timezone.utc)
            for msg_id in ids:
                if msg_id not in sources_by_id:
                    sources_by_id[msg_id] = []
                if built.name not in sources_by_id[msg_id]:
                    sources_by_id[msg_id].append(built.name)
                if msg_id not in seen_in_run:
                    seen_in_run.add(msg_id)
                    candidate_matches.append(CandidateMatchDTO(
                        email_id=msg_id,
                        query_run_id=run_idx,  # index → resolved to DB id by caller
                        fetch_batch_id=batch_id,
                        query_name=built.name,
                        matched_at=matched_at,
                    ))

        multi_match = sum(1 for s in sources_by_id.values() if len(s) > 1)
        logger.info(
            "\nUnique candidates=%d\nMatched >1 query=%d",
            len(sources_by_id),
            multi_match,
        )

        summary = CandidateFetchSummary(
            fetch_batch_id=batch_id,
            total_unique_candidates=len(sources_by_id),
            multi_query_matches=multi_match,
            query_result_counts={r.query_name: r.result_count for r in query_runs},
        )

        return CandidateFetchResult(
            message_ids=list(sources_by_id.keys()),
            query_sources_by_message_id=sources_by_id,
            summary=summary,
            query_runs=query_runs,
            candidate_matches=candidate_matches,
        )
