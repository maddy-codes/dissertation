"""Shared experiment data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Example:
    example_id: str
    transactions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ScoringConfig:
    require_single_paragraph: bool = False
    forbid_ref_numbers: bool = False


@dataclass
class MaterialityPolicy:
    relative_fraction: float = 0.1


@dataclass
class SubscriptionPolicy:
    min_occurrences: int = 3
