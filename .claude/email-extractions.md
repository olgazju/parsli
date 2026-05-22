# Email Extractions — How It Works

This document traces the full lifecycle of email extraction in Parsli: from the
Google Cloud credentials file on disk to a deduplicated, trust-scored list of
candidate message IDs ready for processing, with every step observable in the
database.

---

## Recent changes (2026-05-22)

- **Hebrew footer stripping** (`processing/cleaner.py`) — three `_HEBREW_FOOTER_RES` patterns strip mailing-system boilerplate (`הודעה זו נשלחה ל-…`, `נשלח באמצעות…`, `מערכת דיוור…`) before any analysis.
- **Billing invoice detection** (`processing/rule_engine.py`) — `_INVOICE_RE` expanded with `פירוט חיובים|חיובים תקופתיים`; periodic-billing emails (e.g. Moovit/Pango) are classified `is_invoice=True`.
- **Gmail billing exclusions** (`config.py`) — `"פירוט חיובים"` and `"חיובים תקופתיים"` added to `QueryVocabulary.exclude_terms`; these emails are not downloaded at all.
- **Context-guarded tracking extraction** (`domain/identifiers.py`) — FedEx (15-digit) and DHL (10–11 digit) pure-numeric patterns now require a shipping keyword within 150 chars. `TrackingIdentifier` gains a `source` field (`"body"` or `"body_near_keyword"`). Format-specific carriers (UPS, Israel Post, HFD, ASOS) are unaffected.
- **ASOS↔HFD merge removed** (`domain/merge.py`) — the hardcoded `ASO*↔ECSA*` cross-family merge rule is gone. `can_merge_tracking_numbers` now: identical → merge, same family + different ID → deny, different families → deny. No merchant-specific merge rules remain.

---

## 1. Credentials and OAuth

### 1.1 `credentials.json`

Before any Gmail API call can happen you need a Google Cloud OAuth 2.0 client
secret file. Download it from **Google Cloud Console → APIs & Services →
Credentials → OAuth 2.0 Client IDs → Download JSON** and place it at:

```
.parsli/credentials.json
```

`AppConfig.credentials_path` resolves to `app_dir / "credentials.json"`.
`GmailOAuthManager.is_configured` returns `True` only when this file exists.

The file contains: `client_id`, `client_secret`, `redirect_uris`, `auth_uri`,
`token_uri`. It never contains user tokens — it is a shared OAuth app identity.

### 1.2 Token files

After a user completes the OAuth consent screen, `GmailOAuthManager` persists
the resulting access + refresh tokens as a JSON file under:

```
.parsli/tokens/<16-char-sha256-prefix>.json
```

The filename is the first 16 hex characters of `sha256(email.lower())`. The
email address is stored **inside** the JSON under the key `"account_id"` — not
in the filename — so the filesystem never exposes the user's email address.

Token JSON structure:

```json
{
  "account_id": "user@example.com",
  "token": "<access-token>",
  "refresh_token": "<refresh-token>",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "...",
  "client_secret": "...",
  "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
  "expiry": "2026-05-22T14:00:00"
}
```

### 1.3 `GmailOAuthManager` — `gmail/auth.py`

Key methods:

| Method | What it does |
|---|---|
| `start_auth_flow(redirect_uri)` | Creates a `google_auth_oauthlib.Flow`, returns `(auth_url, state)`. Stores the pending flow in memory keyed by `state`. |
| `complete_auth_flow(code, state)` | Exchanges code for credentials, calls `users.getProfile` to resolve the email address, returns `(email, credentials)`. |
| `refresh_if_needed(account_id)` | Loads token from disk, refreshes via Google if expired, saves back. Raises `TokenMissingError` if no token file exists. |
| `list_token_accounts()` | Reads all `*.json` files in `tokens_dir`, returns the `account_id` value from each. |
| `_token_path(account_id)` | Private. Computes the hashed filename: `sha256(account_id.lower())[:16].json`. |

`TokenMissingError` is the standard signal that the caller (CLI or API) needs
to trigger a new OAuth flow — it carries the `account_id` that failed.

---

## 2. Configuration

