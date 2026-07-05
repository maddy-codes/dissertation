# Setup

## Prerequisites

- Python 3.10+
- Node.js (for the AI Chat feature's Xero MCP server — see below). Not required for every other feature.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

`pyproject.toml` pins the full Python dependency list. Notable ones beyond the obvious Flask stack: `crewai` + `langchain-openai` (present for an experimental, currently-unused synthesis pipeline — see [`ARCHITECTURE.md`](ARCHITECTURE.md#the-review-note-generation-pipeline)), `mcp` (the official Model Context Protocol SDK, for AI Chat), `apscheduler` (Cash Flow Accelerator autoscan), `reportlab` (PDF generation), `pyodbc` (Azure SQL), `crewai`/`gevent`/`gunicorn` (production process model).

### Node dependency (AI Chat only)

The AI Chat feature spawns the **official Xero MCP server** as a subprocess. Install it once:

```bash
npm install
```

This pulls `@xeroapi/xero-mcp-server` and applies a small patch (`patches/@xeroapi+xero-mcp-server+0.0.17.patch`, auto-reapplied via `patch-package`'s `postinstall` hook on every install) that lets the server honour a specific tenant via `XERO_TENANT_ID` — see [`ARCHITECTURE.md`](ARCHITECTURE.md#ai-chat-the-xero-mcp-bridge) for why this was necessary. If `node`/`npm` aren't available, every other feature still works; only `/chat` will fail.

## Environment variables

Copy `.env.example` to `.env` and fill in what you need — never commit real secrets. Nothing here is required just to browse the app with no data connected; each group below is only needed for the feature it names.

### Core Flask

| Variable | Purpose |
|---|---|
| `FLASK_SECRET_KEY` (or `SECRET_KEY`) | Session signing key. Without it, sessions won't survive a process restart (a random key is generated per-boot, with a warning). Set explicitly in production. |
| `FLASK_DEBUG` | `true`/`1` enables Flask's debug mode when running `python3 app.py` directly. |
| `LOG_LEVEL` | Python logging level (default `INFO`). |
| `DATABASE_CONNECTION_STRING` | SQLAlchemy connection string. Omitted → SQLite (`sqlite:///users.db`) in dev; **required** in production (`REPLIT_DEPLOYMENT` set) — refuses to silently fall back to SQLite there. Azure SQL connection strings are auto-sanitised (ODBC driver detection, `Encrypt=True→yes`, etc.). |
| `DATABASE_SCHEMA` | Non-default SQL schema name for all tables (Azure SQL deployments commonly use one). |

### Xero (all Xero-touching features)

| Variable | Purpose |
|---|---|
| `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET` | Your Xero app's OAuth2 credentials. |
| `XERO_REFRESH_TOKEN` | Only for the `XeroClient.from_env()` script/CLI path, not the web app (which stores per-user tokens in the DB). |
| `XERO_REDIRECT_URI` | OAuth2 callback URL, if not inferred. |
| `XERO_TOKEN_CACHE_PATH` | JSON file to persist a refreshed token when no `user` object is available (script usage only). |
| `XERO_MAX_RETRIES`, `XERO_MAX_BACKOFF_SECONDS` | Tuning for the 429 rate-limit retry/backoff in `XeroClient._get`. |

### Azure OpenAI / LLM

| Variable | Purpose |
|---|---|
| `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` | Azure OpenAI credentials. `MODEL_API_KEY`/`MODEL_AZURE_ENDPOINT`/`MODEL_OPENAI_ENDPOINT` are alternate names checked first by `helpers/openai_config.py` (some deployment templates set those instead). |
| `AZURE_OPENAI_API_VERSION` | API version string. |
| `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_DEPLOYMENT_NAME`, `FINAL_REVIEW_DEPLOYMENT_NAME` | Deployment name used for the final review-note synthesis calls. |
| `SCAN_DEPLOYMENT_NAME`, `AZURE_OPENAI_SCAN_DEPLOYMENT_NAME` | Deployment name used for the cheaper/faster "scan" calls (Workbench account-selection, Cash Flow Accelerator drafting, Chat). |
| `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_MAX_TOKENS`, `LLM_TOKEN_PARAM` | General LLM call tuning. |

### Cash Flow Accelerator

| Variable | Default | Purpose |
|---|---|---|
| `CASH_FLOW_TEST_INBOX` | *(required to send)* | Every "Send Outreach" click goes here, **never** to the real customer — a deliberate safety default for a firm-internal tool; see [`FEATURES.md`](FEATURES.md#cash-flow-accelerator). |
| `CASH_FLOW_DORMANT_DAYS` | `90` | Days of silence before a contact counts as "gone quiet" (Win-Back/Subscription signals). |
| `CASH_FLOW_REPEAT_MIN_INVOICES` | `3` | Minimum invoice count to qualify as a Subscription Candidate. |
| `CASH_FLOW_TOP_N` | `12` | Max opportunities shown per scan (round-robin across all 6 types — see ARCHITECTURE.md). |
| `CASH_FLOW_HISTORY_LIMIT` | `20` | How many past generation runs to keep in a tenant's history. |
| `CASH_FLOW_UNDERPERFORMING_WINDOW_DAYS` | `180` | Rolling window length for the underperforming-product comparison. |
| `CASH_FLOW_UNDERPERFORMING_DECLINE_THRESHOLD` | `0.4` | Minimum fractional revenue decline to flag. |
| `CASH_FLOW_UNDERPERFORMING_MIN_PRIOR_REVENUE` | `50` | Ignore items too small to be a meaningful signal. |
| `CASH_FLOW_CROSS_SELL_TOP_N` | `5` | How many top revenue lines are considered "popular enough" to cross-sell. |
| `CASH_FLOW_LATE_RISK_MIN_HISTORY` | `2` | Minimum settled invoices before scoring a contact's payment-lateness history. |
| `CASH_FLOW_LATE_RISK_DAYS_THRESHOLD` | `5` | Minimum average days-late to flag a Payment Risk opportunity. |
| `CASH_FLOW_AUTOSCAN_ENABLED` | *(on)* | Ops-level kill switch for the whole scheduler — set to `false` to disable it entirely. Per-client opt-in is a UI toggle, not this variable. |
| `CASH_FLOW_AUTOSCAN_INTERVAL_HOURS` | `1` | Max refresh frequency per opted-in client. |
| `CASH_FLOW_AUTOSCAN_TICK_MINUTES` | `5` | How often the scheduler checks for due work. |

### Email (Azure Communication Services)

| Variable | Purpose |
|---|---|
| `AZURE_COMM_SERVICE_ENDPOINT`, `AZURE_COMM_SERVICE_PASS` | ACS connection details, used by both review-note emailing and Cash Flow outreach. |
| `AZURE_COMM_SENDER_ADDRESS` | From-address for sent emails. |
| `FIRM_NAME` | Used in email sign-offs / branding. |

### Misc

| Variable | Purpose |
|---|---|
| `PARALLEL_REVIEWS` | Thread-pool size for per-account review generation (default 4). |
| `REPLIT_DEPLOYMENT`, `REPLIT_DEV_DOMAIN` | Set automatically on Replit; `REPLIT_DEPLOYMENT` gates the "refuse to silently fall back to SQLite" production check. |

## Running

```bash
python3 app.py
```

Runs Flask's dev server (`use_reloader=False` deliberately — the stat-reloader re-execs the process, which doesn't survive typical sandboxed/background process management). Restart manually after code changes.

Production runs under gunicorn, potentially with **multiple worker processes** — see [`ARCHITECTURE.md`](ARCHITECTURE.md#multi-worker-safety-the-file-cache-pattern) for why several features coordinate via small JSON files under `instance/` rather than in-memory state.

## Running tests

```bash
python3 -m pytest tests/ -q
```

(or `python3 -m unittest discover -s tests -v`). Tests cover the Xero-data parsing pipeline, LLM prompt/response handling, and config resolution — they run fully offline against fixture data, no live Xero/Azure credentials needed.

## A note on schema changes

There is **no migration tool** (no Alembic/Flask-Migrate) — `db.create_all()` at startup only ever creates missing tables, never alters an existing one. If you remove or rename a model column, any database created before that change keeps the old column, `NOT NULL` and all, and every future insert will fail against it. See [`DATA_MODEL.md`](DATA_MODEL.md#schema-changes-without-a-migration-tool) for the concrete incident this caused and the safe pattern to follow instead.
