"""Lightweight scoring helpers for generated review notes."""

from __future__ import annotations

import re
from typing import Any

from experiments.types import Example, ScoringConfig


REFERENCE_PATTERN = re.compile(r"\b(?:JRN|INV|REF|TXN)[- ]?\d+\b", re.IGNORECASE)


def score_output(
    output_text: str,
    example: Example,
    context_text: str,
    scoring: ScoringConfig,
) -> dict[str, Any]:
    """Score formatting and basic provenance constraints for a generated note."""
    stripped = output_text.strip()
    paragraphs = [part for part in re.split(r"\n\s*\n", stripped) if part.strip()]
    format_scores = {
        "single_paragraph": len(paragraphs) <= 1 if scoring.require_single_paragraph else True,
        "non_empty": bool(stripped),
    }
    provenance_scores = {
        "forbidden_ref_numbers_absent": not REFERENCE_PATTERN.search(stripped)
        if scoring.forbid_ref_numbers
        else True
    }
    return {
        "example_id": example.example_id,
        "format": format_scores,
        "provenance": provenance_scores,
        "context_chars": len(context_text),
    }
