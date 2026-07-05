"""
Top-level orchestrator that turns per-account briefings into review notes.

Differences vs the original implementation:
- Uses a single-shot LLM call per account (ReviewCrew.run_single_shot_review)
  instead of a 3-agent chain. The chain was prone to schema-validation
  failures whose fallback dumped the entire CrewAI internal log as the
  "review note".
- Runs accounts in parallel through a small ThreadPoolExecutor so the user
  doesn't sit through 30+ accounts processed serially.
- Emits per-account `account_start` / `account_complete` / `account_error`
  events as soon as each one finishes, so the live page updates incrementally.
"""
from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.crew_manager import ReviewCrew
from helpers.utility import save_systematic_output
from strings.paths import FILE_PATH_OUT

logger = logging.getLogger(__name__)

# How many accounts to review in parallel. Tuned to stay below typical Azure
# OpenAI rate limits while keeping the wall-clock time reasonable.
DEFAULT_PARALLEL_REVIEWS = int(os.environ.get("PARALLEL_REVIEWS", "4"))


def _safe_emit(emit_event, *args, **kwargs):
    if not emit_event:
        return
    try:
        emit_event(*args, **kwargs)
    except Exception:
        logger.exception("emit_event failed")


def run_all_crew(
    messages,
    mp_df,
    FILE_PATH_OUT=FILE_PATH_OUT,
    emit_event=None,
    max_workers: int = DEFAULT_PARALLEL_REVIEWS,
):
    """
    Generate review notes for every account briefing in `messages`.

    Each item of `messages` is `{"name": <account label>, "message": <briefing>}`.
    `mp_df` is a parallel DataFrame with `xero_names` and an `ai_summary`
    column we fill in for the CSV export.
    """
    crew = ReviewCrew()
    df_lock = threading.Lock()
    all_responses: list[str] = []

    total = len(messages)
    completed = 0
    completed_lock = threading.Lock()

    _safe_emit(
        emit_event,
        "progress",
        message=(
            f"Reviewing {total} accounts in parallel "
            f"({max_workers} at a time). Notes will appear below as they finish."
        ),
    )

    def _process(message):
        account_name = message["name"]
        briefing = message["message"]

        _safe_emit(
            emit_event,
            "account_start",
            account=account_name,
            message=(
                "Drafting review note from Xero data using "
                f"{crew.final_deployment_name}…"
            ),
        )

        try:
            response = crew.run_single_shot_review(account_name, briefing)
            response_str = (response or "").strip()
            if not response_str:
                response_str = "No review note produced for this account."

            with df_lock:
                mp_df.loc[mp_df["xero_names"] == account_name, "ai_summary"] = response_str
                all_responses.append(response_str)

            _safe_emit(
                emit_event,
                "account_complete",
                account=account_name,
                synthesis=response_str,
                model=crew.final_deployment_name,
            )
            return account_name, True, None
        except Exception as exc:
            logger.exception("Review failed for %s", account_name)
            err = str(exc)
            with df_lock:
                mp_df.loc[mp_df["xero_names"] == account_name, "ai_summary"] = (
                    f"FAILED TO PROCESS: {err}"
                )
                all_responses.append(f"FAILED TO PROCESS: {err}")
            _safe_emit(
                emit_event,
                "account_error",
                account=account_name,
                logic=err,
                model=crew.final_deployment_name,
            )
            return account_name, False, err

    if not messages:
        _safe_emit(
            emit_event,
            "progress",
            message="No accounts qualified for review at the configured thresholds.",
        )
    else:
        # Bound concurrency to a small pool to stay under rate limits.
        workers = max(1, min(max_workers, total))
        # Use a list so the inner closure can mutate without `nonlocal`
        completed_box = [0]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_process, m) for m in messages]
            for fut in as_completed(futures):
                try:
                    fut.result()  # exceptions are already logged in _process
                except Exception:
                    logger.exception("Worker future raised")
                with completed_lock:
                    completed_box[0] += 1
                    done = completed_box[0]
                _safe_emit(
                    emit_event,
                    "progress",
                    message=f"Completed {done} of {total} accounts.",
                )

    # Persist results
    try:
        mp_df.to_csv(FILE_PATH_OUT)
        save_systematic_output(lines=all_responses, name=FILE_PATH_OUT)
    except Exception:
        logger.exception("Failed to persist review CSV at %s", FILE_PATH_OUT)


if __name__ == "__main__":
    pass
