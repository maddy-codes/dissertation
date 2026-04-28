"""
Pull a Trial Balance, Profit & Loss, and a per-nominal ledger summary from Xero
for a given client and year-end. Used by the automated review pipeline.

Important fixes vs the original:
- Maps trial balance rows to account codes via the embedded Xero AccountID
  (using `Attributes` on the row), not by regex on the display name.
- Pulls Manual Journals as well as Bank Transactions and Invoices, so journal
  postings to a P&L nominal are included in the per-account ledger.
- Preserves the sign of each transaction so spike/drop detection in
  `analyze_ledger` is meaningful.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from dateutil.relativedelta import relativedelta

from helpers.ledger_analyzer import analyze_ledger

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers for digging codes out of Xero report rows
# ---------------------------------------------------------------------------

def _row_account_id(row: Dict[str, Any]) -> Optional[str]:
    """Pull AccountID from a Xero report row's Attributes/Cell.Attributes."""
    for attr in row.get("Attributes", []) or []:
        if attr.get("Id") == "account":
            value = attr.get("Value")
            if value:
                return value
    for cell in row.get("Cells", []) or []:
        for attr in cell.get("Attributes", []) or []:
            if attr.get("Id") == "account":
                value = attr.get("Value")
                if value:
                    return value
    return None


def _flatten_rows(rows: List[Dict[str, Any]], target: List[Dict[str, Any]]) -> None:
    for r in rows:
        if r.get("RowType") == "Row":
            target.append(r)
        elif "Rows" in r:
            _flatten_rows(r["Rows"], target)


def _row_account_code(row: Dict[str, Any], account_lookup: Dict[str, Dict[str, Any]]) -> str:
    """Resolve account code for a TB/P&L row, preferring the embedded AccountID."""
    aid = _row_account_id(row)
    if aid and aid in account_lookup:
        code = account_lookup[aid].get("Code")
        if code:
            return str(code)
    cells = row.get("Cells", [])
    if not cells:
        return ""
    label = cells[0].get("Value", "")
    # Fallbacks: "1234 - Sales" or "Sales (1234)"
    if " - " in label:
        candidate = label.split(" - ")[0].strip()
        if candidate.replace("-", "").isalnum():
            return candidate
    if "(" in label and label.endswith(")"):
        candidate = label.rsplit("(", 1)[1].rstrip(")").strip()
        if candidate:
            return candidate
    return ""


# ---------------------------------------------------------------------------
# Per-nominal ledger fetch
# ---------------------------------------------------------------------------

def _date_str(payload: Dict[str, Any]) -> str:
    raw = payload.get("DateString") or payload.get("Date") or ""
    return raw[:10] if isinstance(raw, str) else ""


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Cell-level helpers for turning the raw Xero report cells into clean numbers
# ---------------------------------------------------------------------------

def _parse_money(value: Any) -> float:
    """Parse a Xero money cell value like '£1,234.56', '(1,234.56)' or '1234.56'."""
    if value is None:
        return 0.0
    s = str(value).strip()
    if not s:
        return 0.0
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()£$,€ ")
    s = s.replace(",", "")
    try:
        amt = float(s)
    except ValueError:
        return 0.0
    return -amt if negative else amt


def _tb_amount(cells: List[Dict[str, Any]]) -> float:
    """
    Resolve a Trial Balance row's net balance from its cells.

    Xero TB rows typically contain: [label, debit, credit, ytd, ...] or
    [label, debit, credit, balance]. We derive a signed net (Dr positive,
    Cr negative) so downstream comparisons can be done in a uniform space.
    """
    debit = _parse_money(cells[1].get("Value")) if len(cells) > 1 else 0.0
    credit = _parse_money(cells[2].get("Value")) if len(cells) > 2 else 0.0
    return debit - credit


def _pl_amount(cells: List[Dict[str, Any]]) -> float:
    """P&L rows usually have a single value column; take the last numeric cell."""
    for cell in reversed(cells[1:] or []):
        v = cell.get("Value")
        if v not in (None, ""):
            return _parse_money(v)
    return 0.0


def _format_money(amount: float) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}£{abs(amount):,.0f}"


