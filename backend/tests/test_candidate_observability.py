"""Tests for Gmail candidate observability — persistence, querying, deduplication."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from parsli.config import GmailConfig
from parsli.db.models import Base, EmailMessage, EmailAccount
from parsli.db.repositories import CandidateMatchRepository, QueryRunRepository
from parsli.gmail.candidate_fetcher import GmailCandidateFetcher
from parsli.gmail.models import CandidateFetchResult, DomainPreferences
from parsli.gmail.query_builder import GmailQueryBuilder
from parsli.services.candidate_observability_service import (
    CandidateObservabilityService,
    persist_fetch_result,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        yield s


def _make_fetcher(query_results: dict[str, list[str]]) -> GmailCandidateFetcher:
    client = MagicMock()
    builder = GmailQueryBuilder(GmailConfig(lookback_days=30))
    queries = builder.build_queries()

    def _list_ids(query: str) -> list[str]:
        for q in queries:
            if q.query == query:
                return query_results.get(q.name, [])
        return []

    client.list_message_ids.side_effect = _list_ids
    return GmailCandidateFetcher(client=client, builder=builder)


# ── Fetch summary ──────────────────────────────────────────────────────────────

def test_summary_total_unique_candidates():
    fetcher = _make_fetcher({
        "strong_shipping": ["a", "b"],
        "order_lifecycle": ["b", "c"],
        "weak_phrases":    [],
    })
    result = fetcher.fetch()
    assert result.summary.total_unique_candidates == 3


def test_summary_multi_query_matches():
    fetcher = _make_fetcher({
        "strong_shipping": ["a", "b"],
        "order_lifecycle": ["b"],
        "weak_phrases":    [],
    })
    result = fetcher.fetch()
    assert result.summary.multi_query_matches == 1  # only "b"


def test_summary_query_result_counts():
    fetcher = _make_fetcher({
        "strong_shipping": ["a", "b", "c"],
        "order_lifecycle": ["d"],
        "weak_phrases":    [],
    })
    result = fetcher.fetch()
    assert result.summary.query_result_counts["strong_shipping"] == 3
    assert result.summary.query_result_counts["order_lifecycle"] == 1


def test_query_runs_one_per_query():
    fetcher = _make_fetcher({})
    result = fetcher.fetch()
    assert len(result.query_runs) == 3  # 3 base queries


def test_candidate_matches_no_duplicate_within_run():
    fetcher = _make_fetcher({"strong_shipping": ["x", "x", "x"], "order_lifecycle": [], "weak_phrases": []})
    result = fetcher.fetch()
    strong_matches = [m for m in result.candidate_matches if m.query_name == "strong_shipping"]
    assert len(strong_matches) == 1


def test_candidate_matches_run_index_in_range():
    fetcher = _make_fetcher({"strong_shipping": ["a"], "order_lifecycle": ["b"], "weak_phrases": []})
    result = fetcher.fetch()
    for m in result.candidate_matches:
        assert 0 <= m.query_run_id < len(result.query_runs)


# ── Persistence ────────────────────────────────────────────────────────────────

def test_persist_inserts_query_runs(session):
    fetcher = _make_fetcher({"strong_shipping": ["a", "b"], "order_lifecycle": [], "weak_phrases": []})
    result = fetcher.fetch()
    persist_fetch_result(session, result)
    session.flush()

    repo = QueryRunRepository(session)
    runs = repo.list_by_batch(result.summary.fetch_batch_id)
    assert len(runs) == 3


def test_persist_inserts_candidate_matches(session):
    fetcher = _make_fetcher({"strong_shipping": ["a", "b"], "order_lifecycle": ["c"], "weak_phrases": []})
    result = fetcher.fetch()
    persist_fetch_result(session, result)
    session.flush()

    repo = CandidateMatchRepository(session)
    assert repo.queries_for_email("a") == ["strong_shipping"]
    assert set(repo.queries_for_email("b")) == {"strong_shipping"}
    assert repo.queries_for_email("c") == ["order_lifecycle"]


def test_persist_idempotent_on_repeated_call(session):
    """Running persist_fetch_result twice with the same result must not raise."""
    fetcher = _make_fetcher({"strong_shipping": ["a"], "order_lifecycle": [], "weak_phrases": []})
    result = fetcher.fetch()
    persist_fetch_result(session, result)
    session.flush()
    # Second call — same result object, different batch_id because we re-fetch
    fetcher2 = _make_fetcher({"strong_shipping": ["a"], "order_lifecycle": [], "weak_phrases": []})
    result2 = fetcher2.fetch()
    persist_fetch_result(session, result2)
    session.flush()


# ── Observability service queries ──────────────────────────────────────────────

def test_latest_batch_id(session):
    fetcher = _make_fetcher({"strong_shipping": ["a"], "order_lifecycle": [], "weak_phrases": []})
    result = fetcher.fetch()
    persist_fetch_result(session, result)
    session.flush()

    svc = CandidateObservabilityService(session)
    assert svc.latest_batch_id() == result.summary.fetch_batch_id


def test_queries_for_email_multi_match(session):
    fetcher = _make_fetcher({
        "strong_shipping": ["x"],
        "order_lifecycle": ["x"],
        "weak_phrases":    [],
    })
    result = fetcher.fetch()
    persist_fetch_result(session, result)
    session.flush()

    svc = CandidateObservabilityService(session)
    queries = svc.queries_for_email("x")
    assert set(queries) == {"strong_shipping", "order_lifecycle"}


def test_emails_exclusive_to_weak_phrases(session):
    fetcher = _make_fetcher({
        "strong_shipping": ["a", "b"],
        "order_lifecycle": ["c"],
        "weak_phrases":    ["b", "d"],  # "b" also in strong, "d" is exclusive
    })
    result = fetcher.fetch()
    persist_fetch_result(session, result)
    session.flush()

    svc = CandidateObservabilityService(session)
    exclusive = svc.emails_exclusive_to_query("weak_phrases")
    assert exclusive == ["d"]
    assert "b" not in exclusive


def test_emails_matching_multiple_queries(session):
    fetcher = _make_fetcher({
        "strong_shipping": ["a", "b"],
        "order_lifecycle": ["b", "c"],
        "weak_phrases":    ["a"],
    })
    result = fetcher.fetch()
    persist_fetch_result(session, result)
    session.flush()

    svc = CandidateObservabilityService(session)
    multi = svc.emails_matching_multiple_queries()
    assert set(multi) == {"a", "b"}
    assert "c" not in multi


def test_no_latest_batch_returns_empty_lists(session):
    svc = CandidateObservabilityService(session)
    assert svc.emails_exclusive_to_query("weak_phrases") == []
    assert svc.emails_matching_multiple_queries() == []
