# Features

## Dashboard & client management

The landing page (`/`) lists every Xero organisation the logged-in user's OAuth connection covers (searchable, paginated), each linking to that client's detail page. A `client`-role user instead sees only the tenants explicitly granted to them.

**Client detail** (`/client/<tenant_id>`) is the hub for one client: a header with the Xero deep link, and (for staff/partner) three tabs:
- **Plan** — active/inactive follow-up action lists; see [Plans & Timeline](#plans--timeline) below.
- **Timeline** — a flat, reverse-chronological feed of every completed Plan step across all plans, showing who completed it and when.
- **Review History** — every past review run for this tenant: resume a draft, view notes, download the PDF, generate a follow-up Plan from it, or delete it.

**Client Portal Access** (same page, staff/partner only) provisions a restricted `client`-role login for the business owner themselves — pick an email (autocompleted from Xero contacts) and a password, and they get a account scoped to only this tenant's Plan/Timeline (see [`DATA_MODEL.md`](DATA_MODEL.md#roles)).

**Firm Client Overview** (`/partner/clients`, partner role only) is a triage view: latest review per client across the whole firm (not per staff member), each tagged with a positive/negative/neutral sentiment badge computed by a cheap keyword heuristic over the review text (`helpers/client_overview.py`) — deliberately not a second LLM call.

## Workbench

The guided review workflow behind "New Review": a four-stage wizard (Trial Balance → Account Selection → Account Review → Generate) rendered as one page (`templates/workbench.html`) with a live "Processing Log" panel narrating what the AI is doing.

1. **Trial Balance** — live rows fetched from Xero, with search, a "hide zero nominals" filter, and a running match count — added specifically because large trial balances made the raw list unusable.
2. **Account Selection** — an AI batch pass (`/api/workbench/analyze_scope_batch`) flags which nominal codes are worth reviewing (large movements, new/stopped balances, risk-flagged account types) with a one-line reason each; the accountant can override any selection or re-run the analysis for a single account.
3. **Account Review** — for each selected code, a transaction drill-down (`/api/workbench/nominal_transactions`) and an AI narrative (`/api/workbench/analyze_nominal`).
4. **Generate** — kicks off the background review-note pipeline described in [`ARCHITECTURE.md`](ARCHITECTURE.md#the-review-note-generation-pipeline), landing on the live SSE progress page.

Selections and notes are saved as a draft (`/api/workbench/save_draft` / `load_draft`) so a browser refresh or a later session doesn't lose progress.

## Cash Flow Accelerator

Analyses a tenant's Xero invoices to surface revenue-recovery opportunities, each with an AI-drafted insight and (where relevant) a draft outreach email. Generation is always asynchronous — the dashboard never blocks on a live Xero+LLM round trip; it shows a spinner and polls until done.

### The six opportunity types

| Type | Signal |
|---|---|
| **Late Payment** | A contact has an `AUTHORISED` invoice already past its due date (reactive). |
| **Win-Back** | A contact with above-median lifetime revenue has gone quiet for 90+ days. |
| **Subscription Candidate** | A contact buys repeatedly at a regular cadence — a candidate for a retainer/subscription arrangement. |
| **Payment Risk** *(predictive)* | A contact with a real history of paying late (computed from each paid invoice's actual settlement date vs. its due date) has an invoice open that **isn't** overdue yet — a heads-up before it follows the same pattern. Never overlaps Late Payment. |
| **Underperforming** | Tenant-wide (not per-contact): a product/service line's revenue has dropped sharply between two rolling windows. |
| **Cross-Sell** | A simple market-basket heuristic: an active contact hasn't bought one of the business's top revenue lines that comparable customers do buy. |

Because the six types' impact-£ figures are structurally different magnitudes (a contact's whole lifetime revenue vs. a single revenue-decline delta), the merge into the displayed top-12 list is **round-robin across types**, not one global sort — otherwise a few large legacy-type opportunities can silently crowd every other type out of the list entirely. See [`ARCHITECTURE.md`](ARCHITECTURE.md#cash-flow-accelerator-caching--background-jobs) for why this mattered in practice.

### Autonomous scanning — and the one hard boundary

A per-client **"Autonomous Scan: ON/OFF"** toggle on the dashboard lets a client opt into periodic background rescanning, so fresh opportunities are waiting next time someone opens the page instead of requiring a manual click every time. Turning it on fires an immediate scan (same spinner as "Generate New") so the effect is visible right away; from then on, a background scheduler (APScheduler, ticking every few minutes, but only actually refreshing any one client at most once per `CASH_FLOW_AUTOSCAN_INTERVAL_HOURS`) keeps it current.

**Sending outreach is never part of the autonomous path.** Detection and drafting can run on a timer; the "Send Outreach" button is always a manual, human-clicked action, for every single opportunity, every time — there is no code path, autonomous or otherwise, that emails a real customer without a person clicking send first.

### Outcome tracking

Every regeneration diffs the previous scan's opportunities against the new ones; anything that disappears is logged as a resolved outcome (paid off, re-engaged, etc.), cross-referenced against whether outreach had actually been sent for it. Shown as a "Recently Resolved" panel — the evidence that the feature turns detection into a measurable result, not just a list of alerts.

## AI Chat (Xero MCP)

An open-ended chat interface, per client, backed by the **official Xero MCP server** rather than the app's own bespoke Xero client — see [`ARCHITECTURE.md`](ARCHITECTURE.md#ai-chat-the-xero-mcp-bridge) for the technical bridge and why a small patch to the official server was necessary.

- **Sessions & history** — a user can have many conversations per tenant; a History dropdown lists past ones by preview text, and "New Chat" creates a genuinely blank session (not just clearing the view — a real, separate session id).
- **Client Memory** — durable facts about a client (fiscal year quirks, vendor classifications) persist across sessions and staff members, either written by the model itself (a `remember_fact` tool call) or typed directly into the memory panel. Deleting one is a single click.
- **Artefacts** — when a question calls for a chart or table, the model calls a local `render_artifact` tool; the result renders inline in the conversation *and* in a persistent side canvas, with an expand-to-fullscreen option and a history strip to recall earlier artefacts from the same session. Table rows referencing a real Xero record get a "View in Xero" deep link, built server-side from the record's real ID (never trusting a URL the model might invent).
- **Markdown** — assistant replies render through `marked` + `DOMPurify` (sanitised before insertion), so formatting (headings, lists, tables) actually displays instead of showing as raw text.
- **Behaviour tuning** — the system prompt explicitly pushes the model to complete multi-step lookups itself (e.g. "biggest suppliers by spend" needs combining invoices/contacts) rather than stopping to ask which method to use; it should state its assumption and proceed, only asking a real clarifying question when it's ambiguous *what* the user wants.

## Plans & Timeline

A lightweight follow-up action tracker per client, independent of any one review run (though it can be seeded from one):

- A Plan can be hand-created, or **AI-drafted** from a completed review (ranks the weakest-variance accounts, asks the LLM for a title + step list) — always created `inactive` so a staff/partner must review and explicitly activate it before it's "live."
- An "Ask AI" box on an existing Plan drafts a single new step description from a short instruction, which the accountant then reviews before adding.
- Completing/reopening a step is the **one** action a restricted `client`-role login (see Client Portal Access above) is allowed to perform — everything else about Plan structure (create/edit/delete) is staff/partner only. This is the whole mechanism by which a business owner can self-report progress without being able to alter what they're being asked to do.
- The Timeline tab is derived entirely from completed `PlanStep` rows — there's no separate timeline table.
