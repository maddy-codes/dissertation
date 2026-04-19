# ai_review_notes

This repo contains a Flask + Celery app for generating accountant-style review notes, plus an experiment platform to compare models/techniques and demonstrate context degradation.

## Experiments (Multi-Model + Context Degradation)

The app now exposes:
- `GET /experiments` to configure and start an experiment run
- `GET /experiments/status/<task_id>` for Celery status
- `GET /experiments/run/<run_id>` to view results and download CSV/JSON

### Required environment variables (Azure Blob dataset)
- `AZURE_STORAGE_CONNECTION_STRING`
- `EXAMPLES_CONTAINER`
- `EXAMPLES_PREFIX` (optional)

### Fetch details directly from Xero API (optimised mode)
If your corpus JSON is a lightweight descriptor with `metadata.tenant_id` and `metadata.year_end_date`, you can fetch fresh `xero_data` directly from Xero at run time:
- `EXAMPLES_ENRICH_FROM_XERO_API=1`
- `XERO_CLIENT_ID`
- `XERO_CLIENT_SECRET`
- `XERO_REFRESH_TOKEN`
- `XERO_TOKEN_CACHE_PATH` (optional, recommended so refresh-token rotation is persisted)

### Required environment variables (Azure OpenAI models)
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_API_VERSION` (optional, default `2024-02-15-preview`)
- `EXPERIMENT_AZURE_DEPLOYMENT_PRIMARY` (optional, defaults to `DEPLOYED_MODEL_NAME` from `strings/assistant.py`)
- `EXPERIMENT_AZURE_DEPLOYMENT_SECONDARY` (optional)

### Local development dataset fallback (no Blob)
If you set:
- `EXAMPLES_LOCAL_DIR=/absolute/path/to/jsons`

then experiments will load `*.json` from that directory (non-recursive) instead of Azure Blob.

### Optional open-source models (Transformers)
If you set:
- `OSS_MODEL_PATH_BASE` (HF model name or local path)
- `OSS_LORA_ADAPTER_PATH` (optional, LoRA adapter path)

then those models show up in the Experiments UI. You must also install the optional deps (`torch`, `transformers`, and for adapters `peft`).

### Fine-tuning (LoRA)
There is an optional trainer script at `experiments/train_lora.py` that expects a JSONL file with records:
`{"prompt": "...", "response": "..."}`.
