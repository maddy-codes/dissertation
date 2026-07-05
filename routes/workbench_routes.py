"""Working papers (the per-account review preparation screen) and its API."""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from setup.models import ClientAccess, ReviewNote, db
from helpers.openai_config import (
    resolve_azure_openai_api_key,
    resolve_azure_openai_api_version,
    resolve_azure_openai_endpoint,
    resolve_openai_base_url,
    resolve_scan_deployment_name,
)

logger = logging.getLogger(__name__)

workbench_bp = Blueprint("workbench", __name__)


def _xero_client():
    from integrations.xero_api import XeroClient

    token_data = current_user.get_xero_token()
    if not token_data:
        return None
    return XeroClient(
        client_id=os.environ.get("XERO_CLIENT_ID"),
        client_secret=os.environ.get("XERO_CLIENT_SECRET"),
        refresh_token=token_data.get("refresh_token"),
        user=current_user,
    )


def _resolve_account_code_from_row(cells, account_lookup_by_id, row_attrs):
    """Pull AccountID -> Code from row attributes if present."""
    for attr in row_attrs or []:
        if attr.get("Id") == "account":
            aid = attr.get("Value")
            if aid in account_lookup_by_id:
                return account_lookup_by_id[aid].get("Code", ""), aid
    if cells:
        for cell in cells:
            for attr in cell.get("Attributes", []) or []:
                if attr.get("Id") == "account":
                    aid = attr.get("Value")
                    if aid in account_lookup_by_id:
                        return account_lookup_by_id[aid].get("Code", ""), aid
    return "", None


def _has_value(raw):
    """True if a Xero TB cell string represents a non-zero amount."""
    try:
        s = str(raw or "0").replace(",", "").replace("(", "-").replace(")", "")
        return float(s) != 0
    except (TypeError, ValueError):
        return False


_SOURCE_LABELS = {
    "BankTransaction": "Bank Transaction",
    "Invoice": "Invoice",
    "ManualJournal": "Manual Journal",
}


def _meaningful(text):
    """Strip a Xero text field; punctuation-only placeholders (".", "-") don't count."""
    stripped = (text or "").strip()
    return stripped if any(ch.isalnum() for ch in stripped) else ""


def _entry_label(entry):
    """Best available description for a ledger entry.

    Some Xero line items carry a punctuation placeholder (e.g. ".") instead of
    a real Description, which is truthy so it slips past a naive `or` fallback
    and renders as a bare dot in the drilldown. Fall through Contact, then
    Reference, then the entry's source type, so the UI never shows a blank.
    """
    desc = _meaningful(entry.get("Description"))
    if desc:
        return desc
    contact = _meaningful(entry.get("Contact"))
    if contact and contact.lower() != "unknown":
        return contact
    reference = _meaningful(entry.get("Reference"))
    if reference:
        return reference
    return _SOURCE_LABELS.get(entry.get("Source"), "Transaction")


@workbench_bp.route("/workbench", methods=["POST"])
@login_required
def workbench():
    tenant_id = request.form.get("tenant_id")
    current_year_end = request.form.get("current_year_end")
    comparison_year_end = request.form.get("comparison_year_end")

    if not tenant_id:
        flash("Please select a Xero client before opening the working papers.")
        return redirect(url_for("main.dashboard"))

    tenant_name = "Unnamed Client"
    if current_user.role == "client":
        grant = ClientAccess.query.filter_by(user_id=current_user.id, tenant_id=tenant_id).first()
        tenant_name = (grant.tenant_name if grant else None) or tenant_name
    else:
        try:
            xero_client = _xero_client()
            if xero_client:
                for conn in xero_client.list_connections():
                    if conn["tenantId"] == tenant_id:
                        tenant_name = conn["tenantName"]
                        break
        except Exception as exc:
            logger.warning("Could not resolve tenant name for %s: %s", tenant_id, exc)

    return render_template(
        "workbench.html",
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        current_year_end=current_year_end,
        comparison_year_end=comparison_year_end,
    )


