from __future__ import annotations

import os

from strings.assistant import API_VERSION, DEPLOYED_MODEL_NAME

SCAN_DEPLOYMENT_NAME = "gpt-5.4"


def resolve_azure_openai_endpoint() -> str:
    return (
        os.environ.get("MODEL_AZURE_ENDPOINT")
        or os.environ.get("AZURE_EXISTING_RESOURCE_ENDPOINT")
        or os.environ.get("AZURE_OPENAI_ENDPOINT")
        or os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT")
        or ""
    ).strip()


def resolve_azure_openai_api_key() -> str:
    return (
        os.environ.get("MODEL_API_KEY")
        or os.environ.get("AZURE_OPENAI_API_KEY")
        or ""
    ).strip()


def resolve_openai_base_url() -> str:
    return (
        os.environ.get("MODEL_OPENAI_ENDPOINT")
        or os.environ.get("AZURE_EXISTING_AIPROJECT_ENDPOINT")
        or ""
    ).strip()


def resolve_azure_openai_api_version() -> str:
    return (os.environ.get("AZURE_OPENAI_API_VERSION") or API_VERSION).strip()


def resolve_scan_deployment_name() -> str:
    return (
        os.environ.get("SCAN_DEPLOYMENT_NAME")
        or os.environ.get("AZURE_OPENAI_SCAN_DEPLOYMENT_NAME")
        or SCAN_DEPLOYMENT_NAME
    ).strip()


def build_openai_client():
    """Construct the right client (OpenAI-compatible base_url, or AzureOpenAI) from env config."""
    from openai import AzureOpenAI, OpenAI

    base_url = resolve_openai_base_url()
    if base_url:
        return OpenAI(base_url=base_url.rstrip("/") + "/", api_key=resolve_azure_openai_api_key())
    return AzureOpenAI(
        api_key=resolve_azure_openai_api_key(),
        api_version=resolve_azure_openai_api_version(),
        azure_endpoint=resolve_azure_openai_endpoint(),
    )


def resolve_final_review_deployment_name() -> str:
    return (
        os.environ.get("FINAL_REVIEW_DEPLOYMENT_NAME")
        or os.environ.get("AZURE_OPENAI_FINAL_DEPLOYMENT_NAME")
        or os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
        or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        or DEPLOYED_MODEL_NAME
    ).strip()
