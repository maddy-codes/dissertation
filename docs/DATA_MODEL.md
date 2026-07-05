# Data Model

All tables are defined in `setup/models.py` using Flask-SQLAlchemy. Schema is created via `db.create_all()` at startup (`app.py`) — there is **no migration tool** (no Alembic/Flask-Migrate) in this repo, so an existing production database is never altered by a model change, only new tables get created. See the "Schema changes without a migration tool" note at the end of this doc — it has bitten this project before.

The app runs on SQLite locally (`sqlite:///users.db`, resolved by `setup/app_factory.py:_resolve_database_uri`) and Azure SQL in production (via `DATABASE_CONNECTION_STRING`, optionally under a non-default schema set by `DATABASE_SCHEMA`).

## Users & access

### `User` (`users`)
The account behind every login — local email/password, or Xero SSO/OAuth.

| Column | Notes |
|---|---|
| `email` | unique |
| `password_hash` | `String(255)` — nullable (Xero-SSO-only users have none); sized for Werkzeug's scrypt hash (~162 chars), not the old default of 128 |
| `xero_user_id` | unique, nullable — set on first Xero SSO login |
| `xero_token_data` | JSON-serialized OAuth token dict (`access_token`, `refresh_token`, `expires_at`) via `set_xero_token`/`get_xero_token` |
| `role` | `'staff'` (default) \| `'partner'` \| `'client'` — see [Roles](#roles) below |

### `ClientAccess` (`client_access`)
Grants a `'client'`-role `User` read/complete access to exactly one tenant (a business owner's restricted login). Unique on `(user_id, tenant_id)`. Created via `main_routes.grant_client_access` — this is the only way a `client`-role account and its Xero-tenant scoping come into existence.

## Roles

- **`staff`** (default) — sees only their own review history and tenants covered by their own Xero OAuth connection.
- **`partner`** — everything staff can do, plus `/partner/clients`, a firm-wide rollup across *all* staff's completed reviews.
- **`client`** — a restricted business-owner login with no Xero token of its own. Scoped per-tenant via `ClientAccess` grants and gated by `helpers/access.py:user_can_view_tenant`. Can view their client detail page and **complete/reopen their own Plan steps** (`routes/plan_routes.py`), but cannot create/edit/delete plan structure, generate reviews, or use Chat/Cash Flow Accelerator (all gated to non-`client` roles).

## Reviews

### `ReviewNote` (`review_notes`)
One record per completed (or in-progress `'DRAFT'`) AI review run.

| Column | Notes |
|---|---|
| `user_id` | FK → `users.id`; the run's owner (see `_require_run_owner` in `routes/report_routes.py`) |
| `tenant_id`, `tenant_name` | which Xero org this run covers |
| `run_id` | unique — matches the `uploads/<run_id>.{jsonl,csv,pdf,owner}` artifact files |
| `year_start`, `year_end` | fiscal period covered |
| `status` | `'COMPLETED'` (default) or `'DRAFT'` |

The run's actual generated content (AI paragraphs, variances) lives in `uploads/<run_id>.csv`, not in this table — `ReviewNote` is just the DB-side index/metadata over that file.

## Action plans & timeline

### `Plan` (`plans`)
A named, editable action-item list for one tenant — either hand-created or AI-drafted (`helpers/plan_generator.py`) from a completed review, in which case it's created `status='inactive'` until a staff/partner explicitly activates it.

| Column | Notes |
|---|---|
| `tenant_id` | indexed |
| `status` | `'active'` \| `'inactive'` |
| `source_review_note_id` | FK → `review_notes.id`, nullable — set when AI-generated from a specific run |
| `created_by_user_id` | FK → `users.id` |
| `steps` | relationship → `PlanStep`, ordered by `position`, `cascade='all, delete-orphan'` |

### `PlanStep` (`plan_steps`)
One action item. Completing a step is the **only** write action available to a `client`-role user (see Roles above) — this is deliberate, so a business owner can tick off their own to-dos without being able to alter the plan itself.

| Column | Notes |
|---|---|
| `plan_id` | FK → `plans.id` |
| `position` | manual ordering |
| `status` | `'pending'` \| `'done'` |
| `completed_by_user_id`, `completed_at`, `completion_note` | set on completion, cleared on reopen |

The "Timeline" shown on a client's detail page is not a separate table — it's simply every `PlanStep` with `status='done'`, joined back to its `Plan`, ordered by completion time.

## AI Chat (Xero MCP)

### `ChatSession` (`chat_sessions`)
One chat conversation for a `(user, tenant)` pair. A user can have many sessions per tenant, shown as history — there's no archiving concept, whichever `session_id` a page has open is "current."

> **The vestigial `status` column.** This table originally had a `status` (`'active'`/`'archived'`) column; the session-list redesign dropped that concept from the app entirely. But since this repo has no migration tool, any database created before that point still has the column, `NOT NULL`, at the DB level. Rather than attempt an `ALTER TABLE` (which also risks failing outright if the app's DB login lacks `ALTER` rights — common on managed databases), `status` was **restored** to the model, always set to `'active'` and never read anywhere in application code. It exists purely so every environment's schema — new or years-old — satisfies the same constraint. Don't remove it without also confirming no live database still has it as `NOT NULL`.

### `ChatMessage` (`chat_messages`)
One turn (`role='user'|'assistant'`) in a session. `artifact_json`, when present, is a serialized chart/table spec (see [Cash Flow / Chat artifacts](FEATURES.md)) rendered inline and in the side canvas.

### `ClientMemory` (`client_memories`)
A durable fact about one tenant (e.g. "this client's fiscal year end is 31 March"), scoped by `tenant_id` — **not** by session, so it survives "New Chat" and is shared across whichever staff member is chatting. `source` is `'ai'` (the model's own `remember_fact` tool call) or `'manual'` (typed directly into the Client Memory panel).

## Cash Flow Accelerator

### `CashFlowOutreachLog` (`cash_flow_outreach_log`)
Persists every "Send Outreach" click — this is a human-triggered action only; nothing in this app ever sends outreach automatically. Records `tenant_id`, `opportunity_id` (the stable id from the report JSON, e.g. `late_c123`), `opportunity_type`, `contact_name`, `sent_to`, `sent_by_user_id`, `sent_at`. Without this table, a page reload had no way to show "already sent" — it was purely ephemeral JS state.

### `CashFlowOutcome` (`cash_flow_outcomes`)
Auto-recorded whenever a previously-detected opportunity disappears on a later scan (its underlying condition cleared — invoice paid, contact re-engaged, etc.), by diffing the previous cached opportunity-id set against the newly generated one (`helpers/cash_flow_insights.py:_record_outcomes`). `outreach_sent` is looked up from `CashFlowOutreachLog` at record time, so the dashboard's "Recently Resolved" panel can show whether the resolution followed an actual outreach action.

Note: the *live* opportunity list itself is **not** a database table — it's cached as JSON on disk (`instance/cash_flow_cache/<tenant_id>.json`), see [ARCHITECTURE.md](ARCHITECTURE.md#cash-flow-accelerator-caching--background-jobs).

## Entity relationships (summary)

```
User ──< ReviewNote
User ──< ClientAccess >── (tenant_id, no FK — Xero tenants aren't modeled locally)
User ──< Plan (created_by)
Plan ──< PlanStep >── User (completed_by)
Plan >── ReviewNote (source_review_note_id, nullable)
User ──< ChatSession ──< ChatMessage
User ──< CashFlowOutreachLog
(tenant_id) ──< ClientMemory
(tenant_id) ──< CashFlowOutcome
(tenant_id) ──< CashFlowOutreachLog
```

Xero tenants themselves have no local table — `tenant_id` is always the Xero-issued GUID, used as a plain string foreign key across every tenant-scoped table, resolved against live Xero API calls (`list_connections()`) whenever a human-readable name is needed.

## Schema changes without a migration tool

Because there's no Alembic, **any column you remove from a model can break every existing database that predates the change**, since `db.create_all()` never runs an `ALTER TABLE`. The safe options, in order of preference:
1. Don't remove the column — keep it in the model, always populate a valid default, stop reading it in application code (see `ChatSession.status` above).
2. If you must actually change a column, write and run a one-off manual migration script against the target database, and confirm the app-tier DB login actually has `ALTER` rights first (Azure SQL app logins commonly don't).