@workbench_bp.route("/api/workbench/fetch_tb/<tenant_id>", methods=["GET"])
@login_required
def fetch_tb(tenant_id):
    xero_client = _xero_client()
    if not xero_client:
        return jsonify({"status": "Error", "message": "No Xero token"}), 400

    try:
        current_date_str = request.args.get("current_year_end")
        report_date = (
            date.fromisoformat(current_date_str) if current_date_str else date.today()
        )
        prev_report_date = report_date - relativedelta(years=1)

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(
                xero_client.get_trial_balance, tenant_id, report_date=report_date
            )
            f2 = executor.submit(
                xero_client.get_trial_balance, tenant_id, report_date=prev_report_date
            )
            tb_json = f1.result()
            prev_tb_json = f2.result()

        # Build account lookup so we can resolve codes via embedded AccountID
        accounts_lookup = {}
        try:
            for acc in xero_client.get_accounts(tenant_id).get("Accounts", []):
                if acc.get("AccountID"):
                    accounts_lookup[acc["AccountID"]] = acc
        except Exception as exc:
            logger.warning("Accounts fetch failed: %s", exc)

        def collect(rows, into):
            for r in rows:
                if r.get("RowType") == "Row":
                    cells = r.get("Cells", [])
                    if cells and cells[0].get("Value") and cells[0].get("Value") != "Total":
                        into[cells[0].get("Value")] = (cells, r.get("Attributes", []))
                elif "Rows" in r:
                    collect(r["Rows"], into)

        tb_dict = {}
        prev_tb_dict = {}
        if tb_json.get("Reports"):
            collect(tb_json["Reports"][0].get("Rows", []), tb_dict)
        if prev_tb_json.get("Reports"):
            collect(prev_tb_json["Reports"][0].get("Rows", []), prev_tb_dict)

        tb_raw_data = []
        for label, (cells, attrs) in tb_dict.items():
            debit = cells[1].get("Value", "0") if len(cells) > 1 else "0"
            credit = cells[2].get("Value", "0") if len(cells) > 2 else "0"
            # Debit/credit are mutually exclusive per TB row, so the net
            # balance is whichever side actually holds a value — using debit
            # alone left income (credit-only) rows showing a blank balance.
            balance = debit if _has_value(debit) else credit
            prev_cells = prev_tb_dict.get(label, ([], []))[0]
            prev_balance = prev_cells[1].get("Value", "0") if len(prev_cells) > 1 else "0"

            code, account_id = _resolve_account_code_from_row(cells, accounts_lookup, attrs)
            if not code and " - " in label:
                head = label.split(" - ")[0].strip()
                if head:
                    code = head

            tb_raw_data.append(
                {
                    "account": label,
                    "code": code,
                    "account_id": account_id,
                    "debit": debit,
                    "credit": credit,
                    "balance": balance,
                    "prev_balance": prev_balance,
                }
            )

        return jsonify({"status": "Success", "tb_raw": tb_raw_data})
    except Exception as exc:
        logger.exception("fetch_tb failed")
        return jsonify({"status": "Error", "message": str(exc)}), 500


@workbench_bp.route("/api/workbench/analyze_scope_batch/<tenant_id>", methods=["POST"])
@login_required
def analyze_scope_batch(tenant_id):
    from helpers.batch_analyzer import analyze_nominal_batch

    payload = request.get_json(silent=True) or {}
    tb_data = payload.get("tb_data", [])
    global_mat = payload.get("global_materiality", 1000)

    try:
        results = analyze_nominal_batch(tb_data, float(global_mat))
        return jsonify(
            {
                "status": "Success",
                "data": {"coa_suggestions": results},
                "model": resolve_scan_deployment_name(),
            }
        )
    except Exception as exc:
        logger.exception("analyze_scope_batch failed")
        return jsonify({"status": "Error", "message": str(exc)}), 500


@workbench_bp.route("/api/workbench/save_draft/<tenant_id>", methods=["POST"])
@login_required
def save_draft(tenant_id):
    import uuid

    payload = request.get_json(silent=True) or {}
    current_year_end = payload.get("current_year_end")
    comparison_year_end = payload.get("comparison_year_end")
    draft_state = payload.get("draft_state", [])

    draft = ReviewNote.query.filter_by(
        user_id=current_user.id, tenant_id=tenant_id, status="DRAFT"
    ).first()
    if not draft:
        draft = ReviewNote(
            user_id=current_user.id,
            tenant_id=tenant_id,
            run_id=f"draft_{uuid.uuid4().hex[:8]}",
            status="DRAFT",
            year_end=current_year_end,
            year_start=comparison_year_end,
        )
        db.session.add(draft)
        db.session.commit()

    draft_file = os.path.join(
        current_app.config["UPLOAD_FOLDER"], f"{draft.run_id}_draft.json"
    )
    with open(draft_file, "w") as f:
        json.dump(draft_state, f)

    return jsonify({"status": "Success", "message": "Draft saved"})


