# Architecture

## Tech stack

| Layer | Choice |
|---|---|
| Web framework | Flask 3, server-rendered Jinja templates + vanilla JS (no SPA framework) |
| Styling | Tailwind (CDN) + a small custom design-token set in `templates/base.html` |
| Database | SQLAlchemy via Flask-SQLAlchemy. SQLite locally, Azure SQL in production (`DATABASE_CONNECTION_STRING`) |
| Auth | Flask-Login (session cookie) + local password (Werkzeug/scrypt) + Xero OAuth2 (`requests-oauthlib`) |
| AI / LLM | `openai` SDK against Azure OpenAI (or a plain OpenAI-compatible endpoint) — direct Chat Completions calls, not an agent framework, in every production code path |
| Xero data | Custom `XeroClient` (`integrations/xero_api.py`) wrapping the Accounting API `v2.0` REST endpoints |
| AI Chat tool access | The **official** Xero MCP server (`@xeroapi/xero-mcp-server`, Node/npm), spoken over stdio via the official Python `mcp` SDK |
| Background jobs | Plain `threading.Thread` for one-off long tasks (review generation, cash-flow generation); APScheduler `BackgroundScheduler` for the recurring cash-flow autoscan |
| PDF rendering | ReportLab (`Platypus` flowables) |
| Email | Azure Communication Services (`azure-communication-email`) |
| Process model | gunicorn, potentially **multiple worker processes** — this constraint shapes several design choices below |

## Repository map

```
app.py                      Entrypoint: loads .env, creates the Flask app, db.create_all()
setup/
  app_factory.py            create_app(): config, blueprints, CSRF, autoscan scheduler startup
  models.py                 All SQLAlchemy models (see DATA_MODEL.md)
routes/                     One blueprint per feature area (see API_REFERENCE.md)
templates/, static/         Jinja templates + CSS/JS
helpers/                    Business logic: Xero parsing, AI drafting, PDF, email, caching
integrations/xero_api.py    XeroClient — all direct Xero Accounting API calls
integrations/xero_mcp_client.py   The Chat feature's MCP tool-calling bridge
agents/crew_manager.py      Review-note generation LLM calls (CrewAI import present but dormant)
main_crew.py                Orchestrates agents/crew_manager.py across accounts (thread pool)
tests/                      unittest-based tests for the data pipeline
node_modules/, package.json, patches/   Vendored, patched copy of the official Xero MCP server
```

## The four independent feature areas

The app is really four loosely-coupled products sharing one login/tenant model:

