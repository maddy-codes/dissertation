# Route Reference

All blueprints are registered with **no `url_prefix`** (`setup/app_factory.py`), so every path below is exactly as decorated in its source file. "Auth" describes the access-control layer applied, on top of the base `@login_required` (Flask-Login session cookie) that every route below requires unless stated otherwise. See [`ARCHITECTURE.md`](ARCHITECTURE.md#access-control) for how the three access-control mechanisms (`login_required`, `user_can_view_tenant`, run-ownership-by-file) differ.

Roles referenced: `staff` (default), `partner`, `client` — see [`DATA_MODEL.md`](DATA_MODEL.md#roles).

## Auth — `routes/auth_routes.py` (`auth_bp`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET/POST | `/login` | none | Local email/password login |
| GET/POST | `/register` | none | Open self-registration (new users default to `role='staff'`) |
| GET | `/logout` | login | Clear session |
| GET | `/auth/xero` | none | Start Xero OAuth2 — identity scope only ("Sign in with Xero") |
| GET | `/auth/xero/connect` | login | Start Xero OAuth2 — full accounting scope ("Connect Xero") |
| GET | `/auth/xero/callback` | none (validates OAuth `state`) | Exchanges the auth code, creates/logs in the user, persists the token |

## Dashboard & clients — `routes/main_routes.py` (`main_bp`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET/POST | `/` | login | Dashboard: list connected Xero clients; POST kicks off a background review run |
| GET | `/client/<tenant_id>` | login + `user_can_view_tenant` | Client detail: Plan / Timeline / Review History tabs |
| POST | `/client/<tenant_id>/access` | login, staff/partner only | Create a `client`-role login + `ClientAccess` grant |
| POST | `/client/<tenant_id>/access/<access_id>/revoke` | login, staff/partner only | Revoke a client access grant |
| POST | `/client/<tenant_id>/review/<run_id>/delete` | login, run owner | Delete a review + its on-disk artifacts |
| GET | `/client/<tenant_id>/reports/download` | login, owner | ZIP of every completed review PDF for that tenant |
| GET | `/api/client/<tenant_id>/year_ends` | login | JSON list of recent fiscal year-end dates (populates the New Review modal) |
| GET | `/partner/clients` | login, partner only | Firm-wide "latest review per client" rollup with sentiment |

## Working papers — `routes/workbench_routes.py` (`workbench_bp`)

The guided trial-balance review flow (Trial Balance → Account Selection → Account Review → Generate). See [`FEATURES.md`](FEATURES.md#workbench).

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/workbench` | login | Render the workbench page for a chosen tenant/year-end |
| GET | `/api/workbench/fetch_tb/<tenant_id>` | login | Live trial balance rows for the selected period |
| POST | `/api/workbench/analyze_scope_batch/<tenant_id>` | login | AI batch pass: which nominal codes need review, with reasoning |
| POST | `/api/workbench/save_draft/<tenant_id>` | login | Persist in-progress selections/notes so a session survives a reload |
| GET | `/api/workbench/load_draft/<tenant_id>` | login | Restore a saved draft |
| GET | `/api/workbench/nominal_transactions/<tenant_id>` | login | Drill-down transaction list for one nominal code |
| GET | `/api/workbench/prime_ledger/<tenant_id>` | login | Pre-warms the ledger cache ahead of the review run |
| GET | `/api/workbench/analyze_nominal/<tenant_id>` | login | AI narrative for a single selected nominal code |

## Plans & Timeline — `routes/plan_routes.py` (`plan_bp`)

"Manage" below means `user_can_view_tenant` **and** `role != 'client'`; "view" means `user_can_view_tenant` only (so a `client`-role grantee can reach it). All POSTs redirect back to `client_detail#plan` except `suggest_step`, which returns JSON.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/client/<tenant_id>/plans` | manage | Create a Plan + one PlanStep per line of a textarea |
| POST | `/client/<tenant_id>/plans/<plan_id>/toggle` | manage | Flip Plan `active`/`inactive` |
| POST | `/client/<tenant_id>/plans/<plan_id>/edit` | manage | Rename a Plan |
| POST | `/client/<tenant_id>/plans/<plan_id>/delete` | manage | Delete a Plan (cascades its steps) |
| POST | `/client/<tenant_id>/plans/<plan_id>/steps` | manage | Append a new PlanStep |
| POST | `/client/<tenant_id>/plans/<plan_id>/steps/<step_id>/edit` | manage | Edit a step's description |
| POST | `/client/<tenant_id>/plans/<plan_id>/steps/<step_id>/delete` | manage | Delete a step |
| POST | `/client/<tenant_id>/plans/<plan_id>/steps/<step_id>/complete` | **view** | Mark a step done (the one write action a `client`-role user has) |
| POST | `/client/<tenant_id>/plans/<plan_id>/steps/<step_id>/reopen` | **view** | Revert a step to pending |
| POST | `/client/<tenant_id>/plans/generate` | manage | AI-draft a whole Plan from a completed review run (created `inactive`) |
| POST | `/client/<tenant_id>/plans/<plan_id>/suggest_step` | manage | AI-draft one new step description (JSON in/out, no DB write) |

## Reports — `routes/report_routes.py` (`report_bp`)

"Owner" means the run's `uploads/<run_id>.owner` sidecar matches `current_user.id` — independent of tenant/role, so not even a partner can view another user's in-progress run.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/report/<run_id>` | login + owner | Live review-generation page shell |
| GET | `/api/stream_report/<run_id>` | login + owner | Server-Sent Events progress stream |
| GET | `/report/<run_id>/download` | login + owner | Download the rendered PDF |
| POST | `/api/send_report/<run_id>` | login + owner | Email the PDF to a given address |
| GET | `/revoke/<task_id>` | none | Legacy no-op stub (kept so old client JS doesn't 404) |

## Cash Flow Accelerator — `routes/cash_flow_routes.py` (`cash_flow_bp`)

See [`FEATURES.md`](FEATURES.md#cash-flow-accelerator) for the opportunity-detection model and autoscan behaviour.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/cash-flow/<tenant_id>` | login | Dashboard — shows the cached report, never computes inline |
| POST | `/api/cash-flow/<tenant_id>/generate` | login | Kick off a background regeneration ("Generate New") |
| GET | `/api/cash-flow/<tenant_id>/status` | login | Poll generation status (`idle`/`running`/`done`/`error`) |
| POST | `/api/cash-flow/<tenant_id>/autoscan` | login | Toggle this client's autonomous-scan opt-in; turning on fires an immediate scan |
| POST | `/api/cash-flow/<tenant_id>/send/<opportunity_id>` | login | Send the drafted outreach email (always a manual click — never automatic) |

## AI Chat — `routes/chat_routes.py` (`chat_bp`)

Gated to staff/partner only (`_chat_available_to`: `role != 'client'` and a Xero token present). See [`FEATURES.md`](FEATURES.md#ai-chat-xero-mcp).

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/chat` | login, non-client | Chat page: tenant selector + current/most-recent session |
| GET | `/api/chat/<tenant_id>/sessions` | login, non-client | List this user's chat sessions for a tenant (history dropdown) |
| GET | `/api/chat/<tenant_id>/history` | login, non-client | Messages for a specific (or most recent) session |
| POST | `/api/chat/<tenant_id>/message` | login, non-client | Send a message; runs the MCP tool-calling loop, returns reply + artefact |
| POST | `/api/chat/<tenant_id>/new` | login, non-client | Create a genuinely new, empty session |
| GET/POST | `/api/chat/<tenant_id>/memory` | login, non-client | List / manually add a durable client-memory fact |
| DELETE | `/api/chat/<tenant_id>/memory/<memory_id>` | login, non-client | Forget a memory fact |