### 2.1 `AppConfig` — `config.py`

`AppConfig` is a Pydantic `BaseSettings` that reads from env vars with prefix
`PARSLI_` and double-underscore nesting (`PARSLI_GMAIL__LOOKBACK_DAYS=90`).

```
AppConfig
├── app_dir              Path to .parsli/
├── gmail: GmailConfig
│   ├── lookback_days    How many days back to search (default 60)
│   ├── query_category_filter  Optional Gmail category clause, e.g.
│   │                          "(category:updates OR category:primary)"
│   └── vocabulary: QueryVocabulary
├── model: ModelConfig   LLM provider, model name, endpoint URL
├── privacy: PrivacyConfig
│   ├── debug_store_email_artifacts  If True, stores raw JSON + body to disk
│   └── evidence_max_chars           Max chars in status_evidence fields
├── processing: ProcessingConfig
└── database: DatabaseConfig
```

### 2.2 `QueryVocabulary` — keyword groups

`QueryVocabulary` is developer-controlled config — **never exposed to users via
the API**. It groups keywords into named buckets so the query builder can emit
separate targeted queries instead of one large OR clause:

| Group | Purpose |
|---|---|
| `strong_shipping` | High-confidence shipping signals: `"shipped"`, `"tracking number"`, `"out for delivery"`, Hebrew equivalents |
| `package_words` | Direct package references: `"your package"`, `"your shipment"`, `"חבילה"`, `"משלוח"` |
| `order_lifecycle` | Order-confirmation phrases: `"order confirmation"`, `"thanks for your order"`, `"אישור ההזמנה"` |
| `weak_phrases` | Low-precision phrases: `"on its way"`, `"your order"` — noisy, needs extra exclusions |
| `exclude_terms` | Applied to every query: `"פרסומת"` (ad), `"חשבונית מס"` (tax invoice), `"unsubscribe"`, `"booking"`, `"ticket"` |
| `weak_phrase_exclusions` | Extra exclusions only for `weak_phrases`: `"your request"`, `"request is on its way"` |
| `default_exclude_domains` | Payment processors excluded at query level: `paypal.com`, `stripe.com`, `payplus.co.il`, `cardcom.co.il`, `tranzila.com`, `isracard.co.il`, `booking.com` |

---

## 3. Domain Preferences

`DomainPreferences` (`gmail/models.py`) is user-managed state loaded from the
`domain_preferences` DB table via `DomainPreferenceService`.

```python
class DomainPreferences(BaseModel):
    allowlist: list[str] = []       # domains to get a dedicated allowlist query
    blocklist: list[str] = []       # domains added as -from: to all queries
    exclude_senders: list[str] = [] # specific email addresses to exclude
```

How each list is used:

- **`blocklist`** — adds `-from:<domain>` to every query. Belt-and-suspenders:
  these are also filtered by `RuleEngine._PAYMENT_PROCESSOR_DOMAINS` at
  classification time.
- **`allowlist`** — triggers a 4th query `allowlisted_domains` restricted to
  those senders only (see §4 below).
- **`exclude_senders`** — adds `-from:<email>` for each address. Used to
  prevent the account owner's own sent-mail from appearing in results. In
  `SyncService.initial_sync()` and in the notebook query-config cell, the
  account's own email is auto-added here on first run.

`DomainNormalizer.normalize()` sanitises user input: strips `@`, URL scheme,
port, path components, and lowercases before storing.

---

## 4. Query Building — `GmailQueryBuilder`

`gmail/query_builder.py` · `build_queries() → list[BuiltGmailQuery]`

The builder is instantiated with `GmailConfig` + `DomainPreferences`, then
`build_queries()` is called once per sync. It computes the `after:` cutoff date
from `lookback_days` and constructs up to **4 named queries**:

### Query anatomy

Every query follows this template:

```
[category_filter] (KEYWORD_OR_CLAUSE) -EXCLUDE_TERM_1 -EXCLUDE_TERM_2
-from:default_exclude_domain_1 ... -from:blocklist_domain ...
-from:exclude_sender_address ... after:YYYY/MM/DD
```

### The 4 named queries

**`strong_shipping`**