1. **Workbench** (`routes/workbench_routes.py`) — a guided, human-in-the-loop trial-balance review that ends in an AI-drafted PDF review note. See below and [`FEATURES.md`](FEATURES.md#workbench).
2. **Cash Flow Accelerator** (`routes/cash_flow_routes.py`, `helpers/cash_flow_insights.py`) — autonomous-ish revenue-opportunity detection with human-gated outreach. See [`FEATURES.md`](FEATURES.md#cash-flow-accelerator).
3. **AI Chat** (`routes/chat_routes.py`, `integrations/xero_mcp_client.py`) — open-ended Q&A over one client's live Xero data via the official Xero MCP server. See [`FEATURES.md`](FEATURES.md#ai-chat-xero-mcp).
4. **Plans & Timeline** (`routes/plan_routes.py`) — lightweight follow-up action tracking, optionally AI-drafted from a completed review.

## The review-note generation pipeline

This is the app's original/core feature (Dashboard → Workbench → PDF), and the most complex data flow:

```
Xero Accounting API
   │  (XeroClient: Trial Balance, P&L, Accounts, Bank Txns, Invoices, Manual Journals — current + prior year)
   ▼
helpers/xero_api_parser.py :: fetch_and_format_xero_data()
   │  aggregates ledger activity per account code, computes variance vs prior year,
   │  calls helpers/ledger_analyzer.py for transaction-level narrative (cadence, new/stopped
   │  vendors, spikes — pure heuristics, no LLM)
   ▼
messages: [{"name": account, "message": briefing_text}], mp_df: DataFrame(xero_names, xero_codes, ai_summary, current_value, prior_value, variance_abs, variance_pct)
   ▼
main_crew.py :: run_all_crew(messages, mp_df, FILE_PATH_OUT, emit_event)
   │  ThreadPoolExecutor (default 4 workers, PARALLEL_REVIEWS) — one thread per account
   │  each calls agents/crew_manager.py :: ReviewCrew.run_single_shot_review(name, briefing)
   │  → ONE direct Azure OpenAI Chat Completions call per account, fixed-template prose
   │  writes back into mp_df["ai_summary"], emits progress via emit_event()
   ▼
uploads/<run_id>.csv   (mp_df.to_csv — the durable artifact everything downstream reads)
   ▼
helpers/pdf_report.py :: build_review_pdf_from_csv()  →  uploads/<run_id>.pdf   (ReportLab)
```

Side branches off the same CSV artifact:
- `helpers/plan_generator.py` — ranks the weakest-variance accounts and asks the LLM (JSON mode) for a follow-up action Plan; only runs when a staff/partner explicitly requests it from a completed review.
- `helpers/client_overview.py` — a **non-LLM** keyword-heuristic sentiment score over the `ai_summary` text, used for the partner firm-wide rollup (deliberately not a second model call over already-generated text).

**Note on CrewAI**: `agents/crew_manager.py` also defines a genuine 3-agent sequential CrewAI pipeline (`run_synthesis()` — analyst → writer → audit partner, Pydantic-schema outputs). It is **not used by any route** — its docstring/comments explain it was dropped after JSON-schema parsing failures leaked raw CrewAI logs into review notes. It's kept in the codebase for experimentation. Don't assume "CrewAI" in the requirements list means the live pipeline is multi-agent — it isn't.

**Live progress**: `_run_analysis` (in `routes/main_routes.py`) runs the whole pipeline above in a background `threading.Thread`, appending JSON-lines progress events to `uploads/<run_id>.jsonl`. `routes/report_routes.py`'s `/api/stream_report/<run_id>` tails that file over **Server-Sent Events** (polling the file every 0.5s, not a message queue), with a heartbeat comment every 10s so proxies don't kill the connection during long LLM calls.

## Access control

Three independent mechanisms, used for different things — don't conflate them:

1. **`@login_required`** (Flask-Login) — is there a session at all.
2. **`helpers/access.py:user_can_view_tenant(user, tenant_id)`** — does this *tenant* belong to this user. Staff/partner always pass (trusted via their own Xero OAuth scope); a `client`-role user must have an explicit `ClientAccess` grant row. Used across `main_routes`/`plan_routes`.
3. **Run-ownership-by-file** (`routes/report_routes.py:_require_run_owner`) — does this *background run* belong to this user, read from `uploads/<run_id>.owner`. Independent of tenant/role: even a partner can't view another staff member's in-progress run. Deliberately returns 404 (not 403) on mismatch, so it never confirms a run_id exists for someone else.

## Multi-worker safety: the file-cache pattern

Production runs gunicorn, which **can spawn multiple worker processes**. In-memory state (module globals, a running background thread) is only visible within the process that created it — a status poll or a scheduled tick can easily land on a *different* worker. Two subsystems solve this the same way: small JSON files under `instance/`, read/written with plain `open()`, instead of Redis/Celery/anything requiring extra infrastructure:

- **Cash Flow Accelerator** (`helpers/cash_flow_insights.py`): the report itself (`<tenant_id>.json`), generation status (`<tenant_id>.status.json`), the autoscan per-tenant opt-in flag (`<tenant_id>.autoscan_enabled.json`), and the autoscan last-run lock (`<tenant_id>.autoscan.json`) — all in `instance/cash_flow_cache/`.
- **Review runs** (`routes/main_routes.py`/`report_routes.py`): progress (`uploads/<run_id>.jsonl`), ownership (`uploads/<run_id>.owner`), output (`.csv`, `.pdf`).

None of this locking is perfectly atomic — the worst case is two workers doing the same harmless work once in a rare race — which is an accepted, documented tradeoff over adding real infrastructure for a firm-internal tool.

## Cash Flow Accelerator: caching & background jobs

`build_cash_flow_report()` never runs inline in a request — the dashboard route only ever reads whatever's cached; generation happens in a background thread (manual "Generate New") or via the APScheduler job (autoscan). Two further details worth knowing before touching this code:

- **Round-robin merge, not a global sort.** Six independent signal builders run (late payment, win-back, subscription-candidate, predictive late-payment-risk, underperforming-product, upsell/cross-sell). Their `impact_amount` bases are structurally very different sizes (a contact's whole lifetime revenue vs. a single revenue-decline delta) — an earlier version sorted everything by impact and took the top N, which let a handful of big legacy-type opportunities silently crowd every new type out of the result entirely. The fix (`_build_opportunities`) builds each type's list independently, sorts within each type, then merges round-robin (one from each type per round) so every type with *any* qualifying opportunity gets a slot before any type gets a second.
- **Autoscan is a per-*client* opt-in with no server env var to find.** The scheduler infrastructure itself always runs (`setup/app_factory.py` starts it unconditionally, gated only by an ops-level `CASH_FLOW_AUTOSCAN_ENABLED=false` kill switch); what's actually optional is each tenant's toggle, flipped from the Cash Flow Accelerator page itself and persisted via the same file-cache pattern. Turning a client's toggle on also fires an immediate scan (reusing the same background-thread path as "Generate New") so the effect is visible right away rather than waiting for the next scheduled tick. **Sending outreach is never automatic** — the scheduler and every autoscan code path only ever calls the detection/drafting function, never `send_outreach`/`send_plain_email`; a human must click "Send Outreach" for every message, every time.

## AI Chat: the Xero MCP bridge

`integrations/xero_mcp_client.py` is the only place in the app that talks to Xero through an LLM tool-calling loop rather than direct SDK calls. Per chat turn:

1. Spawn `node node_modules/@xeroapi/xero-mcp-server/dist/index.js` as a fresh subprocess (`mcp.client.stdio.stdio_client`), scoped to that turn via env vars `XERO_CLIENT_BEARER_TOKEN` (the current user's live Xero access token) and `XERO_TENANT_ID`.
2. `session.list_tools()` — the official server's ~50 tools, converted 1:1 into OpenAI function-calling schemas, plus one local-only tool `render_artifact` (charts/tables) and `remember_fact` (writes to `ClientMemory`) — neither of which touch the MCP server.
3. Run a bounded (≤12 iteration) tool-calling loop against Azure OpenAI, executing MCP tool calls via `session.call_tool(...)`.
4. Tear the subprocess down at the end of the turn. No long-lived session — simpler and safer under multi-worker gunicorn than trying to keep a process alive across requests.

**Why the official server needed a patch**: its `XeroClient.updateTenants()` always binds to whichever Xero org is *first* in the connections list for a bearer token — there's no way to select a tenant. This app's OAuth tokens are per-*user*, covering every client org that user has ever connected, and the whole point of Chat is picking a specific one. `patches/@xeroapi+xero-mcp-server+0.0.17.patch` (reapplied automatically via `patch-package`'s `postinstall` hook on every `npm install`) makes it honor `XERO_TENANT_ID` when set, falling back to the original behaviour otherwise — a ~10-line, reviewable diff, dropped instantly if Xero ever adds real tenant selection upstream.

## Deep links back into Xero

`helpers/xero_links.py` builds "View in Xero" URLs (invoices, bills, contacts, bank transactions, credit notes, purchase orders, reports) per [Xero's documented deep-linking scheme](https://developer.xero.com/documentation/best-practices/user-experience/deep-linking), which needs the organisation's `ShortCode` (fetched once via `XeroClient.get_organisation_short_code`, cached forever — it never changes) plus the record's real Xero ID. Every caller (Cash Flow Accelerator opportunity cards, Chat artefact table rows) builds the link server-side from `{type, id}}` — the model/report data is never trusted to construct or supply a raw URL itself.
