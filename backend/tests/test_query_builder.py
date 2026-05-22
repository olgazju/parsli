"""Tests for GmailQueryBuilder named-query output."""

import pytest

from parsli.config import GmailConfig
from parsli.gmail.models import DomainPreferences
from parsli.gmail.query_builder import GmailQueryBuilder


def _build(prefs: DomainPreferences | None = None) -> list:
    return GmailQueryBuilder(GmailConfig(lookback_days=30), prefs).build_queries()


def test_produces_three_base_queries():
    queries = _build()
    names = [q.name for q in queries]
    assert names == ["strong_shipping", "order_lifecycle", "weak_phrases"]


def test_no_allowlist_query_when_allowlist_empty():
    queries = _build(DomainPreferences(allowlist=[]))
    assert not any(q.name == "allowlisted_domains" for q in queries)


def test_allowlist_query_emitted_when_allowlist_non_empty():
    queries = _build(DomainPreferences(allowlist=["myshop.com"]))
    names = [q.name for q in queries]
    assert "allowlisted_domains" in names


def test_allowlist_query_restricts_to_from_clause():
    queries = _build(DomainPreferences(allowlist=["myshop.com", "brand.co.il"]))
    aq = next(q for q in queries if q.name == "allowlisted_domains")
    assert "from:myshop.com" in aq.query
    assert "from:brand.co.il" in aq.query


def test_quoted_phrases_preserved():
    queries = _build()
    strong = next(q for q in queries if q.name == "strong_shipping")
    assert '"tracking number"' in strong.query
    assert '"out for delivery"' in strong.query


def test_default_exclude_domains_in_all_queries():
    queries = _build()
    for q in queries:
        assert "-from:paypal.com" in q.query
        assert "-from:payplus.co.il" in q.query
        assert "-from:stripe.com" in q.query


def test_user_blocklist_appended_to_all_queries():
    queries = _build(DomainPreferences(blocklist=["spammer.com"]))
    for q in queries:
        assert "-from:spammer.com" in q.query


def test_weak_phrase_extra_exclusions_only_in_weak_query():
    queries = _build()
    weak = next(q for q in queries if q.name == "weak_phrases")
    strong = next(q for q in queries if q.name == "strong_shipping")
    assert '"your request"' in weak.query or "-\"your request\"" in weak.query
    # Extra exclusions must not bleed into the strong_shipping query
    assert '"your request"' not in strong.terms


def test_after_date_present_in_all_queries():
    queries = _build()
    for q in queries:
        assert "after:" in q.query


def test_empty_category_filter_not_emitted():
    cfg = GmailConfig(lookback_days=30, query_category_filter="")
    queries = GmailQueryBuilder(cfg).build_queries()
    for q in queries:
        assert "category:" not in q.query


def test_category_filter_emitted_when_set():
    cfg = GmailConfig(
        lookback_days=30,
        query_category_filter="(category:updates OR category:primary)",
    )
    queries = GmailQueryBuilder(cfg).build_queries()
    for q in queries:
        assert "category:updates" in q.query
