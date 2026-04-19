from __future__ import annotations

from typing import Any, Optional

from integrations.xero_api import XeroClient, default_two_year_window, parse_year_end_date


def enrich_example_json_from_xero_api(
    *,
    example_json: dict[str, Any],
    tenant_id: Optional[str] = None,
    year_end_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Replace or fill `xero_data` by fetching directly from the Xero API.

    The input JSON can be either:
    - a descriptor with `metadata.tenant_id` and `metadata.year_end_date`
    - or any JSON where those fields can be provided explicitly.
    """
    md = example_json.get("metadata") if isinstance(example_json.get("metadata"), dict) else {}
    tenant = tenant_id or (md.get("tenant_id") if isinstance(md.get("tenant_id"), str) else None)
    if not tenant:
        raise RuntimeError("Missing tenant_id for API enrichment (metadata.tenant_id).")

    yed = year_end_date or (md.get("year_end_date") if isinstance(md.get("year_end_date"), str) else None)
    year_end = parse_year_end_date(yed) if yed else None
    if not year_end:
        raise RuntimeError("Missing/invalid year_end_date for API enrichment (metadata.year_end_date).")

    start_date, end_date = default_two_year_window(year_end)

    client = XeroClient.from_env()
    accounts = client.get_accounts(tenant)
    bank_transactions = client.get_bank_transactions(tenant, start_date, end_date)
    balance_sheet = client.get_balance_sheet(tenant, year_end)

    out = dict(example_json)
    out["xero_data"] = {
        "accounts": accounts,
        "bank_transactions": bank_transactions,
        "balance_sheet": balance_sheet,
    }
    return out