@workbench_bp.route("/api/workbench/load_draft/<tenant_id>", methods=["GET"])
@login_required
def load_draft(tenant_id):
    draft = ReviewNote.query.filter_by(
        user_id=current_user.id, tenant_id=tenant_id, status="DRAFT"
    ).first()
    if draft:
        draft_file = os.path.join(
            current_app.config["UPLOAD_FOLDER"], f"{draft.run_id}_draft.json"
        )
        if os.path.exists(draft_file):
            with open(draft_file) as f:
                draft_state = json.load(f)
            return jsonify(
                {
                    "status": "Success",
                    "draft_state": draft_state,
                    "current_year_end": draft.year_end,
                    "comparison_year_end": draft.year_start,
                }
            )

    return jsonify({"status": "NotFound"})


@workbench_bp.route("/api/workbench/nominal_transactions/<tenant_id>", methods=["GET"])
@login_required
def nominal_transactions(tenant_id):
    """
    Return the top transactions hitting a single nominal account for the
    current financial year.

    Aggregates Bank Transactions, Invoices and posted Manual Journals via
    the same helper the review pipeline uses, so the drilldown matches
    what the LLM is briefed on. (Xero's Accounting API does not expose a
    "DetailedTransactionReport" endpoint — calling that returns 404, which
    is what the previous implementation tripped over.)
    """
    account_code = request.args.get("account_code")
    account_name = request.args.get("account_name")
    current_year_end = request.args.get("current_year_end")
    if not current_year_end or (not account_code and not account_name):
        return jsonify({"status": "Error", "message": "Missing parameter"}), 400

    xero_client = _xero_client()
    if not xero_client:
        return jsonify({"status": "Error", "message": "No Xero token"}), 400

    try:
        # Resolve the account (and its code, if we only got the name)
        accounts = xero_client.get_accounts(tenant_id)
        account_lookup: dict[str, dict] = {}
        resolved_code: str | None = None
        for acc in accounts.get("Accounts", []):
            acc_id = acc.get("AccountID")
            if acc_id:
                account_lookup[acc_id] = acc
            if account_code and acc.get("Code") == account_code:
                resolved_code = acc.get("Code")
            elif account_name and acc.get("Name") == account_name:
                resolved_code = acc.get("Code")

        if account_code and not resolved_code:
            resolved_code = account_code

        if not resolved_code:
            return jsonify({"status": "Success", "transactions": []})

        report_date = date.fromisoformat(current_year_end)
        start_date = report_date - relativedelta(years=1) + timedelta(days=1)

        from helpers.xero_api_parser import _build_ledger_by_code

        ledger = _build_ledger_by_code(
            xero_client, tenant_id, start_date, report_date, account_lookup
        )
        entries = ledger.get(str(resolved_code), [])

        # Reshape for the workbench drilldown JS:
        # { date, desc, amount }
        transactions = [
            {
                "date": e.get("Date", ""),
                "desc": _entry_label(e),
                "reference": e.get("Reference", ""),
                "source": e.get("Source", ""),
                "amount": float(e.get("Amount", 0.0) or 0.0),
            }
            for e in entries
        ]
        transactions.sort(key=lambda x: abs(x["amount"]), reverse=True)
        return jsonify({"status": "Success", "transactions": transactions[:10]})
    except Exception as exc:
        logger.exception("nominal_transactions failed")
        return jsonify({"status": "Error", "message": str(exc)}), 500


