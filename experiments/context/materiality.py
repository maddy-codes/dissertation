from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from experiments.types import Example, MaterialityPolicy
from experiments.utils import safe_float


def summarise_materiality(example: Example, policy: MaterialityPolicy) -> str:
    """
    Build a compressed, materiality-driven context.

    If transaction data exists, we compute top counterparties by absolute total.
    If not, we fall back to corpus paragraphs.
    """
    if not example.transactions and example.corpus_paragraphs:
        paras = "\n".join(example.corpus_paragraphs[:20])
        return "MATERIALITY_SUMMARY (no transactions found)\n" + paras

    txs = example.transactions
    if not txs:
        return "MATERIALITY_SUMMARY (no data)"

    totals_by_contact: Dict[str, float] = defaultdict(float)
    abs_totals: List[float] = []
    for t in txs:
        total = safe_float(t.get("Total"))
        if total is None:
            continue
        abs_total = abs(total)
        abs_totals.append(abs_total)
        name = _contact_name(t)
        totals_by_contact[name] += abs_total

    threshold = _materiality_threshold(abs_totals, policy)
    top = sorted(totals_by_contact.items(), key=lambda kv: kv[1], reverse=True)[:10]
    top_lines = [f"- {name}: £{amt:,.2f}" for name, amt in top]
    return "\n".join(
        [
            f"MATERIALITY_SUMMARY threshold_gbp=£{threshold:,.2f} tx_count={len(txs)}",
            "TOP_COUNTERPARTIES_BY_ABS_TOTAL:",
            *top_lines,
        ]
    )


def _contact_name(t: dict) -> str:
    c = t.get("Contact")
    if isinstance(c, dict) and isinstance(c.get("Name"), str) and c["Name"].strip():
        return c["Name"].strip()
    return "UNKNOWN_CONTACT"


def _materiality_threshold(abs_totals: list[float], policy: MaterialityPolicy) -> float:
    if policy.absolute_gbp is not None:
        return float(policy.absolute_gbp)
    if not abs_totals:
        return 0.0
    base = sum(abs_totals)
    frac = policy.relative_fraction if policy.relative_fraction is not None else 0.01
    return float(base * frac)

