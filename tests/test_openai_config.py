import os
import unittest
from unittest.mock import patch

from agents.crew_manager import resolve_token_param
from helpers.openai_config import (
    resolve_azure_openai_endpoint,
    resolve_final_review_deployment_name,
    resolve_openai_base_url,
    resolve_scan_deployment_name,
)


class OpenAIConfigTests(unittest.TestCase):
    def test_scan_deployment_defaults_to_gpt54(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_scan_deployment_name(), "gpt-5.4")

    def test_final_review_deployment_prefers_explicit_final_override(self):
        env = {
            "FINAL_REVIEW_DEPLOYMENT_NAME": "ft-final",
            "AZURE_OPENAI_DEPLOYMENT_NAME": "stale-main",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve_final_review_deployment_name(), "ft-final")

    def test_endpoint_falls_back_to_ai_foundry_project_endpoint(self):
        env = {"AZURE_EXISTING_AIPROJECT_ENDPOINT": "https://example-resource.openai.azure.com/openai/v1/"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                resolve_azure_openai_endpoint(),
                "https://example-resource.openai.azure.com/openai/v1/",
            )

    def test_base_url_prefers_model_openai_endpoint(self):
        env = {"MODEL_OPENAI_ENDPOINT": "https://example-resource.openai.azure.com/openai/v1"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                resolve_openai_base_url(),
                "https://example-resource.openai.azure.com/openai/v1",
            )

    def test_token_param_defaults_to_max_tokens_without_openai_base_url(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_token_param("gpt-5.4"), "max_tokens")

    def test_token_param_uses_max_completion_tokens_with_openai_base_url(self):
        env = {"MODEL_OPENAI_ENDPOINT": "https://example-resource.openai.azure.com/openai/v1"}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve_token_param("gpt-5.4"), "max_completion_tokens")

    def test_token_param_honours_explicit_override(self):
        with patch.dict(os.environ, {"LLM_TOKEN_PARAM": "max_completion_tokens"}, clear=True):
            self.assertEqual(resolve_token_param("gpt-5.4"), "max_completion_tokens")


if __name__ == "__main__":
    unittest.main()
