"""Run GPT-5.4 prompt-engineering validation against dissertation JSONL data.

The script intentionally reads credentials from environment variables only. It
does not store API keys or Azure subscription metadata in source code.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from openai import OpenAI


DEFAULT_ENDPOINT = "https://dissertation-airn-resource.openai.azure.com/openai/v1/"
DEFAULT_DEPLOYMENT = "gpt-5.4"


@dataclass(frozen=True)
class ValidationExample:
    example_id: str
    system_prompt: str
    user_prompt: str
    gold_response: str


def load_examples(path: Path, limit: int | None = None) -> list[ValidationExample]:
    examples: list[ValidationExample] = []
    with path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            record = json.loads(line)
            messages = record.get("messages", [])
            system_prompt = "\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
            user_prompt = "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
            gold_response = "\n".join(m.get("content", "") for m in messages if m.get("role") == "assistant")
            examples.append(
                ValidationExample(
                    example_id=f"val_{index:03d}",
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    gold_response=gold_response,
                )
            )
            if limit and len(examples) >= limit:
                break
    return examples


def build_messages(strategy: str, target: ValidationExample, shots: Iterable[ValidationExample]) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": target.system_prompt}]
    if strategy in {"single-shot", "few-shot"}:
        for shot in shots:
            messages.append({"role": "user", "content": shot.user_prompt})
            messages.append({"role": "assistant", "content": shot.gold_response})
    messages.append({"role": "user", "content": target.user_prompt})
    return messages


def run_validation(
    input_path: Path,
    output_path: Path,
    endpoint: str,
    deployment: str,
    limit: int | None,
) -> None:
    api_key = os.environ.get("AZURE_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set AZURE_OPENAI_API_KEY or OPENAI_API_KEY before running live validation.")

    examples = load_examples(input_path, limit=limit)
    if len(examples) < 4:
        raise RuntimeError("At least four validation examples are required for few-shot evaluation.")

    client = OpenAI(base_url=endpoint, api_key=api_key)
    strategies = {
        "zero-shot": [],
        "single-shot": examples[:1],
        "few-shot": examples[:3],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["example_id", "strategy", "latency_seconds", "output_text", "gold_text"],
        )
        writer.writeheader()
        for example in examples:
            for strategy, shots in strategies.items():
                if example in shots:
                    continue
                start = time.perf_counter()
                completion = client.chat.completions.create(
                    model=deployment,
                    messages=build_messages(strategy, example, shots),
                )
                latency = time.perf_counter() - start
                output_text = completion.choices[0].message.content or ""
                writer.writerow(
                    {
                        "example_id": example.example_id,
                        "strategy": strategy,
                        "latency_seconds": f"{latency:.3f}",
                        "output_text": output_text,
                        "gold_text": example.gold_response,
                    }
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GPT-5.4 prompt-engineering validation.")
    parser.add_argument("--input", type=Path, default=Path("dissertation_material/exceptional_validation_data.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("dissertation_material/prompt_engineering_results.csv"))
    parser.add_argument("--endpoint", default=os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--deployment", default=os.environ.get("AZURE_OPENAI_DEPLOYMENT", DEFAULT_DEPLOYMENT))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run_validation(args.input, args.output, args.endpoint, args.deployment, args.limit)


if __name__ == "__main__":
    main()
