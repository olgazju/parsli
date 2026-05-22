You are reviewing Parsli backend code. Parsli is a local-first, privacy-focused parcel tracking app.

Review the following files or diff: $ARGUMENTS

If no argument is given, review all staged and unstaged changes in the current git diff (`git diff HEAD`).

---

## What to review

Go through each checklist section below. For every issue found, output it as:

**[SEVERITY] filename:line — short description**
> Explanation and the fix to apply.

Severity levels: `BLOCKER` (must fix before merge) · `WARN` (should fix) · `HINT` (optional improvement).

At the end, print a one-line summary: total blockers / warnings / hints.

---

## 1. Privacy — MOST CRITICAL

These rules are non-negotiable. Flag any violation as BLOCKER.

- No raw email body, raw HTML, or full Gmail API response stored in any ORM model column or written to any file (unless inside `.parsli/debug/` and guarded by `DebugStore` which no-ops when `debug_store_email_artifacts=False`).
- No recipient email address, phone number, home address, payment details, or invoice contents persisted in the database.
- Columns allowed in `email_messages`: `email_id`, `thread_id`, `received_at`, `sender_domain`, `subject_hash`, `subject_debug` (debug-only), `body_hash`, `query_source`, `ingested_at`, `last_seen_at`.
- Evidence snippets stored in `email_extractions.status_evidence` must be clipped to `PrivacyConfig.evidence_max_chars` (default 240) using `clip_text()` before persistence.
- Any new debug artifact write must go through `DebugStore` — never a raw `Path.write_text()` outside of that class.

## 2. Type safety

- Every function and method must have a return type annotation. No bare `def f(x):`.
- No `Any` unless there is a clear reason (add a comment explaining why).
- No `Optional[X]` — use `X | None` (Python 3.10+ union syntax).
- No `List[X]`, `Dict[X, Y]`, `Tuple[X]` — use lowercase `list[X]`, `dict[X, Y]`, `tuple[X]`.
- `TypeVar` bounds must be `bound=BaseModel` when used with Pydantic models.

## 3. Pydantic v2

- All DTOs and domain objects inherit from `pydantic.BaseModel`, not `dataclasses.dataclass`.
- No `dataclasses.dataclass` anywhere in `src/parsli/` — flag as BLOCKER.
- Use `model_validate()` not `parse_obj()`. Use `model_dump()` not `dict()`.
- Field defaults that are mutable (lists, dicts) must use `Field(default_factory=...)`.
- `BaseSettings` subclasses use `SettingsConfigDict`; check `env_prefix` and `env_nested_delimiter` are set.
- `AppConfig` model fields use `Field(default_factory=...)`, not bare mutable defaults.

## 4. SQLAlchemy 2.x ORM

- All ORM models inherit from the project's `Base` (`DeclarativeBase` subclass in `db/models.py`).
- All columns use the new `Mapped[T]` + `mapped_column()` syntax — no `Column(...)` or old-style `db.Column`.
- No business logic inside ORM model classes — only column definitions and relationships.
- Repositories receive a `Session` and use `session.execute(select(...))`, `session.add()`, `session.get()` — no raw SQL strings unless there is a specific reason.
- Upserts use `sqlite_insert(...).on_conflict_do_update(...)` or `on_conflict_do_nothing()`.
- **SQLite NULL uniqueness gotcha**: `on_conflict_do_nothing()` does NOT deduplicate rows where nullable columns in the unique constraint are `NULL` (SQLite treats `NULL ≠ NULL`). Any `insert_if_new`-style method on a table with nullable unique-constraint columns must use an explicit `SELECT` before `INSERT` — check `ShipmentEventRepository.insert_if_new` as the reference implementation.

## 5. Domain model design

- `ShipmentStatus` values come from `domain/statuses.py` — no string literals like `"delivered"` used directly in logic.
- Side statuses (`ACTION_REQUIRED`, `PAYMENT_REQUIRED`, `DELAYED_OR_PROBLEM`, `UNKNOWN`) must never create chronology conflicts — they are excluded from the main-status linear ordering in `check_chronology()`.
- `DELIVERED` is terminal — no event of any other status may override it in `select_current_status()`.
- `UNKNOWN` must never override a known status in `select_current_status()`.
- Merge decisions (`can_merge_tracking_numbers`) are pure Python — no LLM calls allowed. Flag any AI/model call inside `domain/merge.py` as BLOCKER.
- `canonical_shipment_id()` in `domain/merge.py` must be deterministic: same `(alias_type, alias_value)` → same 16-char hex always.

## 6. Rule engine ordering

- In `processing/rule_engine.py`, `_STATUS_RULES` is evaluated top-to-bottom and the first match wins. More-specific or higher-urgency statuses must appear before general ones.
- `ACTION_REQUIRED` must appear before `READY_FOR_PICKUP` (HFD "collect before return" is more specific than a generic pickup notice).
- If a new rule is added, check that it does not shadow a more-specific rule that appears below it.

## 7. Service layer

- Services receive dependencies (session, config, repos) via `__init__` — no module-level singletons.
- `SyncService.initial_sync()` and `incremental_sync()` must raise `TokenMissingError` (not `ValueError` or `None`-return) when no valid OAuth token exists.
- `EmailProcessingService.process_new_emails()` must be idempotent: running it twice with the same emails must not create duplicate rows in `processed_emails` or `email_extractions`.
- `ShipmentResolutionService.resolve_and_insert()` must call `ShipmentEventRepository.insert_if_new()` (not a raw insert) to guarantee deduplication.

## 8. Model clients

- `LMStudioClient` and `LlamaCppClient` must implement the `LocalModelClient` Protocol — check that `extract(prompt, *, response_model)` signature matches exactly.
- No model client may make a network call at import time or `__init__` — connections are lazy.
- Model clients must not make merge decisions or write to the database.

## 9. Code style

- No unnecessary comments. A comment is justified only when the **why** is non-obvious (a hidden constraint, a workaround, a subtle invariant). "This function does X" comments on well-named functions → flag as HINT.
- No multi-paragraph docstrings or multi-line comment blocks. One short line max per docstring.
- No `print()` in library code (`src/parsli/`) — use `logging.getLogger(__name__)`. Flag as WARN.
- No backwards-compatibility shims: no unused `_var` renames, no `# removed` comments for deleted code, no re-exports of removed symbols.
- No feature flags or fallback code for scenarios that can't happen — trust internal invariants.
- Composition over inheritance: if a new class inherits from another application class (not a framework base like `BaseModel` or `DeclarativeBase`), flag as WARN and suggest composition.

## 10. Tests

- New behaviour (new status rule, new merge rule, new domain logic) should have a corresponding test in `tests/`.
- Tests must use in-memory SQLite (`create_engine("sqlite:///:memory:")`), never the real `.parsli/parsli.db`.
- No mocking of the database — integration-style tests against a real (in-memory) SQLite instance are required (per project convention).
- Test functions are plain `def`, not `async def`, unless there is a specific async reason.
