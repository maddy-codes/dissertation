import unittest

from experiments.benchmark_dissertation_methods import parse_example_ids, select_examples
from experiments.prompt_engineering_gpt54 import ValidationExample


class BenchmarkDissertationMethodsTests(unittest.TestCase):
    def test_parse_example_ids_handles_blank_and_csv_values(self):
        self.assertEqual(parse_example_ids(None), [])
        self.assertEqual(parse_example_ids(""), [])
        self.assertEqual(parse_example_ids("val_064, 79 ,val_084"), ["val_064", "79", "val_084"])

    def test_select_examples_accepts_val_ids_and_numeric_ids(self):
        examples = [
            ValidationExample("val_064", "S", "U64", "G64"),
            ValidationExample("val_079", "S", "U79", "G79"),
            ValidationExample("val_084", "S", "U84", "G84"),
        ]

        selected = select_examples(examples, ["64", "val_084"])

        self.assertEqual([example.example_id for example in selected], ["val_064", "val_084"])

    def test_select_examples_raises_for_unknown_id(self):
        examples = [ValidationExample("val_064", "S", "U64", "G64")]

        with self.assertRaisesRegex(RuntimeError, "Unknown validation example ids"):
            select_examples(examples, ["val_999"])


if __name__ == "__main__":
    unittest.main()
