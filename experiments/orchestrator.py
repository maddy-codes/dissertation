from __future__ import annotations

import random
import time
import uuid
from dataclasses import asdict
from typing import Any, Callable, Dict, Iterable, List, Sequence, Tuple

from experiments.context import build_context_variants
from experiments.dataset import normalise_example_json
from experiments.models import ModelRegistry
from experiments.prompts import PromptTemplate, PromptTemplates, render_prompt
from experiments.scoring import score_output
from experiments.store import SqliteExperimentStore
from experiments.types import Example, GenerationRecord, RunDefinition, Technique
from experiments.utils import sha256_text


def run_experiment(
    *,
    run_def: RunDefinition,
    examples: list[tuple[str, dict[str, Any]]],
    store: SqliteExperimentStore,
    model_registry: ModelRegistry,
) -> str:
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    store.create_run(run_id, run_def)

    # Normalise upfront for retrieval / few-shot selection.
    normed: list[Example] = [normalise_example_json(eid, data) for eid, data in examples]

    # Precompute simple example texts for few-shot retrieval.
    example_texts: dict[str, str] = {}
    for ex in normed:
        parts: list[str] = []
        if ex.corpus_paragraphs:
            parts.extend(ex.corpus_paragraphs[:10])
        if ex.transactions:
            parts.append(f"transactions_count={len(ex.transactions)}")
        example_texts[ex.example_id] = "\n".join(parts)[:2000]

    rng = random.Random(1337)

    optimised_by_model_id: dict[str, PromptTemplate] = {}
    if "prompt_optimised" in run_def.techniques:
        for model in run_def.models:
            client = model_registry.get(model)
            optimised_by_model_id[model.model_id] = _prompt_search_best_template(
                client=client,
                dev_examples=normed[: run_def.prompt_search_dev_size],
                run_def=run_def,
                rng=rng,
            )

    # Cache for few-shot exemplars per model/example
    shot_cache: dict[tuple[str, str], str] = {}

    for ex in normed:
        context_variants = build_context_variants(
            ex,
            run_def.context_modes,
            run_def.materiality_policy,
            run_def.subscription_policy,
        )

        for model in run_def.models:
            client = model_registry.get(model)
            for technique in run_def.techniques:
                prompt_template: PromptTemplate
                if technique == "prompt_optimised":
                    prompt_template = optimised_by_model_id.get(
                        model.model_id, PromptTemplates.default_template()
                    )
                elif technique == "few_shot":
                    shots = _build_few_shot_demonstrations(
                        target=ex,
                        all_examples=normed,
                        example_texts=example_texts,
                        client=client,
                        run_def=run_def,
                        model_id=model.model_id,
                        cache=shot_cache,
                    )
                    prompt_template = PromptTemplates.few_shot_template(shots)
                else:
                    prompt_template = PromptTemplates.default_template()

                for context_mode, context_text in context_variants.items():
                    prompt_text = render_prompt(prompt_template, context_text)
                    prompt_hash = sha256_text(prompt_text)
                    context_hash = sha256_text(context_text)

                    start = time.time()
                    gen = client.generate_review_notes(
                        context=context_text,
                        prompt=prompt_text,
                        technique=technique,
                    )
                    latency_s = time.time() - start

                    score = score_output(
                        output_text=gen.output_text,
                        example=ex,
                        context_text=context_text,
                        scoring=run_def.scoring,
                    )

                    store.add_generation(
                        GenerationRecord(
                            run_id=run_id,
                            example_id=ex.example_id,
                            model_id=model.model_id,
                            technique=technique,
                            context_mode=context_mode,
                            prompt_hash=prompt_hash,
                            prompt_text=prompt_text,
                            context_hash=context_hash,
                            context_text=context_text,
                            output_text=gen.output_text,
                            latency_s=latency_s,
                            usage_json=gen.usage,
                            score_json=score,
                        )
                    )

    return run_id


