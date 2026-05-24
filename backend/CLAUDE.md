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
                         LanguageConfig — enabled language codes (default ["en", "he"])
                         GmailConfig — structural Gmail settings (lookback_days, default_exclude_domains)
  languages/             Language pack system
    __init__.py          LanguagePack, MergedLanguageConfig, StatusPatterns,
                         load_language_packs(codes) → MergedLanguageConfig,
                         DEFAULT_LANGUAGES = ["en", "he"]
    en.yaml              English shipping signals, status phrases, query terms,
                         footer patterns, billing phrases, order label regex
    he.yaml              Hebrew equivalents
  domain/                Pure domain objects — no I/O
    statuses.py          ShipmentStatus enum + SIDE_STATUSES / TERMINAL_STATUSES
    identifiers.py       TrackingIdentifier (value, carrier_hint, confidence, source),
                         OrderIdentifier, IdentifierExtractor class (accepts MergedLanguageConfig),
                         module-level extract_tracking_candidates / extract_order_candidates
                         (backward-compat wrappers over lazy-default extractor)
                         FedEx/DHL require nearby shipping context (_CONTEXT_REQUIRED)
    carriers.py          CarrierFamily detection from tracking number or domain
    email_types.py       EmailType enum (order_confirmation | shipping_update | pickup_ready |
                         delivered | payment_problem | billing_only | non_shipping | digital_product)
                         email_type_from_status(status, is_invoice) → EmailType
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
    query_builder.py     GmailQueryBuilder(config, domain_preferences, lang_config).build_queries()
                         → list[BuiltGmailQuery]
                         All query terms come from MergedLanguageConfig.query_include_terms
                         (no longer from QueryVocabulary). Defaults to DEFAULT_LANGUAGES.
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
    cleaner.py           EmailCleaner(lang_config) → CleanedEmail
                         Builds footer/unsubscribe/shipping-signal patterns from MergedLanguageConfig.
                         Defaults to load_language_packs(DEFAULT_LANGUAGES) when omitted.
                         CleanedEmail carries subject: str = "" and sender_domain: str | None = None
                         (model-prompt context — never persisted to DB)
    rule_engine.py       RuleEngine(lang_config) → RuleExtractionResult
                         Builds _invoice_re, _invoice_negative_re, _status_rules, and an
                         IdentifierExtractor dynamically from MergedLanguageConfig.
                         Defaults to load_language_packs(DEFAULT_LANGUAGES) when omitted.
                         sender_domain checked first — payment processors → is_invoice=True
                         ACTION_REQUIRED rule fires before READY_FOR_PICKUP
    model_classifier.py  ModelClassifier(model_client, model_provider, model_name,
                         model_config, debug_store)
                         select_mode(rules, cleaned, sender_trust_level) → ModelExecutionMode
                         classify(cleaned, mode, rules) → (ModelClassificationResult | None,
                         ModelCallObservability)
                         Modes: MODEL_REQUIRED (full prompt, required_max_chars),
                         MODEL_AUDIT (lightweight agreement, audit_max_chars), SKIP_MODEL
    reconciler.py        ClassificationReconciler.reconcile(rules, model, obs, cleaned, ...)
                         → FinalClassificationResult
                         DecisionSource enum: RULE | MODEL | RULE_MODEL_AGREE | MODEL_OVERRIDE |
                         RULE_OVERRIDE | SEMANTIC_GUARD | REVIEW_NEEDED | MODEL_FALLBACK
                         FinalClassificationResult: email_type, rule_email_type, model_email_type,
                         status, rule_status, model_status, status_confidence, rule_confidence,
                         model_confidence, decision_source, conflict_reason, needs_review,
                         rule_model_agreed, confidence_delta, classification_method,
                         plus identifiers, merchant, carrier, provenance, observability
    extraction_orchestrator.py  Wires ModelClassifier → ClassificationReconciler → persistence
                         FinalExtraction = FinalClassificationResult (backward-compat alias)
                         orchestrate(cleaned, rules, sender_trust_level) → FinalClassificationResult
    pipeline.py          EmailProcessingPipeline (wires cleaner→rules→orchestrator)
  model/
    base.py              LocalModelClient Protocol
                         ModelClassificationResult (email_type, status, status_confidence,
                         status_evidence, merchant, carrier, tracking_numbers, order_numbers,
                         pickup_code, amount, currency, reasoning)
                         ModelAuditResult (agrees, email_type, status, status_confidence, reason)
                         ModelExtractionResult = ModelClassificationResult (backward-compat alias)
    prompts.py           format_required_prompt(subject, sender_domain, email_text) → str
                         format_audit_prompt(subject, sender_domain, preview, rule_email_type,
                         rule_status, rule_confidence, rule_evidence, tracking_candidates,
                         order_candidates) → str
                         build_model_text_preview(cleaned_text, max_chars) → str
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
    dashboard_projection_service.py  DashboardProjectionService
                         get_dashboard_projection() → DashboardProjection
                         get_shipment_detail(canonical_id) → ShipmentDetailProjection | None
                         Read-only — never writes. Builds UI-ready projections
                         from pre-resolved shipments, events, and extractions.
    domain_preference_service.py  add/remove allowlist and blocklist domains
    candidate_observability_service.py
                         persist_fetch_result(session, result) — resolves run indices to
                         DB ids and inserts GmailQueryRun + GmailCandidateMatch rows
                         CandidateObservabilityService — queries_for_email(),
                         emails_exclusive_to_query(), emails_matching_multiple_queries()
  api/
    main.py              create_app(config) factory
    routes_dashboard.py  GET /api/dashboard, /api/dashboard/projection,
                         /api/shipments, /api/shipments/{id},
                         /api/shipments/{id}/detail
    routes_sync.py       POST /api/sync/initial|incremental, GET /api/status
    routes_settings.py   GET/POST/DELETE /api/settings/domains/allowlist|blocklist
  cli.py                 parsli serve | sync | rebuild
