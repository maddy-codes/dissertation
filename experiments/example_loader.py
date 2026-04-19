from __future__ import annotations

import json
from typing import Any

from experiments.config import AzureBlobConfig
from experiments.storage import AzureBlobExampleStore, ExampleCache

from experiments.api_enrich import enrich_example_json_from_xero_api


def load_examples_from_blob(
    *,
    blob: AzureBlobConfig,
    cache: ExampleCache,
    limit: int,
    offset: int = 0,
    prefix_override: str | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    if not blob.connection_string or not blob.container:
        raise RuntimeError(
            "Azure Blob not configured. Set AZURE_STORAGE_CONNECTION_STRING and EXAMPLES_CONTAINER."
        )
    store = AzureBlobExampleStore(blob.connection_string, blob.container)
    prefix = prefix_override if prefix_override is not None else blob.prefix
    refs = store.list_json_blobs(prefix=prefix)
    refs = refs[offset : offset + limit]

    out: list[tuple[str, dict[str, Any]]] = []
    for r in refs:
        cached_path = cache.get(r.name, r.etag)
        if cached_path:
            with open(cached_path, "rb") as f:
                data_bytes = f.read()
        else:
            data_bytes, etag = store.download_blob(r.name)
            cache.put(r.name, etag, data_bytes)

        try:
            data = json.loads(data_bytes.decode("utf-8"))
        except Exception:
            # Best-effort: some blobs may not be utf-8; skip them rather than fail the whole run.
            continue

        # Use blob name as a stable example id.
        example_id = r.name
        out.append((example_id, data))

    return out


def load_examples_from_local_dir(
    *,
    directory: str,
    limit: int,
    offset: int = 0,
) -> list[tuple[str, dict[str, Any]]]:
    """
    Local development fallback when Blob isn't configured.
    Reads *.json files from a directory (non-recursive).
    """
    import os

    files = [f for f in os.listdir(directory) if f.lower().endswith(".json")]
    files.sort()
    files = files[offset : offset + limit]
    out: list[tuple[str, dict[str, Any]]] = []
    for fn in files:
        path = os.path.join(directory, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        out.append((fn, data))
    return out


def enrich_examples_from_xero_api(
    examples: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    """
    Fetch Xero data for each example based on metadata pointers.

    This is used to "optimise to fetch details directly from API", keeping blob/local JSON
    as a lightweight index rather than the full stored snapshot.
    """
    enriched: list[tuple[str, dict[str, Any]]] = []
    for eid, payload in examples:
        enriched_payload = enrich_example_json_from_xero_api(example_json=payload)
        enriched.append((eid, enriched_payload))
    return enriched