def _row_has_activity(cells: List[Dict[str, Any]]) -> bool:
    """True if any non-label cell has a non-zero numeric value."""
    for cell in cells[1:] or []:
        if _parse_money(cell.get("Value")) != 0:
            return True
    return False


def _build_ledger_by_code(
    xero_client,
    tenant_id: str,
    s_date: Optional[date],
    e_date: Optional[date],
    account_lookup: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Aggregate Bank Transactions, Invoices and Manual Journals by AccountCode."""
    ledger: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    if not s_date or not e_date:
        return ledger

    def _push(code: str, entry: Dict[str, Any]) -> None:
        if not code:
            return
        ledger[str(code)].append(entry)

    # 1. Bank Transactions
    try:
        bt_resp = xero_client.get_bank_transactions(
            tenant_id, start_date=s_date, end_date=e_date, max_pages=100
        )
    except Exception as exc:
        logger.warning("Bank transactions fetch failed: %s", exc)
        bt_resp = {"BankTransactions": []}

    for bt in bt_resp.get("BankTransactions", []):
        contact = bt.get("Contact", {}).get("Name", "Unknown")
        dstr = _date_str(bt)
        # SPEND => money out (debit on expense), RECEIVE => money in (credit on income)
        sign = -1 if (bt.get("Type") or "").upper().startswith("RECEIVE") else 1
        for li in bt.get("LineItems", []):
            code = li.get("AccountCode")
            if not code:
                continue
            amount = _safe_float(li.get("LineAmount", 0)) * sign
            _push(code, {
                "Description": (li.get("Description") or contact).strip(),
                "Amount": amount,
                "Date": dstr,
                "Source": "BankTransaction",
                "Reference": bt.get("Reference", ""),
                "Contact": contact,
            })

    # 2. Invoices (sales = ACCREC, bills = ACCPAY)
    try:
        inv_resp = xero_client.get_invoices(
            tenant_id,
            start_date=s_date,
            end_date=e_date,
            statuses=["AUTHORISED", "PAID"],
            max_pages=100,
        )
    except Exception as exc:
        logger.warning("Invoices fetch failed: %s", exc)
        inv_resp = {"Invoices": []}

    # Sign by invoice type:
    #   ACCREC        -> -1 (sale credits income, shows negative on income accounts)
    #   ACCRECCREDIT  -> +1 (sales credit note reverses the sale)
    #   ACCPAY        -> +1 (bill debits expense)
    #   ACCPAYCREDIT  -> -1 (purchase credit note reverses the expense)
    invoice_sign = {
        "ACCREC": -1,
        "ACCRECCREDIT": 1,
        "ACCPAY": 1,
        "ACCPAYCREDIT": -1,
    }
    for inv in inv_resp.get("Invoices", []):
        contact = inv.get("Contact", {}).get("Name", "Unknown")
        dstr = _date_str(inv)
        sign = invoice_sign.get((inv.get("Type") or "").upper(), 1)
        for li in inv.get("LineItems", []):
            code = li.get("AccountCode")
            if not code:
                continue
            amount = _safe_float(li.get("LineAmount", 0)) * sign
            _push(code, {
                "Description": (li.get("Description") or contact).strip(),
                "Amount": amount,
                "Date": dstr,
                "Source": "Invoice",
                "Reference": inv.get("InvoiceNumber") or inv.get("Reference", ""),
                "Contact": contact,
            })

    # 3. Manual Journals (POSTED only)
    try:
        mj_resp = xero_client.get_manual_journals(
            tenant_id, start_date=s_date, end_date=e_date, max_pages=100
        )
    except Exception as exc:
        logger.warning("Manual journals fetch failed: %s", exc)
        mj_resp = {"ManualJournals": []}

    for mj in mj_resp.get("ManualJournals", []):
        if (mj.get("Status") or "").upper() != "POSTED":
            continue
        narration = mj.get("Narration", "Manual Journal")
        dstr = _date_str(mj)
        for jl in mj.get("JournalLines", []):
            code = None
            if jl.get("AccountCode"):
                code = jl.get("AccountCode")
            elif jl.get("AccountID") and jl["AccountID"] in account_lookup:
                code = account_lookup[jl["AccountID"]].get("Code")
            if not code:
                continue
            # Xero's LineAmount on manual journals is signed (debit positive, credit negative)
            amount = _safe_float(jl.get("LineAmount", 0))
            desc = (jl.get("Description") or narration).strip()
            _push(code, {
                "Description": desc,
                "Amount": amount,
                "Date": dstr,
                "Source": "ManualJournal",
                "Reference": narration,
                "Contact": "",
            })

    return ledger


# ---------------------------------------------------------------------------
# Top-level entry point used by the analysis pipeline
# ---------------------------------------------------------------------------

def fetch_and_format_xero_data(
    xero_client,
    tenant_id: str,
    report_date: date,
    comparison_date: Optional[date] = None,
) -> Tuple[List[Dict[str, str]], pd.DataFrame]:
    """
    Build the per-account briefing the automated review crew consumes.

    Returns:
        messages: list of {"name": <account label>, "message": <briefing text>}
        mp_df:    DataFrame mapping Xero account labels and codes to summary slots.
    """
    fy_start = report_date - relativedelta(years=1) + timedelta(days=1)

    tb_json = xero_client.get_trial_balance(tenant_id, report_date=report_date)
    pl_json = xero_client.get_profit_and_loss(
        tenant_id, start_date=fy_start, end_date=report_date
    )

    comp_tb_json: Optional[Dict[str, Any]] = None
    comp_pl_json: Optional[Dict[str, Any]] = None
    comp_start: Optional[date] = None
    if comparison_date:
        comp_start = comparison_date - relativedelta(years=1) + timedelta(days=1)
        try:
            comp_tb_json = xero_client.get_trial_balance(
                tenant_id, report_date=comparison_date
            )
            comp_pl_json = xero_client.get_profit_and_loss(
                tenant_id, start_date=comp_start, end_date=comparison_date
            )
        except Exception as exc:
            logger.warning("Comparison-period fetch failed: %s", exc)

    # Account dictionary keyed by AccountID for fast row->code resolution
    account_lookup: Dict[str, Dict[str, Any]] = {}
    try:
        accounts_json = xero_client.get_accounts(tenant_id)
        for acc in accounts_json.get("Accounts", []):
            if acc.get("AccountID"):
                account_lookup[acc["AccountID"]] = acc
    except Exception as exc:
        logger.warning("Accounts fetch failed: %s", exc)

    logger.info("Building ledger for current year %s -> %s", fy_start, report_date)
    curr_ledger = _build_ledger_by_code(
        xero_client, tenant_id, fy_start, report_date, account_lookup
    )

    if comp_start and comparison_date:
        logger.info(
            "Building ledger for prior year %s -> %s", comp_start, comparison_date
        )
        prior_ledger = _build_ledger_by_code(
            xero_client, tenant_id, comp_start, comparison_date, account_lookup
        )
    else:
        prior_ledger = defaultdict(list)

    tb_rows: List[Dict[str, Any]] = []
    if tb_json and tb_json.get("Reports"):
        _flatten_rows(tb_json["Reports"][0].get("Rows", []), tb_rows)

    pl_rows: List[Dict[str, Any]] = []
    if pl_json and pl_json.get("Reports"):
        _flatten_rows(pl_json["Reports"][0].get("Rows", []), pl_rows)

    comp_tb_rows: List[Dict[str, Any]] = []
    if comp_tb_json and comp_tb_json.get("Reports"):
        _flatten_rows(comp_tb_json["Reports"][0].get("Rows", []), comp_tb_rows)

    comp_pl_rows: List[Dict[str, Any]] = []
    if comp_pl_json and comp_pl_json.get("Reports"):
        _flatten_rows(comp_pl_json["Reports"][0].get("Rows", []), comp_pl_rows)

    messages: List[Dict[str, str]] = []
    out_map: Dict[str, List[Any]] = {
        "xero_names": [],
        "xero_codes": [],
        "ai_summary": [],
    }

    for row in tb_rows:
        cells = row.get("Cells", [])
        if not cells:
            continue
        label = (cells[0].get("Value") or "").strip()
        if not label or label.lower().startswith("total"):
            continue

        account_code = _row_account_code(row, account_lookup)

        # Look up the matching rows in the comparison reports
        pl_match = next(
            (p for p in pl_rows if p.get("Cells") and p["Cells"][0].get("Value") == label),
            None,
        )
        comp_tb_match = next(
            (p for p in comp_tb_rows if p.get("Cells") and p["Cells"][0].get("Value") == label),
            None,
        )
        comp_pl_match = next(
            (p for p in comp_pl_rows if p.get("Cells") and p["Cells"][0].get("Value") == label),
            None,
        )

        # Skip rows that are pure section headers / have zero activity in BOTH
        # years AND no transactional data — these just generate noise notes.
        has_curr_activity = _row_has_activity(cells)
        has_prior_activity = bool(comp_tb_match) and _row_has_activity(
            comp_tb_match.get("Cells", [])
        )
        curr_txs_for_code = curr_ledger.get(str(account_code), []) if account_code else []
        prior_txs_for_code = prior_ledger.get(str(account_code), []) if account_code else []
        if (
            not has_curr_activity
            and not has_prior_activity
            and not curr_txs_for_code
            and not prior_txs_for_code
        ):
            continue

        # Resolve clean numbers
        tb_curr = _tb_amount(cells)
        tb_prior = _tb_amount(comp_tb_match.get("Cells", [])) if comp_tb_match else 0.0
        pl_curr = _pl_amount(pl_match.get("Cells", [])) if pl_match else 0.0
        pl_prior = _pl_amount(comp_pl_match.get("Cells", [])) if comp_pl_match else 0.0

        # Use TB as the headline; fall back to P&L if TB is zero (income/expense)
        headline_curr = tb_curr if tb_curr else pl_curr
        headline_prior = tb_prior if tb_prior else pl_prior
        variance_abs = headline_curr - headline_prior
        if abs(headline_prior) > 0.01:
            variance_pct = (variance_abs / abs(headline_prior)) * 100.0
        else:
            variance_pct = 0.0 if abs(headline_curr) < 0.01 else float("inf")

        # Build a clean, sectioned briefing the LLM can actually use
        lines: List[str] = []
        lines.append(f"=== ACCOUNT: {label} (Code {account_code or 'unresolved'}) ===")
        lines.append("")
        lines.append(
            f"CURRENT YEAR (to {report_date.isoformat()}):"
        )
        lines.append(
            f"  Trial Balance net (Dr +ve / Cr -ve): {_format_money(tb_curr)}"
        )
        if pl_match:
            lines.append(f"  P&L movement: {_format_money(pl_curr)}")
        lines.append("")

        if comp_tb_match or comp_pl_match:
            comp_label = comparison_date.isoformat() if comparison_date else "prior year"
            lines.append(f"PRIOR YEAR (to {comp_label}):")
            lines.append(
                f"  Trial Balance net (Dr +ve / Cr -ve): {_format_money(tb_prior)}"
            )
            if comp_pl_match:
                lines.append(f"  P&L movement: {_format_money(pl_prior)}")
            lines.append("")
            lines.append("YEAR-ON-YEAR VARIANCE:")
            direction = "increase" if variance_abs > 0 else "decrease" if variance_abs < 0 else "no change"
            pct_str = (
                "n/a"
                if variance_pct == float("inf")
                else f"{variance_pct:+.1f}%"
            )
            lines.append(
                f"  Absolute: {_format_money(variance_abs)} ({direction})"
            )
            lines.append(f"  Percentage: {pct_str}")
            lines.append("")

        if account_code:
            lines.append(f"TRANSACTIONAL INSIGHTS (Code {account_code}):")
            lines.append(analyze_ledger(curr_txs_for_code, prior_txs_for_code))
        else:
            lines.append(
                "TRANSACTIONAL INSIGHTS: account code could not be resolved for this row, "
                "so individual transactions are not available — base the note on the headline figures only."
            )

        messages.append({"name": label, "message": "\n".join(lines)})

        out_map["xero_names"].append(label)
        out_map["xero_codes"].append(account_code)
        out_map["ai_summary"].append("")

    mp_df = pd.DataFrame(out_map)
    return messages, mp_df
