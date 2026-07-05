"""AI drafting of a standardized Plan (title + steps) from a completed review.

The agent is briefed on the review's weakest nominals — the accounts with the
largest year-on-year variance, which is exactly what the run's CSV already
ranks accountants' attention by — plus the review narrative already written
for each, and asked to return strict JSON that maps 1:1 onto Plan/PlanStep so
it can be rendered directly with no extra parsing.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from helpers.openai_config import build_openai_client, resolve_scan_deployment_name

logger = logging.getLogger(__name__)

TOP_N_WEAKEST = 5

_SYSTEM_PROMPT = "You are a UK accountant assistant returning strict JSON."


def _weakest_nominals(run_csv_path: str, top_n: int = TOP_N_WEAKEST) -> list[dict]:
    """Rank this run's accounts by absolute year-on-year variance."""
    df = pd.read_csv(run_csv_path, index_col=0)
    if "variance_abs" not in df.columns:
        # Older runs predate the variance columns; nothing to rank by.
        return []

    ranked = df.reindex(df["variance_abs"].abs().sort_values(ascending=False).index)
    rows = []
    for _, row in ranked.head(top_n).iterrows():
        rows.append(
            {
                "name": row.get("xero_names", ""),
                "current": row.get("current_value"),
                "prior": row.get("prior_value"),
                "variance_abs": row.get("variance_abs"),
                "variance_pct": row.get("variance_pct"),
                "summary": (row.get("ai_summary") or "").strip() if pd.notna(row.get("ai_summary")) else "",
            }
        )
    return rows


def generate_plan_from_review(run_csv_path: str) -> dict:
    """Return `{"title": str, "steps": [str, ...]}` drafted from this review's weakest nominals."""
    nominals = _weakest_nominals(run_csv_path)
    if not nominals:
        raise ValueError(
            "This review has no ranked accounts to build a plan from "
            "(older runs predate variance tracking)."
        )

    context = "\n".join(
        f"- {n['name']}: £{n['current']:.2f} vs £{n['prior']:.2f} prior "
        f"(variance £{n['variance_abs']:.2f}). Review note: {n['summary'] or 'n/a'}"
        for n in nominals
    )

    prompt = f"""
You are a UK chartered accountant preparing a follow-up action plan for a client based on
the weakest (highest year-on-year variance) nominal accounts from their latest review.

Weakest nominals this year:
{context}

Draft a short, standardized action plan the accountant will review and can edit before
activating. Each step must be ONE concrete, specific action tied to one of the accounts
above (name the account and the discrepancy/amount), phrased as an instruction to either
the accountant or the client. 3 to 6 steps. No preamble, no headings inside a step.

Reply with strict JSON only:
{{"title": "<short plan title>", "steps": ["<step 1>", "<step 2>", "..."]}}
"""
    client = build_openai_client()
    response = client.chat.completions.create(
        model=resolve_scan_deployment_name(),
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    data = json.loads(response.choices[0].message.content)

    title = (data.get("title") or "").strip() or "Review Follow-up Plan"
    steps = [s.strip() for s in (data.get("steps") or []) if isinstance(s, str) and s.strip()]
    if not steps:
        raise ValueError("The AI did not return any usable steps.")
    return {"title": title, "steps": steps}


def suggest_plan_step(existing_steps: list[str], instruction: str) -> str:
    """Return ONE new step description built from `instruction`, aware of `existing_steps`."""
    existing = "\n".join(f"- {s}" for s in existing_steps) or "(no steps yet)"
    prompt = f"""
You are a UK chartered accountant adding one step to an existing client action plan.

Existing steps:
{existing}

Accountant's instruction for the new step: "{instruction}"

Draft ONE new, concrete action step (a single sentence, no numbering, no preamble) that
fulfils the instruction and complements the existing steps without duplicating them.

Reply with strict JSON only: {{"step": "<the new step>"}}
"""
    client = build_openai_client()
    response = client.chat.completions.create(
        model=resolve_scan_deployment_name(),
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    data = json.loads(response.choices[0].message.content)

    step = (data.get("step") or "").strip()
    if not step:
        raise ValueError("The AI did not return a usable step.")
    return step
