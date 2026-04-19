import unittest

from experiments.scoring import score_output
from experiments.types import Example, ScoringConfig


class ScoringTests(unittest.TestCase):
    def test_format_single_paragraph(self):
        ex = Example(example_id="ex", transactions=[])
        s = score_output(
            output_text="One paragraph only.",
            example=ex,
            context_text="",
            scoring=ScoringConfig(require_single_paragraph=True, forbid_ref_numbers=True),
        )
        self.assertTrue(s["format"]["single_paragraph"])

    def test_format_multiple_paragraphs(self):
        ex = Example(example_id="ex", transactions=[])
        s = score_output(
            output_text="Para1.\n\nPara2.",
            example=ex,
            context_text="",
            scoring=ScoringConfig(require_single_paragraph=True, forbid_ref_numbers=False),
        )
        self.assertFalse(s["format"]["single_paragraph"])


if __name__ == "__main__":
    unittest.main()

