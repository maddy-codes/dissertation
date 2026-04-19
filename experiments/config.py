from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AzureBlobConfig:
    connection_string: Optional[str]
    container: Optional[str]
    prefix: str


@dataclass(frozen=True)
class AzureOpenAIConfig:
    endpoint: Optional[str]
    api_key: Optional[str]
    api_version: str


@dataclass(frozen=True)
class ExperimentConfig:
    cache_dir: str
    store_path: str
    blob: AzureBlobConfig
    azure_openai: AzureOpenAIConfig


def load_config() -> ExperimentConfig:
    cache_dir = os.environ.get("EXPERIMENT_CACHE_DIR", ".cache/experiments")
    store_path = os.environ.get("EXPERIMENT_STORE_PATH", "data/experiments.sqlite")

    blob = AzureBlobConfig(
        connection_string=os.environ.get("AZURE_STORAGE_CONNECTION_STRING"),
        container=os.environ.get("EXAMPLES_CONTAINER"),
        prefix=os.environ.get("EXAMPLES_PREFIX", ""),
    )

    azure_openai = AzureOpenAIConfig(
        endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
    )

    return ExperimentConfig(
        cache_dir=cache_dir,
        store_path=store_path,
        blob=blob,
        azure_openai=azure_openai,
    )

