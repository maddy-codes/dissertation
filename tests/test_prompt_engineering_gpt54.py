import json
import tempfile
import unittest
from pathlib import Path

from experiments.prompt_engineering_gpt54 import build_messages, load_examples


class PromptEngineeringGpt54Tests(unittest.TestCase):
    def test_load_examples_extracts_roles(self):
        record = {
            "messages": [
                {"role": "system", "content": "System"},
                {"role": "user", "content": "User"},
                {"role": "assistant", "content": "Gold"},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "validation.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            examples = load_examples(path)

        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0].example_id, "val_001")
        self.assertEqual(examples[0].system_prompt, "System")
        self.assertEqual(examples[0].user_prompt, "User")
        self.assertEqual(examples[0].gold_response, "Gold")

    def test_build_messages_adds_few_shot_examples_before_target(self):
        examples = [
            type("Example", (), {"system_prompt": "S", "user_prompt": "U1", "gold_response": "A1"})(),
            type("Example", (), {"system_prompt": "S", "user_prompt": "U2", "gold_response": "A2"})(),
            type("Example", (), {"system_prompt": "S", "user_prompt": "Target", "gold_response": "Gold"})(),
        ]

        messages = build_messages("few-shot", examples[2], examples[:2])

        self.assertEqual([message["role"] for message in messages], ["system", "user", "assistant", "user", "assistant", "user"])
        self.assertEqual(messages[-1]["content"], "Target")


if __name__ == "__main__":
    unittest.main()
