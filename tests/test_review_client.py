import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agents.crew_manager import ReviewCrew


class _FakeCompletions:
    def __init__(self, fail_on_max_completion_tokens=False):
        self.fail_on_max_completion_tokens = fail_on_max_completion_tokens
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_on_max_completion_tokens and "max_completion_tokens" in kwargs:
            raise TypeError("Completions.create() got an unexpected keyword argument 'max_completion_tokens'")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))]
        )


class _FakeClient:
    def __init__(self, fail_on_max_completion_tokens=False):
        self.chat = SimpleNamespace(
            completions=_FakeCompletions(
                fail_on_max_completion_tokens=fail_on_max_completion_tokens
            )
        )


class ReviewClientTests(unittest.TestCase):
    def test_direct_review_client_sends_no_token_limit_argument(self):
        fake_client = _FakeClient()
        crew = object.__new__(ReviewCrew)
        env = {
            "MODEL_OPENAI_ENDPOINT": "https://example-resource.openai.azure.com/openai/v1",
            "MODEL_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("agents.crew_manager.OpenAI", return_value=fake_client):
                result = crew._invoke_direct_review_client(
                    "gpt-5.4",
                    [{"role": "user", "content": "hi"}],
                )
        self.assertEqual(result, "OK")
        self.assertNotIn("max_completion_tokens", fake_client.chat.completions.calls[0])
        self.assertNotIn("max_tokens", fake_client.chat.completions.calls[0])

    def test_direct_review_client_still_sets_temperature_and_seed(self):
        fake_client = _FakeClient()
        crew = object.__new__(ReviewCrew)
        env = {
            "MODEL_OPENAI_ENDPOINT": "https://example-resource.openai.azure.com/openai/v1",
            "MODEL_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("agents.crew_manager.OpenAI", return_value=fake_client):
                result = crew._invoke_direct_review_client(
                    "gpt-5.4",
                    [{"role": "user", "content": "hi"}],
                )
        self.assertEqual(result, "OK")
        self.assertEqual(fake_client.chat.completions.calls[0]["temperature"], 0.0)
        self.assertEqual(fake_client.chat.completions.calls[0]["seed"], 42)


if __name__ == "__main__":
    unittest.main()
