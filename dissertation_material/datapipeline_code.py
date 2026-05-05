"""Dissertation data-pipeline wrapper.

This file is intentionally small and importable. The reusable implementation
lives in `experiments.data_pipeline` so the submitted codebase can be tested
without requiring Google Colab, interactive OAuth input, or embedded secrets.
"""

from experiments.data_pipeline import (
    analyze_xero_transactions,
    balance_sheet_summary,
    build_records_from_local,
    build_user_context,
    extract_company_name,
    process_xero_json,
    split_and_write,
)

__all__ = [
    "analyze_xero_transactions",
    "balance_sheet_summary",
    "build_records_from_local",
    "build_user_context",
    "extract_company_name",
    "process_xero_json",
    "split_and_write",
]
