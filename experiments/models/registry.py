from __future__ import annotations

from typing import Dict

from experiments.config import ExperimentConfig
from experiments.types import ModelSpec

from .azure_openai_chat import AzureOpenAIChatClient
from .transformers_local import TransformersLocalClient


class ModelRegistry:
    def __init__(self, config: ExperimentConfig) -> None:
        self._config = config
        self._cache: Dict[str, object] = {}

    def get(self, model: ModelSpec):
        if model.model_id in self._cache:
            return self._cache[model.model_id]

        if model.provider == "azure_openai":
            if not self._config.azure_openai.endpoint or not self._config.azure_openai.api_key:
                raise RuntimeError(
                    "Azure OpenAI not configured. Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY."
                )
            deployment = model.config.get("deployment_name") or model.config.get("deployment") or model.model_id
            client = AzureOpenAIChatClient(
                endpoint=self._config.azure_openai.endpoint,
                api_key=self._config.azure_openai.api_key,
                api_version=self._config.azure_openai.api_version,
                deployment_name=str(deployment),
            )
            self._cache[model.model_id] = client
            return client

        if model.provider == "transformers":
            model_path = model.config.get("model_name_or_path") or model.model_id
            adapter = model.config.get("adapter_path")
            client = TransformersLocalClient(
                model_name_or_path=str(model_path),
                adapter_path=str(adapter) if adapter else None,
                max_new_tokens=int(model.config.get("max_new_tokens", 350)),
            )
            self._cache[model.model_id] = client
            return client

        raise RuntimeError(f"Unknown provider: {model.provider}")