@workbench_bp.route("/api/workbench/prime_ledger/<tenant_id>", methods=["GET"])
@login_required
def prime_ledger(tenant_id):
    xero_client = _xero_client()
    if not xero_client:
        return jsonify({"status": "Error", "message": "No Xero token"}), 400

    try:
        current_date_str = request.args.get("current_year_end")
        report_date = (
            date.fromisoformat(current_date_str) if current_date_str else date.today()
        )
    except ValueError:
        report_date = date.today()

    start_date = report_date - relativedelta(years=1) + timedelta(days=1)
    prev_report_date = report_date - relativedelta(years=1)
    prev_start_date = prev_report_date - relativedelta(years=1) + timedelta(days=1)

    try:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=6) as executor:
            executor.submit(
                xero_client.get_bank_transactions,
                tenant_id,
                start_date=start_date,
                end_date=report_date,
            )
            executor.submit(
                xero_client.get_invoices,
                tenant_id,
                start_date=start_date,
                end_date=report_date,
                statuses=["AUTHORISED", "PAID"],
            )
            executor.submit(
                xero_client.get_manual_journals,
                tenant_id,
                start_date=start_date,
                end_date=report_date,
            )
            executor.submit(
                xero_client.get_bank_transactions,
                tenant_id,
                start_date=prev_start_date,
                end_date=prev_report_date,
            )
            executor.submit(
                xero_client.get_invoices,
                tenant_id,
                start_date=prev_start_date,
                end_date=prev_report_date,
                statuses=["AUTHORISED", "PAID"],
            )
            executor.submit(
                xero_client.get_manual_journals,
                tenant_id,
                start_date=prev_start_date,
                end_date=prev_report_date,
            )

        return jsonify({"status": "Success", "message": "Ledger cache primed."})
    except Exception as exc:
        logger.exception("prime_ledger failed")
        return jsonify({"status": "Error", "message": str(exc)}), 500