```
(shipped OR delivered OR "tracking number" OR "out for delivery" OR
 "estimated delivery" OR dispatch OR customs OR "מספר מעקב" OR נשלח
 OR "מוכן לאיסוף" OR "יצא לדרך" OR "your package" OR "your shipment"
 OR "your parcel" OR חבילה OR משלוח)
-פרסומת -"סיכום חודש" -"חשבונית מס" ... -"unsubscribe" -"booking" ...
-from:paypal.com -from:stripe.com ... -from:USER_BLOCKLIST ...
-from:USER_EXCLUDE_SENDERS ...
after:2026/03/22
```

**`order_lifecycle`**

```
("order confirmation" OR "thanks for your order" OR
 "your order has shipped" OR "your order is on its way" OR
 "אישור ההזמנה" OR "הזמנתך התקבלה")
-... exclusions ... after:YYYY/MM/DD
```

**`weak_phrases`**

```
("on its way" OR "your order")
-"your request" -"request is on its way"   ← extra exclusions
-... shared exclusions ... after:YYYY/MM/DD
```

**`allowlisted_domains`** *(only when allowlist is non-empty)*

```
(shipment OR order OR tracking OR delivery OR parcel OR משלוח OR הזמנה)
(from:trusted-shop.com OR from:another-store.co.il)
-... shared exclusions ... after:YYYY/MM/DD
```

### `BuiltGmailQuery` DTO

```python
class BuiltGmailQuery(BaseModel):
    name: str           # "strong_shipping", "order_lifecycle", etc.
    query: str          # the full Gmail search string
    terms: list[str]    # keyword terms used
    exclude_terms: list[str]
    exclude_domains: list[str]
```

---

## 5. Fetching Candidates — `GmailCandidateFetcher`

`gmail/candidate_fetcher.py` · `fetch() → CandidateFetchResult`

This class is **pure network I/O** — no DB access. It runs each named query
against the Gmail API, deduplicates the results, and packages everything for
the caller to persist.

### Execution flow

```
1. Generate UUID → fetch_batch_id
   (groups all queries from this one fetch() call together)

2. For each BuiltGmailQuery (in order: strong_shipping, order_lifecycle,
   weak_phrases, allowlisted_domains):
     a. Record started_at
     b. Call GmailClient.list_message_ids(query)
        → paginated Gmail API call, maxResults=500 per page
     c. Record finished_at, result_count
     d. Create QueryRunDTO with timing + count
     e. For each message_id returned:
          - Add query_name to sources_by_id[message_id]
          - Create CandidateMatchDTO(email_id, query_run_id=run_idx, ...)

3. Build summary: unique count, multi-query match count, per-query counts
4. Return CandidateFetchResult
```

### Deduplication

`sources_by_id: dict[str, list[str]]` tracks every query name that returned
each message ID. A message appearing in 3 queries gets one entry in
`message_ids` but 3 entries in `candidate_matches`. This is the foundation for
per-query observability.

### Critical: run index vs. DB id

`CandidateMatchDTO.query_run_id` holds the **index** (0, 1, 2…) of the query
run in `query_runs` at fetch time — **not a DB id**. The index is resolved to a
real DB primary key by `persist_fetch_result()` after inserting the run rows.
Never confuse the two; the resolution is a one-way operation done exactly once.

### `CandidateFetchResult` structure

```python
class CandidateFetchResult(BaseModel):
    message_ids: list[str]
    # {"msg_id": ["strong_shipping", "weak_phrases"], ...}
    query_sources_by_message_id: dict[str, list[str]]
    summary: CandidateFetchSummary
    query_runs: list[QueryRunDTO]      # one per named query, with timing
    candidate_matches: list[CandidateMatchDTO]  # one per (email, query) pair
```

```python
class CandidateFetchSummary(BaseModel):
    fetch_batch_id: str
    total_unique_candidates: int
    multi_query_matches: int           # matched by >1 query
    query_result_counts: dict[str, int]  # {"strong_shipping": 52, ...}
```

---

## 6. Observability — Persisting Run Data

`services/candidate_observability_service.py`

### `persist_fetch_result(session, result)`

