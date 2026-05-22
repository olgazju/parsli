# Parsli backend

Local-first parcel tracking backend. Privacy-first: raw email bodies and PII are never persisted.

## Stack

- Python 3.14 · pyenv virtualenv `parcli`
- Pydantic v2 + pydantic-settings · SQLAlchemy 2.x (SQLite) · FastAPI · httpx

## Install & run

```bash
cd backend
pip install -e ".[dev]"

parsli serve          # FastAPI on :8000
parsli sync <id>      # incremental sync (auto-opens OAuth browser if no token)
parsli sync <id> --mode initial
parsli rebuild        # rebuild all shipment timelines from existing events
```

## Package layout

```
src/parsli/
  config.py              AppConfig (env prefix PARSLI_, nested __)
                         QueryVocabulary — grouped keyword config (developer-controlled)
  domain/                Pure domain objects — no I/O
    statuses.py          ShipmentStatus enum + SIDE_STATUSES / TERMINAL_STATUSES
    identifiers.py       TrackingIdentifier, OrderIdentifier, pattern extractors
    carriers.py          CarrierFamily detection from tracking number or domain
    events.py            ShipmentEventDTO
    shipments.py         ShipmentDTO, ShipmentAliasDTO, DashboardDTO
    chronology.py        check_chronology(), select_current_status()
    merge.py             can_merge_tracking_numbers(), canonical_shipment_id()
  privacy/
    hashing.py           sha256_hex / body_hash / subject_hash
    sanitizer.py         redact_pii(), extract_sender_domain(), clip_text()
    debug_store.py       DebugStore — no-op when disabled
  db/
    models.py            SQLAlchemy ORM (11 tables, no raw body columns)
                         Includes DomainPreference, GmailQueryRun, GmailCandidateMatch
    session.py           make_engine(), make_session_factory()
    repositories.py      One repo class per table
  gmail/
    auth.py              GmailOAuthManager + TokenMissingError
    client.py            GmailClient (fetch_raw, extract_body, list_message_ids)
    models.py            BuiltGmailQuery, QueryRunDTO, CandidateMatchDTO,
                         CandidateFetchSummary, CandidateFetchResult, DomainPreferences
    domain_normalizer.py DomainNormalizer — cleans user-supplied domain strings
    query_builder.py     GmailQueryBuilder.build_queries() → list[BuiltGmailQuery]
                         Builds 4 named queries: strong_shipping, order_lifecycle,
                         weak_phrases, allowlisted_domains (if allowlist non-empty)
    sender_trust.py      SenderTrustScorer, SenderTrustLevel, SenderTrustResult
                         Domain lists: KNOWN_SHIPPING_DOMAINS, KNOWN_ECOMMERCE_DOMAINS,
                         FREE_EMAIL_PROVIDER_DOMAINS. Scoring signal only — never blocks.
                         Accepts user_blocklist: frozenset[str] → BLOCKED if matched.
    candidate_fetcher.py GmailCandidateFetcher.fetch() → CandidateFetchResult
                         Pure network I/O — no DB access. Returns query_runs and
                         candidate_matches for the caller to persist.
                         candidate_matches[i].query_run_id holds the run INDEX (not DB id)
                         before persistence; persist_fetch_result() resolves it.
    ingestor.py          GmailIngestor — stores metadata only, never full body
                         ingest_from_candidates(result) for named-query source tracking
                         Accepts trust_scorer: SenderTrustScorer; stores trust_level,
                         trust_score, trust_reasons_json in email_messages
  processing/
    cleaner.py           EmailCleaner → CleanedEmail
    rule_engine.py       RuleEngine(email_id, cleaned_text, sender_domain) → RuleExtractionResult
                         sender_domain checked first — payment processors → is_invoice=True
                         ACTION_REQUIRED rule fires before READY_FOR_PICKUP
    extraction_orchestrator.py  Merges rules + model → FinalExtraction, persists rows
    pipeline.py          EmailProcessingPipeline (wires cleaner→rules→orchestrator)
  model/
    base.py              LocalModelClient Protocol + ModelExtractionResult
    prompts.py           format_prompt(text, version)
    lmstudio_client.py   OpenAI-compatible /v1/chat/completions
    llamacpp_client.py   llama-cpp /v1/chat/completions
    factory.py           ModelClientFactory.create(config)
  services/
    sync_service.py      initial_sync() / incremental_sync()
                         Uses GmailCandidateFetcher; loads DomainPreferences from DB;
                         calls persist_fetch_result() for observability
    email_processing_service.py  process_new_emails() / reprocess_email()
    shipment_resolution_service.py  resolve_and_insert(), rebuild_all()
    dashboard_service.py get_dashboard() → DashboardDTO
    domain_preference_service.py  add/remove allowlist and blocklist domains
    candidate_observability_service.py
                         persist_fetch_result(session, result) — resolves run indices to
                         DB ids and inserts GmailQueryRun + GmailCandidateMatch rows
                         CandidateObservabilityService — queries_for_email(),
                         emails_exclusive_to_query(), emails_matching_multiple_queries()
  api/
    main.py              create_app(config) factory
    routes_dashboard.py  GET /api/dashboard, /api/shipments, /api/shipments/{id}
    routes_sync.py       POST /api/sync/initial|incremental, GET /api/status
    routes_settings.py   GET/POST/DELETE /api/settings/domains/allowlist|blocklist
  cli.py                 parsli serve | sync | rebuild
```

