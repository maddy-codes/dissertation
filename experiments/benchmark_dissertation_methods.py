"""Benchmark live dissertation deployments against the validation corpus.

This script discovers the live model deployments from the AI Foundry project
endpoint, then executes:

- GPT-5.4 zero-shot
- GPT-5.4 single-shot
- GPT-5.4 few-shot
- all callable GPT-4.1 fine-tuned deployments

It records raw outputs and end-to-end latency to CSV so the dissertation figures
can be built from measured results rather than illustrative placeholders.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from dotenv import dotenv_values
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.prompt_engineering_gpt54 import ValidationExample, build_messages, load_examples


DEFAULT_VALIDATION_PATH = Path("dissertation_material/exceptional_validation_data.jsonl")
DEFAULT_OUTPUT_PATH = Path("dissertation_material/live_benchmark_results.csv")
DEFAULT_DEPLOYMENTS_SNAPSHOT = Path("dissertation_material/live_deployments_snapshot.json")


@dataclass(frozen=True)
class BenchmarkMethod:
    method_id: str
    method_label: str
    deployment_name: str
    method_family: str
    prompt_strategy: str


def load_env() -> dict[str, str]:
    cfg = {k: v for k, v in dotenv_values(".env").items() if v}
    required = ["MODEL_API_KEY", "MODEL_OPENAI_ENDPOINT", "MODEL_AZURE_ENDPOINT"]
    missing = [key for key in required if key not in cfg]
    if missing:
        raise RuntimeError(f"Missing required .env keys: {', '.join(missing)}")
    return cfg


def list_project_deployments(project_endpoint: str, api_key: str) -> list[dict]:
    response = requests.get(
        f"{project_endpoint.rstrip('/')}/deployments",
        params={"api-version": "v1"},
        headers={"api-key": api_key},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("value", [])


def snapshot_deployments(deployments: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(deployments, indent=2), encoding="utf-8")


def discover_methods(deployments: list[dict]) -> list[BenchmarkMethod]:
    methods: list[BenchmarkMethod] = [
        BenchmarkMethod(
            method_id="gpt54_zero_shot",
            method_label="GPT-5.4 Zero-Shot",
            deployment_name="gpt-5.4",
            method_family="Prompt engineered GPT-5.4",
            prompt_strategy="zero-shot",
        ),
        BenchmarkMethod(
            method_id="gpt54_single_shot",
            method_label="GPT-5.4 Single-Shot",
            deployment_name="gpt-5.4",
            method_family="Prompt engineered GPT-5.4",
            prompt_strategy="single-shot",
        ),
        BenchmarkMethod(
            method_id="gpt54_few_shot",
            method_label="GPT-5.4 Few-Shot",
            deployment_name="gpt-5.4",
            method_family="Prompt engineered GPT-5.4",
            prompt_strategy="few-shot",
        ),
    ]

    fine_tuned = sorted(
        (
            deployment
            for deployment in deployments
            if deployment.get("type") == "ModelDeployment"
            and deployment.get("capabilities", {}).get("chat_completion") == "true"
            and ".ft-" in str(deployment.get("modelName", ""))
        ),
        key=lambda deployment: str(deployment.get("name", "")),
    )
    for index, deployment in enumerate(fine_tuned, start=1):
        methods.append(
            BenchmarkMethod(
                method_id=f"ft_{index}",
                method_label=f"GPT-4.1 Fine-Tuned {index}",
                deployment_name=deployment["name"],
                method_family="Fine-tuned GPT-4.1",
                prompt_strategy="fine-tuned",
            )
        )
    return methods


def fine_tuned_messages(example: ValidationExample) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": example.system_prompt},
        {"role": "user", "content": example.user_prompt},
    ]


def prompt_messages(strategy: str, target: ValidationExample, shots: Iterable[ValidationExample]) -> list[dict[str, str]]:
    return build_messages(strategy, target, shots)


def parse_example_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def select_examples(examples: list[ValidationExample], requested_ids: list[str]) -> list[ValidationExample]:
    if not requested_ids:
        return examples

    by_id = {example.example_id: example for example in examples}
    resolved: list[ValidationExample] = []
    missing: list[str] = []
    for requested in requested_ids:
        normalized = requested if requested.startswith("val_") else f"val_{int(requested):03d}"
        example = by_id.get(normalized)
        if example is None:
            missing.append(requested)
            continue
        resolved.append(example)
    if missing:
        raise RuntimeError(f"Unknown validation example ids: {', '.join(missing)}")
    return resolved


def run_benchmark(
    *,
    methods: list[BenchmarkMethod],
    input_path: Path,
    output_path: Path,
    openai_endpoint: str,
    api_key: str,
    limit: int | None,
    example_ids: list[str],
    shot_example_ids: list[str],
) -> None:
    client = OpenAI(base_url=openai_endpoint.rstrip("/") + "/", api_key=api_key)
    all_examples = load_examples(input_path, limit=limit)
    examples = select_examples(all_examples, example_ids)
    shot_examples = select_examples(all_examples, shot_example_ids) if shot_example_ids else all_examples[:3]
    if len(shot_examples) < 3:
        raise RuntimeError("At least three shot examples are required.")

    strategies = {
        "zero-shot": [],
        "single-shot": shot_examples[:1],
        "few-shot": shot_examples[:3],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "method_id",
                "method_label",
                "method_family",
                "deployment_name",
                "prompt_strategy",
                "example_id",
                "latency_seconds",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "output_text",
                "gold_text",
                "error",
            ],
        )
        writer.writeheader()

        for example in examples:
            for method in methods:
                if method.prompt_strategy in strategies:
                    shots = strategies[method.prompt_strategy]
                    if example in shots:
                        continue
                    messages = prompt_messages(method.prompt_strategy, example, shots)
                else:
                    messages = fine_tuned_messages(example)

                error_text = ""
                output_text = ""
                prompt_tokens = ""
                completion_tokens = ""
                total_tokens = ""
                start = time.perf_counter()
                try:
                    completion = client.chat.completions.create(
                        model=method.deployment_name,
                        messages=messages,
                        temperature=0,
                    )
                    output_text = completion.choices[0].message.content or ""
                    usage = getattr(completion, "usage", None)
                    if usage is not None:
                        prompt_tokens = str(getattr(usage, "prompt_tokens", "") or "")
                        completion_tokens = str(getattr(usage, "completion_tokens", "") or "")
                        total_tokens = str(getattr(usage, "total_tokens", "") or "")
                except Exception as exc:  # noqa: BLE001
                    error_text = f"{type(exc).__name__}: {exc}"
                latency = time.perf_counter() - start

                writer.writerow(
                    {
                        "method_id": method.method_id,
                        "method_label": method.method_label,
                        "method_family": method.method_family,
                        "deployment_name": method.deployment_name,
                        "prompt_strategy": method.prompt_strategy,
                        "example_id": example.example_id,
                        "latency_seconds": f"{latency:.3f}",
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                        "output_text": output_text,
                        "gold_text": example.gold_response,
                        "error": error_text,
                    }
                )
                handle.flush()
                status = "ok" if not error_text else f"error={error_text}"
                print(
                    f"{example.example_id} | {method.method_label} | "
                    f"{latency:.3f}s | pt={prompt_tokens or '?'} | ct={completion_tokens or '?'} | {status}",
                    flush=True,
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark dissertation AI Foundry deployments.")
    parser.add_argument("--input", type=Path, default=DEFAULT_VALIDATION_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_DEPLOYMENTS_SNAPSHOT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--examples",
        help="Comma-separated validation ids to benchmark, e.g. val_064,val_079,val_084",
    )
    parser.add_argument(
        "--shot-examples",
        help="Comma-separated validation ids to use as the single/few-shot exemplars.",
    )
    args = parser.parse_args()

    cfg = load_env()
    deployments = list_project_deployments(cfg["MODEL_AZURE_ENDPOINT"], cfg["MODEL_API_KEY"])
    snapshot_deployments(deployments, args.snapshot)
    methods = discover_methods(deployments)

    print("Discovered benchmark methods:")
    for method in methods:
        print(f"- {method.method_label} -> {method.deployment_name}")

    run_benchmark(
        methods=methods,
        input_path=args.input,
        output_path=args.output,
        openai_endpoint=cfg["MODEL_OPENAI_ENDPOINT"],
        api_key=cfg["MODEL_API_KEY"],
        limit=args.limit,
        example_ids=parse_example_ids(args.examples),
        shot_example_ids=parse_example_ids(args.shot_examples),
    )
    print(f"Wrote live benchmark results to {args.output}")


if __name__ == "__main__":
    main()
