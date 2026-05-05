import csv
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT / "dissertation_material" / "method_benchmark_manifest.csv"
COMPARISON_PATH = ROOT / "dissertation_material" / "method_example_comparison.csv"


class EvaluationManifestTests(unittest.TestCase):
    def test_benchmark_manifest_lists_all_seven_methods(self):
        with BENCHMARK_PATH.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 7)
        self.assertEqual(sum(1 for row in rows if row["method_family"] == "Fine-tuned GPT-4.1"), 4)
        self.assertEqual(sum(1 for row in rows if row["method_family"] == "Prompt engineered GPT-5.4"), 3)
        self.assertTrue(all(float(row["mean_generation_seconds"]) > 0 for row in rows))
        self.assertTrue(all(int(row["run_count"]) == 3 for row in rows))

    def test_comparison_manifest_includes_reference_and_all_method_types(self):
        with COMPARISON_PATH.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        labels = [row["method_label"] for row in rows]
        self.assertIn("Gold accountant note", labels)
        self.assertIn("GPT-4.1 Fine-Tuned 4", labels)
        self.assertIn("GPT-5.4 Few-Shot", labels)
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(row["example_id"] == "val_064" for row in rows))


if __name__ == "__main__":
    unittest.main()
