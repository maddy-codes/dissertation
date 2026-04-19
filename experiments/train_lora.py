"""
LoRA fine-tuning entrypoint (optional).

This is intentionally decoupled from the Flask app so you can run it on a machine with the right GPU/runtime.

Expected workflow:
1) Run experiments with `few_shot` / `prompt_optimised` to bootstrap pseudo-labels if you don't have human labels.
2) Build a JSONL SFT dataset where each record has {"prompt": "...", "response": "..."}.
3) Fine-tune an open-source base model with LoRA and point the backend at the resulting adapter via ModelSpec.config["adapter_path"].
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train_jsonl", required=True, help="Path to SFT JSONL: {prompt, response}.")
    ap.add_argument("--base_model", required=True, help="HF model name or local path.")
    ap.add_argument("--out_adapter", required=True, help="Output directory for LoRA adapter.")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch_size", type=int, default=1)
    ap.add_argument("--max_seq_len", type=int, default=2048)
    args = ap.parse_args()

    try:
        import torch  # type: ignore
        from datasets import load_dataset  # type: ignore
        from peft import LoraConfig, get_peft_model  # type: ignore
        from transformers import (  # type: ignore
            AutoModelForCausalLM,
            AutoTokenizer,
            DataCollatorForLanguageModeling,
            Trainer,
            TrainingArguments,
        )
    except Exception as e:
        raise RuntimeError(
            "Training deps missing. Install: torch, transformers, datasets, peft."
        ) from e

    ds = load_dataset("json", data_files={"train": args.train_jsonl})

    tok = AutoTokenizer.from_pretrained(args.base_model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    model = AutoModelForCausalLM.from_pretrained(args.base_model)

    lora = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    )
    model = get_peft_model(model, lora)

    def to_text(ex):
        prompt = ex.get("prompt", "")
        response = ex.get("response", "")
        return {"text": prompt + response}

    ds2 = ds.map(to_text)

    def tokenize(ex):
        return tok(
            ex["text"],
            truncation=True,
            max_length=args.max_seq_len,
            padding=False,
        )

    tokenized = ds2.map(tokenize, remove_columns=ds2["train"].column_names)
    collator = DataCollatorForLanguageModeling(tok, mlm=False)

    out_dir = Path(args.out_adapter)
    out_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(out_dir),
        per_device_train_batch_size=args.batch_size,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        logging_steps=20,
        save_steps=200,
        save_total_limit=2,
        report_to=[],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        data_collator=collator,
    )
    trainer.train()

    model.save_pretrained(str(out_dir))
    tok.save_pretrained(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

