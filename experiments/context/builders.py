from __future__ import annotations

import math
from typing import Dict, Iterable, List

from experiments.types import ContextMode, Example, MaterialityPolicy, SubscriptionPolicy
from experiments.utils import safe_float

from .materiality import summarise_materiality
from .subscriptions import summarise_subscriptions


def build_context_variants(
    example: Example,
    requested_modes: list[ContextMode],
    materiality_policy: MaterialityPolicy,
    subscription_policy: SubscriptionPolicy,
) -> Dict[ContextMode, str]:
    """
    Build the context strings for a given example.

    Degradation protocol:
    - If "raw" is requested, we emit: raw_25, raw_50, raw_100 (token budget approximation by transaction count).
    """
    out: Dict[ContextMode, str] = {}

    if "raw" in requested_modes:
        if example.transactions:
            txs = example.transactions
            n = max(1, len(txs))
            out["raw_25"] = _raw_transactions_context(txs[: max(1, math.ceil(n * 0.25))])
            out["raw_50"] = _raw_transactions_context(txs[: max(1, math.ceil(n * 0.50))])
            out["raw_100"] = _raw_transactions_context(txs)
        else:
            # Fall back to corpus paragraphs for "raw" degradation (approx by paragraph count).
            paras = example.corpus_paragraphs
            n = max(1, len(paras))
            out["raw_25"] = _raw_paragraphs_context(paras[: max(1, math.ceil(n * 0.25))])
            out["raw_50"] = _raw_paragraphs_context(paras[: max(1, math.ceil(n * 0.50))])
            out["raw_100"] = _raw_paragraphs_context(paras)

    if "materiality" in requested_modes:
        out["materiality"] = summarise_materiality(example, materiality_policy)
    if "subscriptions" in requested_modes:
        out["subscriptions"] = summarise_subscriptions(example, subscription_policy)
    if "materiality+subscriptions" in requested_modes:
        mat = summarise_materiality(example, materiality_policy)
        subs = summarise_subscriptions(example, subscription_policy)
        out["materiality+subscriptions"] = "\n\n".join([mat, subs]).strip()

    # Allow explicit raw_XX requests.
    for mode in ("raw_25", "raw_50", "raw_100"):
        if mode in requested_modes and mode not in out:
            # This happens if user bypasses "raw".
            if example.transactions:
                txs = example.transactions
                n = max(1, len(txs))
                frac = 0.25 if mode == "raw_25" else 0.50 if mode == "raw_50" else 1.0
                out[mode] = _raw_transactions_context(
                    txs[: max(1, math.ceil(n * frac))]
                )
            else:
                paras = example.corpus_paragraphs
                n = max(1, len(paras))
                frac = 0.25 if mode == "raw_25" else 0.50 if mode == "raw_50" else 1.0
                out[mode] = _raw_paragraphs_context(
                    paras[: max(1, math.ceil(n * frac))]
                )

    # Only return those requested, plus expanded "raw" variants.
    return {k: v for k, v in out.items() if k in out}


def _raw_transactions_context(txs: list[dict]) -> str:
    lines: List[str] = []
    for t in txs:
        contact = ""
        c = t.get("Contact")
        if isinstance(c, dict) and isinstance(c.get("Name"), str):
            contact = c["Name"]
        total = safe_float(t.get("Total"))
        date = t.get("DateString") or t.get("Date") or ""
        desc = ""
        items = t.get("LineItems")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            desc = str(items[0].get("Description") or "")
        lines.append(
            f"- date={date} contact={contact} total_gbp={total} desc={desc}".strip()
        )
    header = f"RAW_TRANSACTIONS count={len(txs)}"
    return "\n".join([header] + lines)


def _raw_paragraphs_context(paras: list[str]) -> str:
    header = f"RAW_CORPUS_PARAGRAPHS count={len(paras)}"
    body = "\n".join([p.strip() for p in paras if p.strip()])
    return "\n".join([header, body]).strip()

