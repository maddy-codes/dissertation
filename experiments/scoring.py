from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List

from experiments.types import Example, ScoringConfig
from experiments.utils import safe_float


_RE_MULTIPLE_PARAGRAPHS = re.compile(r"\n\s*\n")
_RE_REF = re.compile(r"\b(ref|reference|journal)\b", re.IGNORECASE)


def score_output(
    *,
    output_text: str,
    example: Example,
    context_text: str,
    scoring: ScoringConfig,
) -> Dict[str, Any]:
    """
    Best-effort scoring without gold labels:
    - format compliance
    - grounding against counterparties in transactions (if present)
    - subscription mention presence when subscriptions are detected in context
    """
    out = (output_text or "").strip()
    score: Dict[str, Any] = {"format": {}, "grounding": {}, "subscription": {}}

    # Format compliance
    if scoring.require_single_paragraph:
        score["format"]["single_paragraph"] = not bool(_RE_MULTIPLE_PARAGRAPHS.search(out))
    if scoring.forbid_ref_numbers:
        score["format"]["no_ref_words"] = not bool(_RE_REF.search(out))

    # Grounding: top counterparties mentioned
    counterparties = _top_counterparties(example, top_k=5)
    if counterparties:
        mentioned = [c for c in counterparties if _contains_name(out, c)]
        score["grounding"]["top_counterparties"] = counterparties
        score["grounding"]["mentioned_top_counterparties"] = mentioned
        score["grounding"]["counterparty_coverage"] = len(mentioned) / max(1, len(counterparties))
    else:
        score["grounding"]["counterparty_coverage"] = None

    # Subscriptions: if context suggests recurring payments, check output mentions at least one.
    if "SUBSCRIPTIONS_SUMMARY detected" in context_text:
        score["subscription"]["mentions_any_subscription_hint"] = bool(
            re.search(r"\b(subscription|recurring|monthly|direct debit)\b", out, re.IGNORECASE)
        )
    else:
        score["subscription"]["mentions_any_subscription_hint"] = None

    # Numeric fidelity is left as N/A unless trial balance fields are present.
    score["numeric"] = {"available": bool(example.trial_balance_rows)}

    return score


def _contains_name(text: str, name: str) -> bool:
    if not name or name == "UNKNOWN_CONTACT":
        return False
    return name.lower() in text.lower()


def _top_counterparties(example: Example, top_k: int) -> list[str]:
    txs = example.transactions
    if not txs:
        return []
    totals = defaultdict(float)
    for t in txs:
        c = t.get("Contact")
        name = None
        if isinstance(c, dict) and isinstance(c.get("Name"), str):
            name = c["Name"].strip()
        if not name:
            continue
        total = safe_float(t.get("Total"))
        if total is None:
            continue
        totals[name] += abs(total)
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return [n for n, _ in ranked[:top_k]]

