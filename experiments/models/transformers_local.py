from __future__ import annotations

import time
from typing import Any, Dict, Optional

from experiments.types import GenerationResult, Technique


class TransformersLocalClient:
    def __init__(
        self,
        *,
        model_name_or_path: str,
        adapter_path: Optional[str] = None,
        max_new_tokens: int = 350,
        device: str = "auto",
    ) -> None:
        try:
            import torch  # type: ignore
            from transformers import (  # type: ignore
                AutoModelForCausalLM,
                AutoTokenizer,
                TextGenerationPipeline,
            )
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Missing dependencies for local models. Install `torch` + `transformers`."
            ) from e

        self._torch = torch
        self._AutoModelForCausalLM = AutoModelForCausalLM
        self._AutoTokenizer = AutoTokenizer
        self._TextGenerationPipeline = TextGenerationPipeline

        tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
        model = AutoModelForCausalLM.from_pretrained(
            model_name_or_path,
            torch_dtype=getattr(torch, "float16", None),
            device_map="auto" if device == "auto" else None,
        )

        # Optional LoRA adapter.
        if adapter_path:
            try:
                from peft import PeftModel  # type: ignore
            except Exception as e:  # pragma: no cover
                raise RuntimeError(
                    "Adapter requested but `peft` is not installed."
                ) from e
            model = PeftModel.from_pretrained(model, adapter_path)

        self._pipe = self._TextGenerationPipeline(model=model, tokenizer=tokenizer)
        self._max_new_tokens = max_new_tokens

    def generate_review_notes(
        self, *, context: str, prompt: str, technique: Technique
    ) -> GenerationResult:
        start = time.time()
        # A simple text-generation call; prompt already includes context and instructions.
        out = self._pipe(
            prompt,
            max_new_tokens=self._max_new_tokens,
            do_sample=(technique != "prompt_optimised"),
            temperature=0.2 if technique != "prompt_optimised" else 0.0,
            top_p=0.9,
            return_full_text=False,
        )
        latency_s = time.time() - start
        text = ""
        if isinstance(out, list) and out and isinstance(out[0], dict):
            text = str(out[0].get("generated_text") or "")
        return GenerationResult(output_text=text, latency_s=latency_s, usage={})

