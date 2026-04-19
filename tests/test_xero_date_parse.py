import unittest
from datetime import date

from integrations.xero_api import parse_year_end_date


class XeroDateParseTests(unittest.TestCase):
    def test_parse_iso(self):
        self.assertEqual(parse_year_end_date("2022-03-31"), date(2022, 3, 31))


if __name__ == "__main__":
    unittest.main()

