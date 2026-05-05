import json
import tempfile
import unittest
from pathlib import Path

from experiments.data_pipeline import (
    analyze_xero_transactions,
    build_records_from_local,
    extract_company_name,
    process_xero_json,
    split_and_write,
)


class DataPipelineTests(unittest.TestCase):
    def sample_raw_json(self):
        return {
            "metadata": {"year_end_date": "2024-03-31"},
            "original_json_data": {
                "paragraphs": [
                    {"paragraph_title": "P&L", "content": ["Turnover increased due to new contracts."]},
                ]
            },
            "xero_data": {
                "balance_sheet": {
                    "Reports": [
                        {
                            "Rows": [
                                {"RowType": "SummaryRow", "Cells": [{"Value": "Cash"}, {"Value": "1234.56"}]},
                            ]
                        }
                    ]
                },
                "bank_transactions": {
                    "BankTransactions": [
                        {"Contact": {"Name": "Adobe"}, "Total": "15.00", "DateString": "2024-01-01"},
                        {"Contact": {"Name": "Adobe"}, "Total": "15.00", "DateString": "2024-02-01"},
                        {"Contact": {"Name": "Adobe"}, "Total": "15.00", "DateString": "2024-03-01"},
                        {"Contact": {"Name": "One Off"}, "Total": "250.00", "DateString": "2024-03-15"},
                    ]
                },
            },
        }

    def test_extract_company_name_removes_prefix_and_suffix(self):
        name = extract_company_name("structured/Chris/A0254_-_Ashton_Wealth_Management_Spreadsheets_2024.json")
        self.assertEqual(name, "Ashton Wealth Management")

    def test_analyze_xero_transactions_detects_subscription_and_one_off(self):
        summary = analyze_xero_transactions(self.sample_raw_json())
        self.assertIn("Found subscription: Adobe", summary)
        self.assertIn("NEW PAYEE: GBP 250.00 paid to One Off", summary)

    def test_process_xero_json_returns_chat_record(self):
        record = process_xero_json(self.sample_raw_json())
        self.assertIsNotNone(record)
        self.assertEqual([message["role"] for message in record.messages], ["system", "user", "assistant"])
        self.assertIn("YEAR END DATE: 2024-03-31", record.messages[1]["content"])

    def test_build_records_and_split_write_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "sample.json"
            source.write_text(json.dumps(self.sample_raw_json()), encoding="utf-8")
            records = build_records_from_local([source])
            split = split_and_write(records, tmp_path / "out", validation_fraction=0.5)

            self.assertEqual(len(records), 1)
            self.assertTrue(split.validation_path.exists())
            self.assertEqual(split.validation_count, 1)


if __name__ == "__main__":
    unittest.main()
