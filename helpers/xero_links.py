"""Builds 'View in Xero' deep links.

URL formats are per developer.xero.com/documentation/best-practices/user-experience/deep-linking —
every link needs the organisation's ShortCode plus the record's real Xero ID.
"""
from __future__ import annotations

from urllib.parse import quote

_ENTITY_BUILDERS = {
    "invoice": lambda sc, rid: f"https://go.xero.com/app/{sc}/invoicing/view/{rid}",
    "bill": lambda sc, rid: (
        f"https://go.xero.com/organisationlogin/default.aspx?shortcode={sc}"
        f"&redirecturl=/AccountsPayable/Edit.aspx?InvoiceID={rid}"
    ),
    "contact": lambda sc, rid: f"https://go.xero.com/app/{sc}/contacts/contact/{rid}",
    "banktransaction": lambda sc, rid: (
        f"https://go.xero.com/organisationlogin/default.aspx?shortcode={sc}"
        f"&redirecturl=/Bank/ViewTransaction.aspx?bankTransactionID={rid}"
    ),
    "creditnote": lambda sc, rid: (
        f"https://go.xero.com/organisationlogin/default.aspx?shortcode={sc}"
        f"&redirecturl=/AccountsPayable/ViewCreditNote.aspx?creditNoteID={rid}"
    ),
    "purchaseorder": lambda sc, rid: (
        f"https://go.xero.com/organisationlogin/default.aspx?shortcode={sc}"
        f"&redirecturl=/Accounts/Payable/PurchaseOrders/View/{rid}"
    ),
}

ENTITY_TYPES = tuple(_ENTITY_BUILDERS.keys())

# Report IDs are region-specific; this firm operates in GB (see deep-linking docs).
_REPORT_IDS = {
    "trialbalance": "1005",
    "balancesheet": "1217",
    "profitandloss": "1216",
    "agedreceivablessummary": "1201",
    "agedpayablessummary": "1200",
}


def build_entity_link(short_code: str | None, entity_type: str | None, record_id: str | None) -> str | None:
    if not short_code or not entity_type or not record_id:
        return None
    builder = _ENTITY_BUILDERS.get(entity_type.strip().lower())
    if not builder:
        return None
    # Xero ShortCodes conventionally start with "!" (e.g. "!NLglS" — see the
    # examples in developer.xero.com's deep-linking guide). Encoding it away
    # to "%21" produces a shortcode Xero's router doesn't recognise, which
    # surfaces as a generic "Sorry, we can't show this page right now" error.
    return builder(quote(short_code, safe="!"), quote(record_id.strip(), safe=""))


def build_report_link(short_code: str | None, report_key: str | None) -> str | None:
    if not short_code or not report_key:
        return None
    report_id = _REPORT_IDS.get(report_key.strip().lower())
    if not report_id:
        return None
    return f"https://reporting.xero.com/{quote(short_code, safe='')}/v1/Run/{report_id}"
