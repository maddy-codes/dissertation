# AI Review Notes Dissertation Codebase

This repository accompanies the dissertation **Automating Year-End Accounting Notes**. It contains:

- A Flask application for accountant-style year-end review note generation.
- Deterministic data-processing helpers for Xero-derived trial balance and transaction data.
- Experiment utilities for context construction, scoring, GPT-5.4 prompt-engineering validation, and dataset preparation.
- LaTeX dissertation source and generated figures under `dissertation_material/`.
- Unit tests covering date parsing, scoring, context builders, prompt construction, and the data pipeline.

## Repository Map

- `app.py`, `routes/`, `templates/`, `static/`: Flask web application.
- `helpers/`: ledger parsing, mapping, utility, Xero processing, and analysis helpers.
- `agents/`: CrewAI agent orchestration.
- `experiments/`: reproducible experiment and evaluation code.
- `tests/`: unit tests for the submitted code.
- `dissertation_material/`: LaTeX source, report PDF, survey data, validation JSONL, and generated figures.
- `docs/company_restrictions_privacy_notes.md`: submission note covering firm restrictions, GDPR/privacy concerns, and where the real generated examples come from.
- `generate_graphs.py`: regenerates dissertation graphs from local data files.

## Setup

Use Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

The checked-in `pyproject.toml` lists the application dependencies. Optional live Azure and Xero integrations require credentials, but local tests and dissertation graph generation do not.

## Environment Variables

Create a local `.env` file from `.env.example`. Do not commit real secrets.

Required only for live Azure OpenAI prompt-engineering validation:

- `AZURE_OPENAI_API_KEY`
- `AZURE_EXISTING_AIPROJECT_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`

Required only for Azure Blob/Xero enrichment workflows:

- `AZURE_STORAGE_CONNECTION_STRING`
- `XERO_CLIENT_ID`
- `XERO_CLIENT_SECRET`
- `XERO_REFRESH_TOKEN`

## Run Tests

```bash
python3 -m unittest discover -s tests -v
```

## Generate Dissertation Figures

```bash
XDG_CACHE_HOME=/tmp/font-cache MPLCONFIGDIR=/tmp/mpl python3 generate_graphs.py
```

This command does two things:

- renders the Mermaid workflow diagrams via `render_mermaid_diagrams.mjs`
- regenerates the Matplotlib / PyPlot figures from local data files

It reads:

- `dissertation_material/survey data/Survey1_Baseline_Data.csv`
- `dissertation_material/survey data/Survey2_AI_Evaluation_Data.csv`
- `dissertation_material/exceptional_validation_data.jsonl`

and writes PNG figures into `dissertation_material/figures/`.

## Build Data Pipeline JSONL Files

To transform local Xero/working-paper JSON files into chat-style training and validation JSONL:

```bash
python3 -m experiments.run_data_pipeline extra --output-dir dissertation_material/generated_datasets
```

The reusable implementation is in `experiments/data_pipeline.py`. The dissertation-facing wrapper is `dissertation_material/datapipeline_code.py`.

## Run GPT-5.4 Prompt-Engineering Validation

Set `AZURE_OPENAI_API_KEY` first, then run:

```bash
python3 -m experiments.prompt_engineering_gpt54 \
  --input dissertation_material/exceptional_validation_data.jsonl \
  --output dissertation_material/prompt_engineering_results.csv \
  --deployment gpt-5.4
```

The harness evaluates zero-shot, single-shot, and few-shot prompt conditions against the same validation corpus. It stores generated outputs and gold responses for subsequent scoring.

## Build Dissertation PDF

```bash
cd dissertation_material
latexmk -pdf -interaction=nonstopmode -halt-on-error 22830110_dissertation.tex
```

The current built report is `dissertation_material/22830110_dissertation.pdf`.
