# parsli

Local-first parcel tracking — extracts shipment status from Gmail using local AI models.

## Backend

### Requirements

- Python 3.12+
- [pyenv](https://github.com/pyenv/pyenv) with the `parcli` virtualenv (created automatically if you follow the steps below)
- A local model running via [LM Studio](https://lmstudio.ai) or [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
- A Google Cloud project with the Gmail API enabled and `credentials.json` downloaded

### Setup

```bash
# 1. Install dependencies
cd backend
make install-dev

# 2. Place credentials.json in the app directory
mkdir -p .parsli
cp ~/Downloads/credentials.json .parsli/credentials.json

# 3. (Optional) create a .env file to override defaults
cat > .env <<EOF
PARSLI_GMAIL__LOOKBACK_DAYS=60
PARSLI_MODEL__PROVIDER=lmstudio
PARSLI_MODEL__MODEL_NAME=google/gemma-4-e4b
PARSLI_MODEL__ENDPOINT_URL=http://localhost:1234
EOF
```

### Make targets

All commands run from the `backend/` directory.

| Target | What it does |
|---|---|
| `make install` | Install the package (no dev deps) |
| `make install-dev` | Install the package + pytest |
| `make test` | Run the test suite |

`make install` and `make install-dev` both set `PIP_UPLOADED_PRIOR_TO` to 7 days ago, so pip refuses to install any package uploaded to PyPI less than 7 days before you run the command. This guards against supply-chain attacks via freshly published malicious releases.

> **Linux note:** the Makefile uses BSD `date -v-7d` (macOS). On Linux change line 4 to `date -d '7 days ago' +%F`.

### Run the server

```bash
parsli serve
# API available at http://localhost:8000
# Frontend served at http://localhost:8000/
```

### Sync Gmail

```bash
# First run — fetches the last N days of email
parsli sync <account-id-or-email> --mode initial

# Subsequent runs — only new messages since last sync
parsli sync <account-id-or-email>
```

If no Gmail token exists, the browser opens automatically for OAuth consent.

### Other commands

```bash
# Rebuild all shipment timelines from existing events (after rule changes)
parsli rebuild

# Verbose logging
parsli -v sync <account-id>
```

### API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/status` | App readiness + credentials check |
| `GET` | `/api/dashboard` | Full dashboard with all shipments |
| `GET` | `/api/shipments` | List shipments |
| `GET` | `/api/shipments/{id}` | Single shipment |
| `POST` | `/api/accounts/connect` | Start Gmail OAuth flow |
| `POST` | `/api/sync/initial/{id}` | Full lookback sync |
| `POST` | `/api/sync/incremental/{id}` | Incremental sync |

### Tests

```bash
cd backend
make test
```

## Code review

Parsli ships a project-level Claude Code slash command that reviews code against the project's specific conventions — privacy rules, Pydantic v2 patterns, SQLAlchemy 2.x idioms, domain model constraints, and more.

### Run a review

Open this project in [Claude Code](https://claude.ai/code) (CLI or IDE extension), then:

```
# Review everything changed since the last commit
/parsli-review

# Review specific files
/parsli-review backend/src/parsli/processing/rule_engine.py

# Review multiple files
/parsli-review backend/src/parsli/db/repositories.py backend/src/parsli/services/sync_service.py
```

The command runs a dedicated review agent that outputs issues as `[BLOCKER]`, `[WARN]`, or `[HINT]` with file:line references, then a one-line summary count.

### What it checks

| # | Section |
|---|---|
| 1 | **Privacy** — no raw body/HTML in DB, `DebugStore` guard, evidence clipping |
| 2 | **Type safety** — return annotations, `X \| None` syntax, lowercase generics |
| 3 | **Pydantic v2** — `BaseModel` not dataclass, `model_validate`, `default_factory` |
| 4 | **SQLAlchemy 2.x** — `Mapped[T]`, no raw SQL, SQLite NULL-in-unique-constraint gotcha |
| 5 | **Domain model** — status rules, terminal `DELIVERED`, no AI in merge decisions |
| 6 | **Rule ordering** — `ACTION_REQUIRED` before `READY_FOR_PICKUP`, no shadowing |
| 7 | **Services** — `TokenMissingError`, idempotency, `insert_if_new` |
| 8 | **Model clients** — Protocol match, lazy connections, no DB writes |
| 9 | **Code style** — no redundant comments, `logging` not `print`, no compat shims |
| 10 | **Tests** — in-memory SQLite, no DB mocks, new behaviour needs a test |

The full checklist lives in [`.claude/commands/parsli-review.md`](.claude/commands/parsli-review.md).

## Notebook playground

`notebooks/backend_playground.ipynb` mirrors the original `compare_ollama_vs_lmstudio.ipynb` flow but imports all logic from the backend package — no reimplementation inline.

**Parts:**

1. **Gmail auth + download** — `GmailOAuthManager`, `GmailClient`, `GmailQueryBuilder`. Opens a browser OAuth tab automatically if no token exists.
2. **Preprocessing** — `EmailCleaner` (HTML stripping, boilerplate removal) + `RuleEngine` (deterministic Hebrew/English rules). No model calls.
3. **Model classification** — `ModelClientFactory` selects LM Studio or llama-cpp. Rule-first loop; model is called only for ambiguous rows.
4. **Persistence** — `ShipmentResolutionService` resolves canonical shipment IDs, inserts events idempotently, rebuilds timelines. `DashboardService` renders the final view.

**Run:**

```bash
cd backend
pip install -e ".[notebook]"   # installs pandas + jupyter

cd ../notebooks
jupyter notebook backend_playground.ipynb
```

Emails are cached to `notebooks/data/emails.json` and results to `notebooks/data/results.csv` so you can re-run individual parts without re-downloading or re-running the model.