def _prompt_search_best_template(
    *,
    client,
    dev_examples: list[Example],
    run_def: RunDefinition,
    rng: random.Random,
) -> PromptTemplate:
    candidates = PromptTemplates.optimised_candidates(
        seed_text="",
        rng=rng,
        trials=run_def.prompt_search_trials,
    )
    if not dev_examples:
        return PromptTemplates.default_template()

    best = PromptTemplates.default_template()
    best_score = -1.0

    # Use a stable representative context: prefer materiality+subscriptions if requested.
    preferred_modes: list[str] = []
    if "materiality+subscriptions" in run_def.context_modes:
        preferred_modes.append("materiality+subscriptions")
    if "raw" in run_def.context_modes:
        preferred_modes.append("raw_50")
    preferred_modes.extend(["raw_25", "raw_100", "materiality", "subscriptions"])

    for tmpl in candidates:
        scores: list[float] = []
        for ex in dev_examples:
            contexts = build_context_variants(
                ex,
                run_def.context_modes,
                run_def.materiality_policy,
                run_def.subscription_policy,
            )
            ctx = None
            for m in preferred_modes:
                if m in contexts:
                    ctx = contexts[m]
                    break
            if ctx is None:
                continue

            prompt = render_prompt(tmpl, ctx)
            gen = client.generate_review_notes(context=ctx, prompt=prompt, technique="prompt_optimised")
            sc = score_output(
                output_text=gen.output_text,
                example=ex,
                context_text=ctx,
                scoring=run_def.scoring,
            )
            scores.append(_scalarise_score(sc))
        avg = sum(scores) / max(1, len(scores))
        if avg > best_score:
            best_score = avg
            best = tmpl

    return best


def _scalarise_score(score_json: dict) -> float:
    # Minimal scalar objective: prioritize format compliance + grounding coverage.
    fmt = score_json.get("format", {})
    grounding = score_json.get("grounding", {})
    single = 1.0 if fmt.get("single_paragraph") else 0.0
    no_ref = 1.0 if fmt.get("no_ref_words") else 0.0
    cov = grounding.get("counterparty_coverage")
    cov_f = float(cov) if isinstance(cov, (int, float)) else 0.0
    return single + no_ref + cov_f


def _build_few_shot_demonstrations(
    *,
    target: Example,
    all_examples: list[Example],
    example_texts: dict[str, str],
    client,
    run_def: RunDefinition,
    model_id: str,
    cache: dict[tuple[str, str], str],
) -> list[tuple[str, str, str]]:
    # Retrieve K similar examples.
    shots = _retrieve_few_shot_examples(
        target_id=target.example_id,
        example_texts=example_texts,
        k=run_def.few_shot_k,
    )
    by_id = {ex.example_id: ex for ex in all_examples}
    demos: list[tuple[str, str, str]] = []
    for eid, _ in shots:
        ex = by_id.get(eid)
        if not ex:
            continue
        contexts = build_context_variants(
            ex,
            run_def.context_modes,
            run_def.materiality_policy,
            run_def.subscription_policy,
        )
        ctx = (
            contexts.get("materiality+subscriptions")
            or contexts.get("raw_50")
            or contexts.get("raw_25")
            or ""
        )
        if not ctx:
            continue
        key = (model_id, eid)
        if key not in cache:
            teacher_prompt = render_prompt(PromptTemplates.default_template(), ctx)
            cache[key] = client.generate_review_notes(
                context=ctx, prompt=teacher_prompt, technique="zero_shot"
            ).output_text
        demos.append((eid, ctx, cache[key]))
    return demos


def _retrieve_few_shot_examples(
    *,
    target_id: str,
    example_texts: dict[str, str],
    k: int,
) -> list[tuple[str, str]]:
    target_text = example_texts.get(target_id, "")
    scored: list[tuple[float, str]] = []
    for eid, text in example_texts.items():
        if eid == target_id:
            continue
        s = _cheap_similarity(target_text, text)
        scored.append((s, eid))
    scored.sort(reverse=True)
    shots: list[tuple[str, str]] = []
    for _, eid in scored[:k]:
        shots.append((eid, example_texts.get(eid, "")))
    return shots


def _cheap_similarity(a: str, b: str) -> float:
    # Jaccard over lowercase tokens is cheap and dependency-free.
    a_set = set(_tokenise(a))
    b_set = set(_tokenise(b))
    if not a_set or not b_set:
        return 0.0
    return len(a_set & b_set) / max(1, len(a_set | b_set))


def _tokenise(text: str) -> list[str]:
    out: list[str] = []
    cur = []
    for ch in text.lower():
        if ch.isalnum():
            cur.append(ch)
        else:
            if cur:
                out.append("".join(cur))
                cur = []
    if cur:
        out.append("".join(cur))
    return out