## Gmail candidate query design

`GmailQueryBuilder.build_queries()` emits up to 4 named queries instead of one large OR:

| Query name | Terms used | Notes |
|---|---|---|
| `strong_shipping` | `strong_shipping` + `package_words` | High-confidence signals |
| `order_lifecycle` | `order_lifecycle` | Order confirmation/shipped phrases |
| `weak_phrases` | `weak_phrases` + extra exclusions | Low-precision, extra noise filtering |
| `allowlisted_domains` | broad terms + `from:domain` restriction | Only when user allowlist is non-empty |

Every query includes: default `exclude_terms`, `-from:` for all `default_exclude_domains` and user blocklist, `after:<date>`.

`email_messages.query_source` stores which named queries matched, comma-joined: `"strong_shipping,order_lifecycle"`.

## Gmail observability

Two new tables (`gmail_query_runs`, `gmail_candidate_matches`) track every fetch execution.
`fetch_batch_id` (UUID) groups all query runs from one `fetcher.fetch()` call.

**`persist_fetch_result(session, result)`** — resolves run indices to real DB ids and writes both tables in one session. Call immediately after `fetch()`.

**`CandidateObservabilityService`** read-only helpers (all default to latest batch):
- `queries_for_email(email_id)` — which queries ever matched this email
- `emails_exclusive_to_query(query_name)` — emails that matched ONLY this query
- `emails_matching_multiple_queries()` — emails that matched >1 query

## Domain preferences

User-managed via API (`/api/settings/domains`):
- **allowlist** — builds an extra `allowlisted_domains` query for those senders
- **blocklist** — adds `-from:domain` to every query

Developer defaults in `QueryVocabulary.default_exclude_domains`:
`payplus.co.il`, `paypal.com`, `stripe.com`, `cardcom.co.il`, `tranzila.com`, `isracard.co.il`

Also checked by `RuleEngine` at classification time (belt-and-suspenders).

`DomainNormalizer` accepts: bare domain, `@domain`, `https://domain/path`, uppercase.

## Key rules

**Sender trust** — `SenderTrustScorer` in `gmail/sender_trust.py` is a SIGNAL only, never a hard filter. trust_level/score/reasons are stored in `email_messages` for observability. Shipping domain → HIGH (+4), ecommerce → HIGH (+3), generic → MEDIUM (+1), free email → LOW (−2), user-blocklisted → BLOCKED (−10). Scored per-email during ingestion with the user's current blocklist.

**Privacy** — never add body/full-text/PII columns to ORM models. Allowed to store: message_id, received_at, sender_domain, subject_hash, body_hash, extracted structured fields, short evidence snippets, query run metadata, sender trust metadata.

**Merge** — `can_merge_tracking_numbers()` in `domain/merge.py`. No LLM for merge decisions. ASO↔ECSA allowed; same carrier family with different IDs → deny.

**Chronology** — `SIDE_STATUSES` (action_required, payment_required, delayed_or_problem, unknown) never create conflicts. Only main-status regressions flagged.

**Rule ordering** — `action_required` fires before `ready_for_pickup`. Payment processor domains checked before text rules.

**SQLite NULL uniqueness** — `ShipmentEventRepository.insert_if_new` uses explicit SELECT (SQLite treats NULL≠NULL in unique constraints).

**Token missing** — `GmailOAuthManager.refresh_if_needed` raises `TokenMissingError`. CLI opens browser OAuth; API returns 401 + `auth_url`.

**Keywords are developer config** — `QueryVocabulary` in `config.py`. Do not expose keyword editing to users via API.

**Candidate match run indices** — `CandidateFetchResult.candidate_matches[i].query_run_id` holds the *index* into `query_runs` before `persist_fetch_result()` is called; it becomes the real DB id after. Do not confuse the two.

## Tests

```bash
python -m pytest tests/ -v   # 91 tests, all must pass
```

## Notebook playground

`notebooks/backend_playground.ipynb` — 4-part flow using backend imports.

**Cell execution order matters:**
1. Setup cell + DB setup cell — must run first (creates `config`, `session_factory`)
2. Part 1: auth → query config (loads domain prefs from DB) → fetch → persist observability → download → inspect
3. Part 2: preprocessing (can reload from `data/emails.json` without re-downloading)
4. Part 3: model classification
5. Part 4: persistence + dashboard (reuses `session_factory` from step 1)
