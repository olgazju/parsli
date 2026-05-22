"""Gmail-specific DTOs and query result models."""

from datetime import datetime

from pydantic import BaseModel


class BuiltGmailQuery(BaseModel):
    """A single named Gmail search query with its structured breakdown."""

    name: str
    query: str
    terms: list[str]
    exclude_terms: list[str]
    exclude_domains: list[str]


class QueryRunDTO(BaseModel):
    """Tracks one execution of a named Gmail query."""

    id: int | None = None
    fetch_batch_id: str
    query_name: str
    query_string: str
    started_at: datetime
    finished_at: datetime | None = None
    result_count: int = 0


class CandidateMatchDTO(BaseModel):
    """One (email_id, named_query) pairing from a fetch run."""

    email_id: str
    query_run_id: int  # resolved after QueryRunDTO is persisted
    fetch_batch_id: str
    query_name: str
    matched_at: datetime


class CandidateFetchSummary(BaseModel):
    """Aggregate statistics for one fetch() call."""

    fetch_batch_id: str
    total_unique_candidates: int
    multi_query_matches: int
    query_result_counts: dict[str, int]


class CandidateFetchResult(BaseModel):
    """Full result of running all named queries against the Gmail API."""

    message_ids: list[str]
    query_sources_by_message_id: dict[str, list[str]]
    summary: CandidateFetchSummary
    query_runs: list[QueryRunDTO]
    candidate_matches: list[CandidateMatchDTO]


class DomainPreferences(BaseModel):
    """User-managed per-sender overrides applied on top of the app defaults."""

    allowlist: list[str] = []
    blocklist: list[str] = []
    exclude_senders: list[str] = []  # specific email addresses, e.g. your own address
