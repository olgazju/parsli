"""Tests for GmailCandidateFetcher deduplication and source tracking."""

from unittest.mock import MagicMock

from parsli.config import GmailConfig
from parsli.gmail.candidate_fetcher import GmailCandidateFetcher
from parsli.gmail.models import DomainPreferences
from parsli.gmail.query_builder import GmailQueryBuilder


def _make_fetcher(query_results: dict[str, list[str]]) -> GmailCandidateFetcher:
    """Build a fetcher whose GmailClient returns controlled IDs per query name."""
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


def test_deduplicates_message_ids():
    fetcher = _make_fetcher({
        "strong_shipping": ["id1", "id2", "id3"],
        "order_lifecycle": ["id2", "id3", "id4"],
        "weak_phrases":    ["id5"],
    })
    result = fetcher.fetch()
    assert sorted(result.message_ids) == ["id1", "id2", "id3", "id4", "id5"]


def test_single_source_messages():
    fetcher = _make_fetcher({
        "strong_shipping": ["id1"],
        "order_lifecycle": [],
        "weak_phrases":    [],
    })
    result = fetcher.fetch()
    assert result.query_sources_by_message_id["id1"] == ["strong_shipping"]


def test_multi_source_messages():
    fetcher = _make_fetcher({
        "strong_shipping": ["id1", "id2"],
        "order_lifecycle": ["id2", "id3"],
        "weak_phrases":    [],
    })
    result = fetcher.fetch()
    sources = result.query_sources_by_message_id["id2"]
    assert "strong_shipping" in sources
    assert "order_lifecycle" in sources


def test_no_duplicate_source_labels():
    # If the same ID appears twice in one query response, source should only be listed once.
    fetcher = _make_fetcher({
        "strong_shipping": ["id1", "id1"],
        "order_lifecycle": [],
        "weak_phrases":    [],
    })
    result = fetcher.fetch()
    assert result.query_sources_by_message_id["id1"].count("strong_shipping") == 1


def test_empty_results():
    fetcher = _make_fetcher({})
    result = fetcher.fetch()
    assert result.message_ids == []
    assert result.query_sources_by_message_id == {}
