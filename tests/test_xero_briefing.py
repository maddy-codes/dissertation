import unittest
from datetime import date

from helpers.xero_api_parser import fetch_and_format_xero_data


class _FakeXeroClient:
    def get_trial_balance(self, tenant_id, report_date):
        return {
            "Reports": [
                {
                    "Rows": [
                        {
                            "RowType": "Row",
                            "Attributes": [{"Id": "account", "Value": "acc-1"}],
                            "Cells": [
                                {"Value": "Software Costs"},
                                {"Value": "120.00"},
                                {"Value": "0.00"},
                            ],
                        }
                    ]
                }
            ]
        }

    def get_profit_and_loss(self, tenant_id, start_date, end_date):
        return {
            "Reports": [
                {
                    "Rows": [
                        {
                            "RowType": "Row",
                            "Cells": [
                                {"Value": "Software Costs"},
                                {"Value": "120.00"},
                            ],
                        }
                    ]
                }
            ]
        }

    def get_accounts(self, tenant_id):
        return {
            "Accounts": [
                {"AccountID": "acc-1", "Code": "7702", "Name": "Software Costs"}
            ]
        }

    def get_bank_transactions(self, tenant_id, start_date, end_date, max_pages=100):
        return {
            "BankTransactions": [
                {
                    "Type": "SPEND",
                    "DateString": "2025-03-01",
                    "Reference": "BT-1",
                    "Contact": {"Name": "Adobe"},
                    "LineItems": [
                        {"AccountCode": "7702", "Description": "Adobe", "LineAmount": "40.00"}
                    ],
                }
            ]
        }

    def get_invoices(self, tenant_id, start_date, end_date, statuses, max_pages=100):
        return {
            "Invoices": [
                {
                    "Type": "ACCPAY",
                    "DateString": "2025-03-02",
                    "InvoiceNumber": "INV-1",
                    "Reference": "Bill",
                    "Contact": {"Name": "Microsoft"},
                    "LineItems": [
                        {"AccountCode": "7702", "Description": "M365", "LineAmount": "50.00"}
                    ],
                }
            ]
        }

    def get_manual_journals(self, tenant_id, start_date, end_date, max_pages=100):
        return {
            "ManualJournals": [
                {
                    "Status": "POSTED",
                    "DateString": "2025-03-03",
                    "Narration": "Year-end accrual",
                    "JournalLines": [
                        {"AccountCode": "7702", "Description": "Accrual", "LineAmount": "30.00"}
                    ],
                }
            ]
        }


class XeroBriefingTests(unittest.TestCase):
    def test_briefing_includes_source_breakdown_for_processed_transactions(self):
        messages, mp_df = fetch_and_format_xero_data(
            _FakeXeroClient(),
            tenant_id="tenant-1",
            report_date=date(2025, 3, 31),
            comparison_date=date(2024, 3, 31),
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(mp_df.iloc[0]["xero_codes"], "7702")
        self.assertIn(
            "Current year source counts: Total processed: 3 (Bank Transactions: 1, Invoices: 1, Manual Journals: 1)",
            messages[0]["message"],
        )


if __name__ == "__main__":
    unittest.main()
