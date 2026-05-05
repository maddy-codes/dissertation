"""Command-line entry point for building dissertation JSONL datasets."""

from __future__ import annotations

import argparse
from pathlib import Path

from experiments.data_pipeline import build_records_from_local, split_and_write


def main() -> None:
    parser = argparse.ArgumentParser(description="Build chat-style JSONL datasets from local Xero/working-paper JSON.")
    parser.add_argument("inputs", nargs="+", type=Path, help="JSON files or directories containing JSON files.")
    parser.add_argument("--output-dir", type=Path, default=Path("dissertation_material/generated_datasets"))
    parser.add_argument("--validation-fraction", type=float, default=0.15)
    args = parser.parse_args()

    records = build_records_from_local(args.inputs)
    split = split_and_write(records, args.output_dir, args.validation_fraction)
    print(f"Training records: {split.train_count} -> {split.train_path}")
    print(f"Validation records: {split.validation_count} -> {split.validation_path}")


if __name__ == "__main__":
    main()
