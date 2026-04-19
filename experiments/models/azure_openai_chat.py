from __future__ import annotations

import time
from typing import Any, Dict, Optional

from openai import AzureOpenAI

from experiments.types import GenerationResult, Technique


class AzureOpenAIChatClient:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        api_version: str,
        deployment_name: str,
        default_temperature: float = 0.1,
        default_top_p: float = 0.9,
    ) -> None:
        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        self._deployment_name = deployment_name
        self._default_temperature = default_temperature
        self._default_top_p = default_top_p

    def generate_review_notes(
        self, *, context: str, prompt: str, technique: Technique
    ) -> GenerationResult:
        # Basic defaults; can be tuned per-technique if desired.
        temperature = self._default_temperature
        top_p = self._default_top_p
        if technique in ("zero_shot", "few_shot"):
            temperature = 0.05
        elif technique == "prompt_optimised":
            temperature = 0.0

        start = time.time()
        resp = self._client.chat.completions.create(
            model=self._deployment_name,
            temperature=temperature,
            top_p=top_p,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
        latency_s = time.time() - start

        content = ""
        if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
            content = resp.choices[0].message.content

        usage: Dict[str, Any] = {}
        if getattr(resp, "usage", None):
            usage = {
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
                "completion_tokens": getattr(resp.usage, "completion_tokens", None),
                "total_tokens": getattr(resp.usage, "total_tokens", None),
            }

        return GenerationResult(output_text=content, latency_s=latency_s, usage=usage)

