from __future__ import annotations

from typing import Any, Dict, List

from experiments.types import Example


def _coerce_paragraphs(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                # common schema: {"text": "..."} or {"content": "..."}
                for k in ("text", "content", "paragraph"):
                    if k in item and isinstance(item[k], str):
                        out.append(item[k])
                        break
        return out
    return []


def _extract_transactions(example_json: dict[str, Any]) -> list[dict[str, Any]]:
    # Flexible extraction: accept either a direct "transactions" list or Xero API wrapper forms.
    if isinstance(example_json.get("transactions"), list):
        txs = [t for t in example_json["transactions"] if isinstance(t, dict)]
        return txs

    xero_data = example_json.get("xero_data")
    if isinstance(xero_data, dict):
        bt = xero_data.get("bank_transactions")
        if isinstance(bt, dict) and isinstance(bt.get("BankTransactions"), list):
            return [t for t in bt["BankTransactions"] if isinstance(t, dict)]
    return []


def _extract_tb_rows(example_json: dict[str, Any]) -> list[dict[str, Any]]:
    # If the corpus already includes a trial balance style list, preserve it.
    if isinstance(example_json.get("trial_balance_rows"), list):
        rows = [r for r in example_json["trial_balance_rows"] if isinstance(r, dict)]
        return rows
    return []


def normalise_example_json(example_id: str, example_json: dict[str, Any]) -> Example:
    metadata: Dict[str, Any] = {}
    if isinstance(example_json.get("metadata"), dict):
        metadata.update(example_json["metadata"])

    corpus_paragraphs: List[str] = []
    original = example_json.get("original_json_data")
    if isinstance(original, dict):
        corpus_paragraphs.extend(_coerce_paragraphs(original.get("paragraphs")))
    corpus_paragraphs.extend(_coerce_paragraphs(example_json.get("paragraphs")))

    return Example(
        example_id=example_id,
        metadata=metadata,
        trial_balance_rows=_extract_tb_rows(example_json),
        transactions=_extract_transactions(example_json),
        corpus_paragraphs=corpus_paragraphs,
    )