Called immediately after `fetcher.fetch()` — before anything else writes to the
DB in that session.

```
1. Insert each QueryRunDTO → gmail_query_runs table
   → get back list of real DB ids: [run_db_ids[0], run_db_ids[1], ...]

2. For each CandidateMatchDTO:
   resolved_match = match.model_copy(update={
       "query_run_id": run_db_ids[match.query_run_id]  # index → real id
   })

3. Bulk-insert all resolved matches → gmail_candidate_matches table
```

### DB tables

**`gmail_query_runs`**

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `fetch_batch_id` | UUID string | Groups all queries from one `fetch()` |
| `query_name` | str | `strong_shipping`, `order_lifecycle`, etc. |
| `query_string` | str | The full Gmail query that was run |
| `started_at` | datetime | |
| `finished_at` | datetime | |
| `result_count` | int | Raw count before deduplication |

**`gmail_candidate_matches`**

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `email_id` | str | Gmail message ID |
| `query_run_id` | FK → `gmail_query_runs.id` | Resolved from run index |
| `fetch_batch_id` | UUID string | Denormalised for fast batch queries |
| `query_name` | str | Which named query matched this message |
| `matched_at` | datetime | |

### `CandidateObservabilityService` — read-only helpers

```python
svc = CandidateObservabilityService(session)

# Which queries ever matched a specific message?
svc.queries_for_email("19ccd4b806a9c1b0")
# → ["strong_shipping", "weak_phrases"]

# Which emails were matched exclusively by weak_phrases (nothing else)?
svc.emails_exclusive_to_query("weak_phrases")
# → ["abc123", "def456", ...]

# Which emails were matched by more than one query in the latest batch?
svc.emails_matching_multiple_queries()
# → ["ghi789", ...]
```

All methods default to the latest `fetch_batch_id` when none is specified.
Use `svc.latest_batch_id()` to get it explicitly.

---

## 7. Ingestion — `GmailIngestor`

`gmail/ingestor.py`

Fetches the full raw message from Gmail for each new candidate and writes a
minimal metadata row to `email_messages`. **Raw bodies, full text, and PII are
never written to the database.**

### Two ingestion entry points

**`ingest_from_candidates(result: CandidateFetchResult)`** — preferred after a
`fetch()` call. Reads `query_sources_by_message_id` and stores the
comma-joined query names in `email_messages.query_source`, e.g.
`"strong_shipping,order_lifecycle"`.

**`ingest_many(message_ids, query_source=None)`** — used by incremental sync
where the source is just `"incremental_sync"`.

### Per-message flow (`_ingest_one`)

```
1. Check if message_id already exists in email_messages
   → if yes: touch last_seen_at via upsert and return was_new=False

2. GmailClient.fetch_raw(message_id)
   → full Gmail API call, returns raw JSON payload
   → DebugStore.store_raw_email() if debug mode is on (default: off)

3. Extract headers: Subject, From, internalDate, threadId

4. Compute:
   - received_at = datetime from internalDate (milliseconds → UTC)
   - sender_domain = extract_sender_domain(From header)
     e.g. "Amazon <ship@amazon.com>" → "amazon.com"
   - subject_hash = sha256(subject)[:12]   (stored; subject itself is not)
   - body_hash = sha256(full plain text)[:32]  (stored; body is not)

5. SenderTrustScorer.score(sender_domain) → SenderTrustResult

6. Write EmailMessage row via EmailMessageRepository.upsert()
```

### What is stored in `email_messages`

```
email_id              Gmail message ID (PK)
account_id            FK to email_accounts
thread_id             Gmail thread ID
received_at           UTC datetime from internalDate
sender_domain         "amazon.com", "israelpost.co.il", etc.
subject_hash          12-char sha256 prefix
body_hash             32-char sha256 of full extracted plain text
query_source          "strong_shipping,weak_phrases" (comma-joined)
sender_trust_level    "high" | "medium" | "low" | "blocked"
sender_trust_score    int score
sender_trust_reasons_json  JSON array of reason strings
```

