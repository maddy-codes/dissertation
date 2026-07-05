"""
Lightweight, dependency-free sentiment rollup for a completed review's CSV
output, used by the partner-facing client overview dashboard.

Deliberately a keyword heuristic rather than another LLM call: the review
notes are already AI-generated, so re-scoring them with a second model call
would add latency/cost/failure-surface for a signal a handful of accounting
keywords already gives us.
"""
from __future__ import annotations

import csv
import os

POSITIVE_MARKERS = (
    "increase", "increased", "growth", "higher", "improved", "improvement", "up from",
)
NEGATIVE_MARKERS = (
    "decrease", "decreased", "decline", "declined", "risk", "unusual", "written off",
    "bad debt", "loss", "lower", "shortfall", "overdue",
)
ERROR_MARKERS = ("failed to process",)


def summarize_review_sentiment(csv_path: str) -> dict:
    """
    Returns {"label": "positive"|"negative"|"neutral"|"unknown",
             "positive_hits": int, "negative_hits": int, "error_rows": int,
             "total_rows": int}.
    """
    if not csv_path or not os.path.exists(csv_path):
        return {"label": "unknown", "positive_hits": 0, "negative_hits": 0, "error_rows": 0, "total_rows": 0}

    positive_hits = 0
    negative_hits = 0
    error_rows = 0
    total_rows = 0

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                summary = (row.get("ai_summary") or "").strip()
                if not summary:
                    continue
                total_rows += 1
                lowered = summary.lower()
                if any(marker in lowered for marker in ERROR_MARKERS):
                    error_rows += 1
                    continue
                positive_hits += sum(lowered.count(marker) for marker in POSITIVE_MARKERS)
                negative_hits += sum(lowered.count(marker) for marker in NEGATIVE_MARKERS)
    except Exception:
        return {"label": "unknown", "positive_hits": 0, "negative_hits": 0, "error_rows": 0, "total_rows": 0}

    net = positive_hits - negative_hits
    if total_rows == 0:
        label = "unknown"
    elif net > 0:
        label = "positive"
    elif net < 0:
        label = "negative"
    else:
        label = "neutral"

    return {
        "label": label,
        "positive_hits": positive_hits,
        "negative_hits": negative_hits,
        "error_rows": error_rows,
        "total_rows": total_rows,
    }