```

## Language pack system

All locale-specific phrases live in `src/parsli/languages/<code>.yaml`. The core processing
components are language-agnostic — they accept a `MergedLanguageConfig` and build their
compiled patterns at construction time.

```python
from parsli.languages import load_language_packs, DEFAULT_LANGUAGES

lang = load_language_packs(["en", "he"])   # merge two packs
lang = load_language_packs(["en"])         # English-only: Hebrew rules invisible
```

`AppConfig.language.enabled` (default `["en", "he"]`) controls which packs are loaded by
`EmailProcessingService`. To add a new language: create `<code>.yaml`, add the code to
`enabled_languages`. No Python changes required.

Each YAML pack defines: `shipping_signals`, `footer_patterns`, `unsubscribe_patterns`,
`billing_exclusion_phrases`, `shipping_override_phrases`, `tracking_context_words`,
`order_label_patterns`, `query_include_terms`, `query_exclude_terms`,
`query_weak_phrase_exclusions`, `allowlist_broad_terms`, `status_patterns`.

## Gmail candidate query design

`GmailQueryBuilder.build_queries()` emits up to 4 named queries instead of one large OR.
Query terms come entirely from `MergedLanguageConfig.query_include_terms`:

| Query name | Terms used | Notes |
|---|---|---|
| `strong_shipping` | `strong_shipping` + `package_words` groups | High-confidence signals |
| `order_lifecycle` | `order_lifecycle` group | Order confirmation/shipped phrases |
| `weak_phrases` | `weak_phrases` group + extra exclusions | Low-precision, extra noise filtering |
| `allowlisted_domains` | `allowlist_broad_terms` + `from:domain` restriction | Only when allowlist is non-empty |

Every query includes: `query_exclude_terms` from active packs, `-from:` for all
`GmailConfig.default_exclude_domains` and user blocklist, `after:<date>`.

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

**Merge** — `can_merge_tracking_numbers()` in `domain/merge.py`. No LLM for merge decisions. No merchant-specific merge rules. Identical tracking → merge; same carrier family, different IDs → deny; different families → deny.

**Chronology** — `SIDE_STATUSES` (action_required, payment_required, delayed_or_problem, unknown) never create conflicts. Only main-status regressions flagged.

**Rule ordering** — `action_required` fires before `ready_for_pickup`. Payment processor domains checked before text rules.

**Billing exclusion** — `billing_exclusion_phrases` in language packs (`he.yaml`: `פירוט חיובים`, `חיובים תקופתיים`; `en.yaml`: `invoice`, `billing statement`, …) feed `_INVOICE_RE` in `RuleEngine`. The same Hebrew phrases appear in `he.yaml: query_exclude_terms` so periodic-billing emails are not downloaded at all.

**Tracking extraction context guard** — FedEx (15-digit) and DHL (10–11 digit) patterns in `domain/identifiers.py` require a shipping keyword within 150 chars. Context words come from `MergedLanguageConfig.tracking_context_words` (built by `IdentifierExtractor`). Pure-digit matches without context (phone numbers, billing IDs) are silently dropped. Format-specific carriers (UPS, Israel Post, HFD, ASOS) are extracted globally — no context guard. `TrackingIdentifier.source` carries `"subject"` (found in subject line), `"body_near_keyword"` (adjacent to a shipping keyword), or `"body"` (format match only). `RuleEngine` tags subject-found identifiers after extraction; `select_best_tracking` uses source as a secondary scoring dimension.

**Identifier selection** — `select_best_tracking` in `domain/identifiers.py` uses candidate-level scoring: structured carriers (non-numeric prefix: UPS, Israel Post, HFD, ASOS) beat generic numeric ones (FedEx, DHL); within the same structure tier, subject > body_near_keyword > body. No carrier-brand ranking. `ShipmentResolutionService._rebuild_shipment` applies the same principle via `_STRUCTURED_FAMILIES` when sorting tracking numbers for the `primary_tracking_number` display field.

**Resolution paths** — `ShipmentResolutionService.resolve_and_insert` splits on `email_type`: `order_confirmation` → creates order alias + `order_confirmed` event only (no tracking required); shipping types → looks up tracking alias, falls back to order+merchant alias, derives new canonical. Never skips dedup: events inserted via `ShipmentEventRepository.insert_if_new`.

**SQLite NULL uniqueness** — `ShipmentEventRepository.insert_if_new` uses explicit SELECT (SQLite treats NULL≠NULL in unique constraints).

**Token missing** — `GmailOAuthManager.refresh_if_needed` raises `TokenMissingError`. CLI opens browser OAuth; API returns 401 + `auth_url`.

**Language packs are developer config** — YAML packs in `src/parsli/languages/`. `AppConfig.language.enabled` selects active packs. Do not expose pack editing to users via API; the planned settings UI will only allow enabling/disabling whole language codes.

**Candidate match run indices** — `CandidateFetchResult.candidate_matches[i].query_run_id` holds the *index* into `query_runs` before `persist_fetch_result()` is called; it becomes the real DB id after. Do not confuse the two.

## Tests

```bash
python -m pytest tests/ -v   # 215 tests, all must pass
```

## Notebook playground

`notebooks/backend_playground.ipynb` — 5-part flow using backend imports.

**Cell execution order matters:**
1. Setup cell + DB setup cell — must run first (creates `config`, `session_factory`)
2. Part 1: auth → query config (loads domain prefs from DB) → fetch → persist observability → download → inspect
3. Part 2: preprocessing (can reload from `data/emails.json` without re-downloading)
4. Part 3: model classification
5. Part 4: persistence + dashboard (reuses `session_factory` from step 1)
6. Part 5: dashboard projection — `DashboardProjectionService.get_dashboard_projection()` summary,
   `get_shipment_detail(canonical_id)` detail view; use `INSPECT_IDX` variable to pick shipment