Everything else — raw HTML, full body text, subject text, From header, recipient
address — is discarded immediately after hashing. `subject_debug` is populated
only when `privacy.debug_store_email_artifacts = True`.

---

## 8. Sender Trust Scoring

`gmail/sender_trust.py`

`SenderTrustScorer` is a **signal layer** — it scores senders during ingestion
for observability but never filters or blocks messages at this stage (that
happens later in `RuleEngine`).

### Scoring logic

```
sender_domain in user_blocklist  → BLOCKED  (score −10)
sender_domain in KNOWN_SHIPPING_DOMAINS   → HIGH   (score +4)
sender_domain in KNOWN_ECOMMERCE_DOMAINS  → HIGH   (score +3)
sender_domain in FREE_EMAIL_PROVIDER_DOMAINS → LOW (score −2)
otherwise                                 → MEDIUM (score +1)
```

Domain lists live in the file itself and include hundreds of known senders
(Israel Post, DHL, FedEx, Amazon, ASOS, etc. and their country variants).

The `SenderTrustScorer` is instantiated with the current user `blocklist` as a
frozen set:

```python
trust_scorer = SenderTrustScorer(
    user_blocklist=frozenset(domain_prefs.blocklist)
)
```

Scores are stored in `email_messages` and surfaced in the notebook for
inspection. They feed future features like automatic skip-processing of BLOCKED
senders, but today they are observe-only.

---

## 9. End-to-End Flow Summary

```
credentials.json  (Google Cloud OAuth client secret, never changes)
        │
        ▼
GmailOAuthManager.refresh_if_needed(account_id)
        │  ← tokens/<sha256[:16]>.json (per-account, hashed filename)
        ▼
GmailClient(credentials)          ← google-api-python-client wrapper

DomainPreferenceService(session)  ← reads domain_preferences table
        │  (allowlist, blocklist, exclude_senders)
        ▼
GmailQueryBuilder(config, domain_prefs)
        │  ← QueryVocabulary (developer-controlled keyword groups)
        ▼
.build_queries() → [BuiltGmailQuery × 3–4]
        │
        ▼
GmailCandidateFetcher(client, builder)
.fetch() ──────────────────────────────────────────────────────────────┐
  • generates fetch_batch_id (UUID)                                     │
  • for each named query:                                               │
      GmailClient.list_message_ids(query) → [msg_id, ...]  (paginated) │
      record QueryRunDTO (timing, result_count)                         │
      record CandidateMatchDTO per (email_id, query_name) pair         │
  • deduplicates across queries → sources_by_id                        │
  • returns CandidateFetchResult                                        │
└──────────────────────────────────────────────────────────────────────┘
        │
        ▼
persist_fetch_result(session, result)
  • inserts gmail_query_runs rows → get real DB ids
  • resolves CandidateMatchDTO.query_run_id (index → DB id)
  • inserts gmail_candidate_matches rows
        │
        ▼
GmailIngestor.ingest_from_candidates(result)
  for each message_id:
    • skip if already in email_messages
    • GmailClient.fetch_raw() → full Gmail API call
    • extract headers, compute hashes, score sender trust
    • write EmailMessage (metadata only, no body)
        │
        ▼
email_messages table  ←  ready for EmailProcessingService
```

---

## 10. Initial vs. Incremental Sync

Both paths share the same ingestion chain. The difference is in how message IDs
are obtained.

**Initial sync** (`SyncService.initial_sync`):
- Runs `GmailCandidateFetcher.fetch()` with the full lookback window
- After ingestion, stores `last_history_id` from `users.getProfile` so
  incremental sync has a starting point
- Auto-adds the account's own email to `exclude_senders` if not already present

**Incremental sync** (`SyncService.incremental_sync`):
- Calls `GmailClient.get_history(start_history_id)` → Gmail History API
  returns only message IDs added since that checkpoint
- Ingests via `ingestor.ingest_many(new_ids, query_source="incremental_sync")`
  (no named-query breakdown — just the word `"incremental_sync"`)
- Updates `last_history_id` to the new value returned by the History API

Both call `_process_and_resolve()` after ingestion to run `EmailProcessingService`
and `ShipmentResolutionService` on any unprocessed messages.
