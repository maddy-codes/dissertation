# Review Portal

A Flask portal for accounting firms built on Xero: AI-drafted year-end review notes, a live revenue-opportunity radar, an open-ended AI chat over live client data, and lightweight follow-up action tracking — all scoped per client, with a restricted portal login firms can hand to the business owner themselves.

## Features

- **Workbench** — a guided trial-balance review (select accounts → AI-flagged risk areas → drill into transactions → generate) ending in an AI-drafted PDF review note, live-streamed as it's written.
- **Cash Flow Accelerator** — detects six kinds of revenue opportunity (late payment, win-back, subscription candidates, *predictive* payment risk, underperforming products, cross-sell) from live Xero invoices, drafts outreach for each, and can scan autonomously on a schedule — sending is always a manual, human-clicked action, never automatic.
- **AI Chat** — open-ended Q&A over one client's live Xero data, powered by the official Xero MCP server, with durable per-client memory and inline chart/table artefacts.
- **Plans & Timeline** — follow-up action lists (hand-written or AI-drafted from a completed review) with a restricted client-role login that can tick off its own progress without touching anything else.

See [`docs/FEATURES.md`](docs/FEATURES.md) for a full walkthrough of each.

## Documentation

| Doc | Covers |
|---|---|
| [`docs/FEATURES.md`](docs/FEATURES.md) | What each feature does, in detail |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Tech stack, the review-generation pipeline, the Xero MCP bridge, multi-worker/background-job patterns |
| [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) | Every route: method, path, auth requirement, purpose |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | Database schema, roles, and entity relationships |
| [`docs/SETUP.md`](docs/SETUP.md) | Full environment variable reference, install/run/test instructions |

## Repository map

```
app.py                      Entrypoint
setup/                      App factory, config, database models
routes/                     One blueprint per feature (auth, dashboard, workbench, plans, reports, cash flow, chat)
templates/, static/         Jinja templates + CSS/JS
helpers/                    Business logic: Xero parsing, AI drafting, PDF, email, caching
integrations/                XeroClient (direct API) + the AI Chat MCP bridge
agents/, main_crew.py       Review-note generation LLM calls
tests/                      Offline unit tests for the data pipeline
node_modules/, patches/     Vendored, patched Xero MCP server (AI Chat feature only)
```

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
npm install          # only needed for the AI Chat feature
cp .env.example .env # fill in what you need — see docs/SETUP.md
python3 app.py
```

## Run tests

```bash
python3 -m pytest tests/ -q
```

Tests run fully offline against fixture data — no live Xero/Azure credentials required.
