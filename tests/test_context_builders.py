import unittest

from experiments.context import build_context_variants
from experiments.types import Example, MaterialityPolicy, SubscriptionPolicy


class ContextBuildersTests(unittest.TestCase):
    def test_raw_degradation_variants_from_transactions(self):
        ex = Example(
            example_id="ex1",
            transactions=[
                {"Total": 10, "Contact": {"Name": "A"}},
                {"Total": 11, "Contact": {"Name": "A"}},
                {"Total": 12, "Contact": {"Name": "B"}},
                {"Total": 13, "Contact": {"Name": "C"}},
            ],
        )
        ctxs = build_context_variants(
            ex,
            requested_modes=["raw", "materiality+subscriptions"],
            materiality_policy=MaterialityPolicy(relative_fraction=0.01),
            subscription_policy=SubscriptionPolicy(min_occurrences=3),
        )
        self.assertIn("raw_25", ctxs)
        self.assertIn("raw_50", ctxs)
        self.assertIn("raw_100", ctxs)
        self.assertIn("materiality+subscriptions", ctxs)


if __name__ == "__main__":
    unittest.main()

