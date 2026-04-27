# AI Review Notes Portal

## Overview
A Flask-based web application for PHM Accountants that uses multi-agent AI (CrewAI) to generate "accountant-style" review notes by analyzing financial data (Trial Balances and transactions) from the Xero API. Also includes an experimentation framework to compare different LLMs and prompting techniques.

## Tech Stack
- **Backend**: Python 3.10, Flask with Flask-Login, Flask-SQLAlchemy, Flask-WTF
- **AI/Agent Framework**: CrewAI, LangChain, Azure OpenAI
- **Database**: SQLite (local fallback) or Azure SQL (production via ODBC)
- **External Integrations**: Xero API, Azure Blob Storage, Azure Communication Email
- **Package Manager**: `uv` (with `pyproject.toml`)
- **Production Server**: Gunicorn

## Project Structure
- `app.py` — Main Flask application and route definitions (1054 lines)
- `setup/app_factory.py` — Flask app factory with DB configuration
- `setup/models.py` — SQLAlchemy models (User)
- `agents/` — CrewAI multi-agent definitions (crew_manager.py)
- `experiments/` — LLM experimentation framework
- `helpers/` — Utility modules (data processors, mappers, email service)
- `integrations/` — Xero API and Azure email integrations
- `routes/` — Flask Blueprints (auth_routes.py)
- `templates/` & `static/` — Jinja2 HTML templates and static assets
- `strings/` — Centralized configuration for prompt paths and model names
- `uploads/` — Temporary storage for JSONL logs and generated reports

## Running the App
```bash
uv run python app.py
```
Runs on `0.0.0.0:5000`.

## Key Environment Variables
- `DATABASE_CONNECTION_STRING` — Azure SQL connection string (falls back to SQLite if unavailable)
- `DATABASE_SCHEMA` — Database schema prefix (e.g., "airn") — only applied for non-SQLite backends
- `OPENAI_API_KEY` / Azure OpenAI credentials — For AI model access
- `XERO_*` — Xero API credentials for financial data
- `AZURE_STORAGE_*` — Azure Blob Storage for datasets/examples

## Architecture Notes
- The app gracefully falls back to SQLite when Azure SQL is unavailable (no ODBC drivers)
- The schema prefix (`DATABASE_SCHEMA`) is only applied for non-SQLite databases
- Background threads handle long-running AI analysis tasks with JSONL event logging
- Flask-WTF CSRF protection is enabled throughout
