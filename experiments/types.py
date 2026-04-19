from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Optional


ContextMode = Literal[
    "raw",
    "raw_25",
    "raw_50",
    "raw_100",
    "materiality",
    "subscriptions",
    "materiality+subscriptions",
]
Technique = Literal["zero_shot", "prompt_optimised", "few_shot", "fine_tuned"]
Provider = Literal["azure_openai", "transformers"]


@dataclass(frozen=True)
class Example:
    example_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Optional canonical data; not all corpora will contain all fields.
    trial_balance_rows: List[Dict[str, Any]] = field(default_factory=list)
    transactions: List[Dict[str, Any]] = field(default_factory=list)
    corpus_paragraphs: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    provider: Provider
    # Provider-specific fields (e.g., Azure deployment name or local HF model path).
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MaterialityPolicy:
    # Either an absolute GBP threshold, or a relative fraction (e.g., 0.01 == 1%) of a base.
    absolute_gbp: Optional[float] = None
    relative_fraction: Optional[float] = 0.01
    base_field: str = "total"


@dataclass(frozen=True)
class SubscriptionPolicy:
    # Minimum repeats to call a subscription / recurring supplier.
    min_occurrences: int = 3
    # Allowed +/- variation in amount (GBP) to still count as the same recurring payment.
    amount_tolerance_gbp: float = 2.0


@dataclass(frozen=True)
class ScoringConfig:
    require_single_paragraph: bool = True
    forbid_ref_numbers: bool = True


@dataclass(frozen=True)
class RunDefinition:
    run_name: str
    models: List[ModelSpec]
    techniques: List[Technique]
    context_modes: List[ContextMode]
    dataset_limit: int = 25
    dataset_offset: int = 0
    examples_prefix: str = ""
    materiality_policy: MaterialityPolicy = MaterialityPolicy()
    subscription_policy: SubscriptionPolicy = SubscriptionPolicy()
    scoring: ScoringConfig = ScoringConfig()
    few_shot_k: int = 3
    prompt_search_trials: int = 12
    prompt_search_dev_size: int = 8


@dataclass(frozen=True)
class GenerationResult:
    output_text: str
    latency_s: float
    # Usage is best-effort; may be empty for some providers.
    usage: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationRecord:
    run_id: str
    example_id: str
    model_id: str
    technique: Technique
    context_mode: ContextMode
    prompt_hash: str
    prompt_text: str
    context_hash: str
    context_text: str
    output_text: str
    latency_s: float
    usage_json: Dict[str, Any]
    score_json: Dict[str, Any]