@workbench_bp.route("/api/workbench/analyze_nominal/<tenant_id>", methods=["GET"])
@login_required
def analyze_nominal(tenant_id):
    from openai import AzureOpenAI, OpenAI

    xero_client = _xero_client()
    if not xero_client:
        return jsonify({"status": "Error", "message": "No Xero token"}), 400

    nominal_name = request.args.get("nominal")
    account_id = request.args.get("account_id")
    if not nominal_name:
        return jsonify({"status": "Error", "message": "No nominal name provided"}), 400

    try:
        accounts = xero_client.get_accounts(tenant_id).get("Accounts", [])
        target_account = None

        if account_id and account_id not in ("undefined", "null"):
            for acc in accounts:
                if acc.get("AccountID") == account_id:
                    target_account = acc
                    break

        if not target_account:
            for acc in accounts:
                code = acc.get("Code", "")
                name = acc.get("Name", "")
                full_name = f"{code} - {name}"
                if full_name == nominal_name or name == nominal_name or code == nominal_name:
                    target_account = acc
                    break
            if not target_account and nominal_name:
                for acc in accounts:
                    code = acc.get("Code", "")
                    name = acc.get("Name", "")
                    if (code and code in nominal_name) and (name and name in nominal_name):
                        target_account = acc
                        break

        if not target_account:
            return (
                jsonify(
                    {
                        "status": "Error",
                        "message": f"Account '{nominal_name}' was not found in Xero.",
                    }
                ),
                404,
            )

        target_code = target_account.get("Code")

        try:
            current_date_str = request.args.get("current_year_end")
            report_date = (
                date.fromisoformat(current_date_str) if current_date_str else date.today()
            )
        except ValueError:
            report_date = date.today()

        start_date = report_date - relativedelta(years=1) + timedelta(days=1)
        prev_report_date = report_date - relativedelta(years=1)
        prev_start_date = prev_report_date - relativedelta(years=1) + timedelta(days=1)

        def fetch_filtered(s_date, e_date):
            txs = []
            try:
                bt_resp = xero_client.get_bank_transactions(
                    tenant_id, start_date=s_date, end_date=e_date, max_pages=50
                )
                inv_resp = xero_client.get_invoices(
                    tenant_id,
                    start_date=s_date,
                    end_date=e_date,
                    statuses=["AUTHORISED", "PAID"],
                    max_pages=50,
                )
                mj_resp = xero_client.get_manual_journals(
                    tenant_id, start_date=s_date, end_date=e_date, max_pages=50
                )

                for bt in bt_resp.get("BankTransactions", []):
                    for li in bt.get("LineItems", []):
                        if li.get("AccountCode") == target_code:
                            txs.append(
                                {
                                    "Date": bt.get("DateString", bt.get("Date", "")),
                                    "Source": "BankTransaction",
                                    "Description": li.get("Description", bt.get("Reference", "")),
                                    "Reference": bt.get("Reference", ""),
                                    "Contact": bt.get("Contact", {}).get("Name", ""),
                                    "Total": li.get("LineAmount", ""),
                                }
                            )

                for inv in inv_resp.get("Invoices", []):
                    for li in inv.get("LineItems", []):
                        if li.get("AccountCode") == target_code:
                            txs.append(
                                {
                                    "Date": inv.get("DateString", inv.get("Date", "")),
                                    "Source": "Invoice",
                                    "Description": li.get(
                                        "Description", inv.get("InvoiceNumber", "")
                                    ),
                                    "Reference": inv.get("Reference", ""),
                                    "Contact": inv.get("Contact", {}).get("Name", ""),
                                    "Total": li.get("LineAmount", ""),
                                }
                            )

                for mj in mj_resp.get("ManualJournals", []):
                    if (mj.get("Status") or "").upper() != "POSTED":
                        continue
                    for jl in mj.get("JournalLines", []):
                        if jl.get("AccountCode") == target_code:
                            txs.append(
                                {
                                    "Date": mj.get("DateString", mj.get("Date", "")),
                                    "Source": "ManualJournal",
                                    "Description": jl.get(
                                        "Description", mj.get("Narration", "")
                                    ),
                                    "Reference": mj.get("Narration", ""),
                                    "Contact": "",
                                    "Total": jl.get("LineAmount", ""),
                                }
                            )
            except Exception as exc:
                logger.warning("fetch_filtered for %s failed: %s", target_code, exc)
            return txs

        curr_txs = fetch_filtered(start_date, report_date)
        prev_txs = fetch_filtered(prev_start_date, prev_report_date)

        global_mat = request.args.get("global_materiality", "1000")
        nominal_mat = request.args.get("nominal_materiality", "500")
        deployment_name = resolve_scan_deployment_name()
        base_url = resolve_openai_base_url()
        if base_url:
            client = OpenAI(
                base_url=base_url.rstrip("/") + "/",
                api_key=resolve_azure_openai_api_key(),
            )
        else:
            client = AzureOpenAI(
                api_key=resolve_azure_openai_api_key(),
                api_version=resolve_azure_openai_api_version(),
                azure_endpoint=resolve_azure_openai_endpoint(),
            )

        context_str = (
            f"Current Year Transactions ({start_date} to {report_date}) - "
            f"Total Found: {len(curr_txs)}:\n"
        )
        context_str += "\n".join(str(t) for t in curr_txs[:50])
        context_str += (
            f"\n\nPrior Year Transactions ({prev_start_date} to {prev_report_date}) - "
            f"Total Found: {len(prev_txs)}:\n"
        )
        context_str += "\n".join(str(t) for t in prev_txs[:50])

        prompt = f"""
You are a UK chartered accountant. Review these transactions for the nominal account
'{nominal_name}'. The configured global materiality is £{global_mat} and the trivial
threshold is £{nominal_mat}.

Identify:
1. Recurring items: payments occurring regularly (monthly/quarterly/annually) in either year.
2. Outliers: large or unusual items. Items above £{nominal_mat} matter; items above
   £{global_mat} are material.
3. Year-on-year changes: notable new vendors and stopped vendors.

Reply with JSON:
{{
  "subscriptions": [
    {{"name": "...", "amount": "...", "frequency": "...", "status": "New / Existing / Stopped", "logic": "..."}}
  ],
  "outliers": [
    {{"name": "...", "amount": "...", "date": "...", "logic": "..."}}
  ],
  "summary": "Concise overview of the account's transactional activity."
}}
"""

        response = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a UK accountant assistant returning strict JSON.",
                },
                {"role": "user", "content": prompt + "\n\n" + context_str},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        result_data = json.loads(response.choices[0].message.content)
        return jsonify(
            {
                "status": "Success",
                "nominal": nominal_name,
                "data": result_data,
                "transactions": curr_txs,
                "model": deployment_name,
            }
        )
    except Exception as exc:
        logger.exception("analyze_nominal failed")
        return jsonify({"status": "Error", "message": str(exc)}), 500
