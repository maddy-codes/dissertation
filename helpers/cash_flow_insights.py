"""
Cash Flow Accelerator: turns a tenant's Xero invoices into ranked revenue
opportunities (late payment, dormant/win-back, subscription-conversion
candidates), each with an AI-drafted insight + outreach email.

Results are cached to disk per tenant so the dashboard never depends on a
live Xero + LLM round trip: a failed refresh falls back to the last good
cache instead of showing an error.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join("instance", "cash_flow_cache")
HISTORY_LIMIT = int(os.environ.get("CASH_FLOW_HISTORY_LIMIT", "20"))

DORMANT_DAYS_THRESHOLD = int(os.environ.get("CASH_FLOW_DORMANT_DAYS", "90"))
REPEAT_MIN_INVOICES = int(os.environ.get("CASH_FLOW_REPEAT_MIN_INVOICES", "3"))
TOP_N_OPPORTUNITIES = int(os.environ.get("CASH_FLOW_TOP_N", "12"))

# Underperforming products/services: compare two equal rolling windows of
# tenant-wide revenue per product/service; flag a big enough drop.
UNDERPERFORMING_WINDOW_DAYS = int(os.environ.get("CASH_FLOW_UNDERPERFORMING_WINDOW_DAYS", "180"))
UNDERPERFORMING_DECLINE_THRESHOLD = float(os.environ.get("CASH_FLOW_UNDERPERFORMING_DECLINE_THRESHOLD", "0.4"))
UNDERPERFORMING_MIN_PRIOR_REVENUE = float(os.environ.get("CASH_FLOW_UNDERPERFORMING_MIN_PRIOR_REVENUE", "50"))

# Upsell/cross-sell: simple market-basket heuristic over the same windows.
CROSS_SELL_TOP_N_ITEMS = int(os.environ.get("CASH_FLOW_CROSS_SELL_TOP_N", "5"))

# Predictive late-payment risk: needs a minimum history to avoid flagging on
# a single data point, and a minimum average lateness to be worth a heads-up.
LATE_RISK_MIN_HISTORY = int(os.environ.get("CASH_FLOW_LATE_RISK_MIN_HISTORY", "2"))
LATE_RISK_DAYS_LATE_THRESHOLD = float(os.environ.get("CASH_FLOW_LATE_RISK_DAYS_THRESHOLD", "5"))

# Bookkeeping/migration placeholder contacts (not real customers) that show
# up in real-world Xero data, e.g. rolled-up balances imported from a legacy
# system. These would otherwise surface as huge, meaningless "opportunities".
_NON_CUSTOMER_NAME_MARKERS = (
    "all debtors",
    "all creditors",
    "opening balance",
    "suspense",
    "per iris",
    "per sage",
    "migration",
)


def _looks_like_real_customer(name: str) -> bool:
    lowered = (name or "").lower()
    return not any(marker in lowered for marker in _NON_CUSTOMER_NAME_MARKERS)


# ---------------------------------------------------------------------------
# Small parsing helpers (mirrors helpers/xero_api_parser.py conventions)
# ---------------------------------------------------------------------------

def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(raw: str):
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _field_date(payload: dict, base_key: str):
    raw = payload.get(f"{base_key}String") or payload.get(base_key) or ""
    return _parse_date(raw if isinstance(raw, str) else "")


def _item_key(line_item: dict) -> str | None:
    """Best available identifier for a line item's product/service.

    Prefers Xero's Items catalog (ItemCode) when the org uses it, falling
    back to the nominal account or free-text description. This repo's other
    code (helpers/xero_api_parser.py) has only ever consumed AccountCode and
    Description, but real Xero orgs using the Items feature will send
    ItemCode too — it's part of the same LineItems payload we already fetch.
    """
    for key in ("ItemCode", "AccountCode", "Description"):
        value = (line_item.get(key) or "").strip()
        if value:
            return value
    return None


def _invoice_days_late(inv: dict, due_date) -> float | None:
    """Days between an invoice's due date and when it was actually settled,
    using the latest date in the invoice's embedded Payments array.

    Xero's standard Invoice schema includes this Payments sub-array whenever
    a payment has been recorded against the invoice, but no code in this repo
    parses it today — orgs that reconcile purely via bank feed matching
    rather than recording discrete Payments may have none, hence the
    None fallback rather than assuming it's always present.
    """
    payments = inv.get("Payments") or []
    if not payments or not due_date:
        return None
    payment_dates = [d for d in (_field_date(p, "Date") for p in payments) if d]
    if not payment_dates:
        return None
    settled_date = max(payment_dates)
    return (settled_date - due_date).days


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------

def _cache_path(tenant_id: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{tenant_id}.json")


def load_cached(tenant_id: str):
    path = _cache_path(tenant_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to read cash flow cache for %s", tenant_id)
        return None


def _save_cache(tenant_id: str, data: dict) -> None:
    try:
        with open(_cache_path(tenant_id), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        logger.exception("Failed to write cash flow cache for %s", tenant_id)


# ---------------------------------------------------------------------------
# Generation status (file-based, not in-memory: gunicorn can run multiple
# worker processes, and the poll request checking status may land on a
# different worker than the one running the background generation thread).
# ---------------------------------------------------------------------------

def _status_path(tenant_id: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{tenant_id}.status.json")


def get_status(tenant_id: str) -> dict:
    path = _status_path(tenant_id)
    if not os.path.exists(path):
        return {"status": "idle"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"status": "idle"}


def set_status(tenant_id: str, status: str, message: str | None = None) -> None:
    try:
        with open(_status_path(tenant_id), "w", encoding="utf-8") as f:
            json.dump({"status": status, "message": message}, f)
    except Exception:
        logger.exception("Failed to write cash flow status for %s", tenant_id)


def _autoscan_lock_path(tenant_id: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{tenant_id}.autoscan.json")


def try_acquire_autoscan_lock(tenant_id: str, interval_hours: float) -> bool:
    """True if the autonomous scheduler (helpers/cash_flow_scheduler.py)
    should refresh this tenant right now, and immediately marks it claimed.

    False if it already ran within the interval — same file-based
    cross-process coordination as get_status/set_status above, needed
    because gunicorn can run multiple worker processes, each with its own
    independent scheduler thread. Not perfectly atomic across processes, but
    the worst case (two workers both refresh once in a rare race) is
    harmless, just wasteful — consistent with this module's existing
    tolerance for "good enough" file-based locking.
    """
    path = _autoscan_lock_path(tenant_id)
    now = time.time()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                last_run = json.load(f).get("last_run_at", 0)
            if now - last_run < interval_hours * 3600:
                return False
        except Exception:
            pass  # corrupt/unreadable lock file — treat as claimable
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"last_run_at": now}, f)
    except Exception:
        logger.exception("Could not write autoscan lock for %s", tenant_id)
    return True


def _autoscan_enabled_path(tenant_id: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{tenant_id}.autoscan_enabled.json")


def is_autoscan_enabled_for_tenant(tenant_id: str) -> bool:
    """Per-client opt-in for autonomous scanning — off by default (no
    surprise Xero/LLM spend), flipped on via a real toggle in the Cash Flow
    Accelerator UI (routes/cash_flow_routes.py), not a server env var."""
    path = _autoscan_enabled_path(tenant_id)
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("enabled"))
    except Exception:
        return False


def set_autoscan_enabled_for_tenant(tenant_id: str, enabled: bool) -> None:
    try:
        with open(_autoscan_enabled_path(tenant_id), "w", encoding="utf-8") as f:
            json.dump({"enabled": enabled}, f)
    except Exception:
        logger.exception("Could not persist autoscan toggle for %s", tenant_id)


def get_last_autoscan_at(tenant_id: str) -> float | None:
    """Epoch timestamp of the last autonomous rescan for this tenant, or
    None if autoscan has never run for it (e.g. disabled, or only manual
    'Generate' clicks so far) — used to show a 'Last auto-scan: X ago'
    indicator on the dashboard."""
    path = _autoscan_lock_path(tenant_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("last_run_at")
    except Exception:
        return None


def _build_history(previous: dict | None, generated_at: str, opportunities: list[dict]) -> list[dict]:
    """Prepend a record of this generation onto the tenant's run history.

    Each "Generate New" click gets its own entry (timestamp, how many
    opportunities, total £ impact) so the dashboard can show past runs
    instead of only ever exposing the single most recent snapshot.
    """
    history = list(previous.get("history", [])) if previous else []
    entry = {
        "generated_at": generated_at,
        "opportunity_count": len(opportunities),
        "total_impact": round(sum(o.get("impact_amount", 0.0) for o in opportunities), 2),
    }
    return ([entry] + history)[:HISTORY_LIMIT]


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------

def _aggregate_contacts(invoices: list[dict], today: date) -> dict:
    by_contact: dict[str, dict] = {}

    for inv in invoices:
        if inv.get("Type") != "ACCREC":
            continue
        contact = inv.get("Contact") or {}
        cid = contact.get("ContactID")
        if not cid or not _looks_like_real_customer(contact.get("Name")):
            continue

        rec = by_contact.setdefault(
            cid,
            {
                "contact_id": cid,
                "name": contact.get("Name") or "Unknown",
                "total_revenue": 0.0,
                "invoice_count": 0,
                "invoice_dates": [],
                "overdue_invoices": [],
                "open_invoices": [],
                "payment_lateness": [],
            },
        )

        status = inv.get("Status")
        total = _safe_float(inv.get("Total"))
        amount_due = _safe_float(inv.get("AmountDue"))
        inv_date = _field_date(inv, "Date")
        due_date = _field_date(inv, "DueDate")

        if status in ("AUTHORISED", "PAID"):
            rec["total_revenue"] += total
            rec["invoice_count"] += 1
            if inv_date:
                rec["invoice_dates"].append(inv_date.isoformat())

        if status == "AUTHORISED" and amount_due > 0.005 and due_date:
            if due_date < today:
                rec["overdue_invoices"].append(
                    {
                        "invoice_number": inv.get("InvoiceNumber"),
                        "amount_due": round(amount_due, 2),
                        "due_date": due_date.isoformat(),
                        "days_overdue": (today - due_date).days,
                    }
                )
            else:
                # Not yet due — candidate for predictive late-payment-risk
                # scoring (see _build_late_payment_risk_opportunities), never
                # the reactive overdue signal above.
                rec["open_invoices"].append(
                    {
                        "invoice_number": inv.get("InvoiceNumber"),
                        "amount_due": round(amount_due, 2),
                        "due_date": due_date.isoformat(),
                        "days_until_due": (due_date - today).days,
                    }
                )

        if status == "PAID" and due_date:
            days_late = _invoice_days_late(inv, due_date)
            if days_late is not None:
                rec["payment_lateness"].append(days_late)

    return by_contact


def _aggregate_item_windows(invoices: list[dict], today: date) -> dict:
    """Tenant-wide (not per-contact) revenue per product/service key, split
    into a 'recent' and an equal-length 'prior' rolling window, plus which
    contacts bought each item recently.

    Feeds the underperforming-products and cross-sell signal builders, which
    both need a whole-business view rather than one contact's own history —
    unlike _aggregate_contacts, which stays per-contact.
    """
    window = timedelta(days=UNDERPERFORMING_WINDOW_DAYS)
    recent_start = today - window
    prior_start = recent_start - window

    recent_revenue: dict[str, float] = {}
    prior_revenue: dict[str, float] = {}
    recent_buyers: dict[str, set] = {}
    active_contacts: dict[str, dict] = {}

    for inv in invoices:
        if inv.get("Type") != "ACCREC" or inv.get("Status") not in ("AUTHORISED", "PAID"):
            continue
        contact = inv.get("Contact") or {}
        cid = contact.get("ContactID")
        if not cid or not _looks_like_real_customer(contact.get("Name")):
            continue
        inv_date = _field_date(inv, "Date")
        if not inv_date:
            continue

        if recent_start <= inv_date <= today:
            bucket = recent_revenue
            active_contacts[cid] = {"contact_id": cid, "name": contact.get("Name") or "Unknown"}
        elif prior_start <= inv_date < recent_start:
            bucket = prior_revenue
        else:
            continue

        for line in inv.get("LineItems") or []:
            key = _item_key(line)
            if not key:
                continue
            amount = _safe_float(line.get("LineAmount"))
            bucket[key] = bucket.get(key, 0.0) + amount
            if bucket is recent_revenue:
                recent_buyers.setdefault(key, set()).add(cid)

    return {
        "recent_revenue": recent_revenue,
        "prior_revenue": prior_revenue,
        "recent_buyers": recent_buyers,
        "active_contacts": active_contacts,
    }


def _build_underperforming_opportunities(item_windows: dict) -> list[dict]:
    """Tenant-wide (not per-customer): a product/service line whose revenue
    has dropped sharply between the prior and recent windows.
    """
    opportunities: list[dict] = []
    recent = item_windows["recent_revenue"]
    prior = item_windows["prior_revenue"]

    for item_key, prior_amount in prior.items():
        if prior_amount < UNDERPERFORMING_MIN_PRIOR_REVENUE:
            continue
        recent_amount = recent.get(item_key, 0.0)
        decline = (prior_amount - recent_amount) / prior_amount
        if decline < UNDERPERFORMING_DECLINE_THRESHOLD:
            continue
        opportunities.append(
            {
                "id": f"underperf_{item_key}",
                "type": "underperforming_product",
                "contact_id": None,
                # Reused field: for this tenant-wide type, "contact_name"
                # holds the product/service name rather than a customer —
                # keeps the opportunity dict shape (and the UI) uniform
                # across all types instead of adding a parallel field.
                "contact_name": item_key,
                "impact_amount": round(prior_amount - recent_amount, 2),
                "detail": (
                    f"Revenue from '{item_key}' fell {decline * 100:.0f}% — "
                    f"£{prior_amount:,.2f} in the prior {UNDERPERFORMING_WINDOW_DAYS} days vs "
                    f"£{recent_amount:,.2f} in the most recent {UNDERPERFORMING_WINDOW_DAYS}."
                ),
            }
        )
    return opportunities


def _build_cross_sell_opportunities(item_windows: dict) -> list[dict]:
    """Simple market-basket heuristic: for each contact active in the recent
    window, flag their single highest-value missing item among the
    business's top revenue lines — one candidate per contact, not a flood.
    """
    recent_revenue = item_windows["recent_revenue"]
    recent_buyers = item_windows["recent_buyers"]
    active_contacts = item_windows["active_contacts"]

    top_items = sorted(recent_revenue.items(), key=lambda kv: kv[1], reverse=True)[:CROSS_SELL_TOP_N_ITEMS]
    if not top_items:
        return []

    opportunities: list[dict] = []
    for cid, contact in active_contacts.items():
        missing = [
            (item_key, revenue) for item_key, revenue in top_items
            if cid not in recent_buyers.get(item_key, set())
        ]
        if not missing:
            continue
        item_key, item_revenue = missing[0]
        buyer_count = len(recent_buyers.get(item_key, set())) or 1
        avg_spend = item_revenue / buyer_count
        opportunities.append(
            {
                "id": f"crosssell_{cid}_{item_key}",
                "type": "upsell_cross_sell",
                "contact_id": cid,
                "contact_name": contact["name"],
                "impact_amount": round(avg_spend, 2),
                "detail": (
                    f"Active customer who hasn't bought '{item_key}' — one of the business's top "
                    f"{CROSS_SELL_TOP_N_ITEMS} revenue lines, averaging £{avg_spend:,.2f} per "
                    "buyer recently."
                ),
            }
        )
    return opportunities


def _build_late_payment_risk_opportunities(by_contact: dict) -> list[dict]:
    """Predictive (not reactive): a contact with a track record of paying
    late has an invoice open that ISN'T overdue yet — worth a proactive
    nudge before it follows the same pattern. Never overlaps the reactive
    `late_payment` type, which only covers invoices already overdue.
    """
    opportunities: list[dict] = []
    for cid, rec in by_contact.items():
        lateness_history = rec.get("payment_lateness") or []
        if len(lateness_history) < LATE_RISK_MIN_HISTORY:
            continue
        avg_late = sum(lateness_history) / len(lateness_history)
        if avg_late < LATE_RISK_DAYS_LATE_THRESHOLD:
            continue
        open_invoices = rec.get("open_invoices") or []
        if not open_invoices:
            continue
        total_at_risk = sum(o["amount_due"] for o in open_invoices)
        opportunities.append(
            {
                "id": f"risk_{cid}",
                "type": "late_payment_risk",
                "contact_id": cid,
                "contact_name": rec["name"],
                "impact_amount": round(total_at_risk, 2),
                "detail": (
                    f"Has historically paid {avg_late:.0f} days late on average across "
                    f"{len(lateness_history)} settled invoices. {len(open_invoices)} invoice(s) "
                    f"currently open totalling £{total_at_risk:,.2f} — worth a heads-up before "
                    "they're overdue."
                ),
            }
        )
    return opportunities


def _build_late_payment_opportunities(by_contact: dict) -> list[dict]:
    """Reactive: any contact with an overdue AUTHORISED invoice."""
    opportunities = []
    for cid, rec in by_contact.items():
        if not rec["overdue_invoices"]:
            continue
        total_overdue = sum(o["amount_due"] for o in rec["overdue_invoices"])
        max_days = max(o["days_overdue"] for o in rec["overdue_invoices"])
        opportunities.append(
            {
                "id": f"late_{cid}",
                "type": "late_payment",
                "contact_id": cid,
                "contact_name": rec["name"],
                "impact_amount": round(total_overdue, 2),
                "detail": (
                    f"{len(rec['overdue_invoices'])} overdue invoice(s) totalling "
                    f"£{total_overdue:,.2f}, up to {max_days} days late."
                ),
            }
        )
    return opportunities


def _build_win_back_opportunities(by_contact: dict, today: date) -> list[dict]:
    """Dormant / win-back: meaningful past revenue, gone quiet."""
    opportunities = []
    revenues = sorted(r["total_revenue"] for r in by_contact.values() if r["total_revenue"] > 0)
    median_revenue = revenues[len(revenues) // 2] if revenues else 0.0

    for cid, rec in by_contact.items():
        if not rec["invoice_dates"] or rec["total_revenue"] <= 0:
            continue
        last_date = max(date.fromisoformat(d) for d in rec["invoice_dates"])
        days_quiet = (today - last_date).days
        if rec["total_revenue"] >= median_revenue and days_quiet >= DORMANT_DAYS_THRESHOLD:
            opportunities.append(
                {
                    "id": f"dormant_{cid}",
                    "type": "win_back",
                    "contact_id": cid,
                    "contact_name": rec["name"],
                    "impact_amount": round(rec["total_revenue"], 2),
                    "detail": (
                        f"£{rec['total_revenue']:,.2f} in lifetime revenue across "
                        f"{rec['invoice_count']} invoices, but nothing in {days_quiet} days "
                        f"(last invoice {last_date.isoformat()})."
                    ),
                }
            )
    return opportunities


def _build_subscription_candidate_opportunities(by_contact: dict, today: date) -> list[dict]:
    """Repeat purchase: active, regular cadence -> subscription candidate."""
    opportunities = []
    for cid, rec in by_contact.items():
        if rec["invoice_count"] < REPEAT_MIN_INVOICES or not rec["invoice_dates"]:
            continue
        dates = sorted(date.fromisoformat(d) for d in rec["invoice_dates"])
        days_quiet = (today - dates[-1]).days
        if days_quiet >= DORMANT_DAYS_THRESHOLD:
            continue  # already covered by win-back, or genuinely inactive
        span_days = (dates[-1] - dates[0]).days or 1
        avg_gap = span_days / max(1, rec["invoice_count"] - 1)
        opportunities.append(
            {
                "id": f"repeat_{cid}",
                "type": "subscription_candidate",
                "contact_id": cid,
                "contact_name": rec["name"],
                "impact_amount": round(rec["total_revenue"], 2),
                "detail": (
                    f"{rec['invoice_count']} invoices averaging one every {avg_gap:.0f} days — "
                    "a strong candidate for a recurring/subscription plan."
                ),
            }
        )
    return opportunities


def _build_opportunities(by_contact: dict, today: date, item_windows: dict | None = None) -> list[dict]:
    """Builds each signal type independently, then merges round-robin (one
    from each type in turn) instead of one global £-impact sort.

    A global sort would let a handful of big-revenue win-back/late-payment
    contacts silently crowd every other signal type out of the fixed
    TOP_N_OPPORTUNITIES cap — their impact figures are a contact's whole
    lifetime revenue, structurally much larger than e.g. cross-sell's
    per-buyer average or underperforming's revenue-decline delta. Round-robin
    guarantees every type that has *any* qualifying opportunity gets a slot
    before any type gets a second one.
    """
    by_type: dict[str, list[dict]] = {
        "late_payment": _build_late_payment_opportunities(by_contact),
        "win_back": _build_win_back_opportunities(by_contact, today),
        "subscription_candidate": _build_subscription_candidate_opportunities(by_contact, today),
        "late_payment_risk": _build_late_payment_risk_opportunities(by_contact),
    }
    if item_windows:
        by_type["underperforming_product"] = _build_underperforming_opportunities(item_windows)
        by_type["upsell_cross_sell"] = _build_cross_sell_opportunities(item_windows)

    type_lists = list(by_type.values())
    for opps in type_lists:
        opps.sort(key=lambda o: o["impact_amount"], reverse=True)

    merged: list[dict] = []
    round_index = 0
    while len(merged) < TOP_N_OPPORTUNITIES and any(round_index < len(lst) for lst in type_lists):
        for lst in type_lists:
            if round_index < len(lst):
                merged.append(lst[round_index])
                if len(merged) >= TOP_N_OPPORTUNITIES:
                    break
        round_index += 1

    return merged


# ---------------------------------------------------------------------------
# LLM drafting (direct client call, mirroring agents/crew_manager.py's
# single-shot pattern — more reliable in this codebase than the crew chain)
# ---------------------------------------------------------------------------

_TYPE_GUIDANCE = {
    "late_payment": "This customer has overdue invoices. Draft a firm-but-polite payment chase email.",
    "win_back": (
        "This customer used to buy regularly but has gone quiet. Draft a friendly "
        "win-back/re-engagement email."
    ),
    "subscription_candidate": (
        "This customer buys repeatedly at a regular cadence. Draft an email proposing a "
        "subscription or retainer arrangement that would save them admin and lock in the relationship."
    ),
    "late_payment_risk": (
        "This customer has a history of paying late and has an invoice open that isn't overdue "
        "yet. Draft a friendly, proactive payment reminder — not a chase, since nothing is late yet."
    ),
    "upsell_cross_sell": (
        "This is an active customer who hasn't bought one of the business's popular services. "
        "Draft a short, low-pressure email introducing that service and why it might suit them."
    ),
    "underperforming_product": (
        "This is an internal signal about one product/service line's revenue declining across "
        "the whole customer base — not a single customer to email. Write the insight as a note "
        "to the business owner suggesting they investigate why."
    ),
}

# Types where a customer outreach email makes sense; underperforming_product
# is a whole-business signal with no single customer to email, so its
# email fields are always blanked regardless of what the model returns.
_CUSTOMER_FACING_TYPES = {
    "late_payment", "win_back", "subscription_candidate", "late_payment_risk", "upsell_cross_sell",
}


def _llm_client_and_deployment():
    from openai import AzureOpenAI, OpenAI

    from helpers.openai_config import (
        resolve_azure_openai_api_key,
        resolve_azure_openai_api_version,
        resolve_azure_openai_endpoint,
        resolve_openai_base_url,
        resolve_scan_deployment_name,
    )

    deployment = resolve_scan_deployment_name()
    base_url = resolve_openai_base_url()
    if base_url:
        client = OpenAI(
            base_url=base_url.rstrip("/") + "/",
            api_key=resolve_azure_openai_api_key(),
            timeout=30,
            max_retries=2,
        )
    else:
        client = AzureOpenAI(
            azure_endpoint=resolve_azure_openai_endpoint(),
            api_key=resolve_azure_openai_api_key(),
            api_version=resolve_azure_openai_api_version(),
            timeout=30,
            max_retries=2,
        )
    return client, deployment


def _fallback_draft(opportunity: dict, business_name: str) -> dict:
    if opportunity["type"] not in _CUSTOMER_FACING_TYPES:
        return {"insight": opportunity["detail"], "email_subject": "", "email_body": ""}
    return {
        "insight": opportunity["detail"],
        "email_subject": f"Following up, {opportunity['contact_name']}",
        "email_body": (
            f"Hi {opportunity['contact_name']},\n\n"
            f"{opportunity['detail']}\n\n"
            f"Kind regards,\n{business_name}"
        ),
    }


def draft_opportunity_message(opportunity: dict, business_name: str) -> dict:
    """Ask the LLM for a one-line insight + (for customer-facing types) a
    draft outreach email. Falls back to a deterministic templated message if
    the LLM call fails, so a flaky model call never breaks the dashboard."""
    is_customer_facing = opportunity["type"] in _CUSTOMER_FACING_TYPES
    try:
        client, deployment = _llm_client_and_deployment()
        guidance = _TYPE_GUIDANCE.get(opportunity["type"], "Draft a relevant outreach email for this opportunity.")

        system_prompt = (
            "You are a revenue operations assistant for a small business that uses Xero. "
            "You turn one data signal into (1) a one-sentence plain-English insight for the "
            "business owner and (2), when appropriate, a short draft outreach email to the "
            "customer. Only use the facts given; never invent numbers or specifics not present "
            "in the signal."
        )
        user_prompt = f"""\
Business: {business_name}
Subject: {opportunity['contact_name']}
Opportunity type: {opportunity['type']}
Signal: {opportunity['detail']}

{guidance}

Respond as JSON with exactly these keys:
"insight": one sentence, plain English, for the business owner.
"email_subject": a short email subject line, or "" if this isn't a customer-facing signal.
"email_body": a short email body (3-5 sentences) signed off generically as "{business_name}", or "" if this isn't a customer-facing signal.
"""

        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        draft = {
            "insight": (parsed.get("insight") or "").strip(),
            # Blanked in code regardless of model output for non-customer-facing
            # types — never trust the model alone to withhold an email it
            # wasn't supposed to draft.
            "email_subject": (parsed.get("email_subject") or "").strip() if is_customer_facing else "",
            "email_body": (parsed.get("email_body") or "").strip() if is_customer_facing else "",
        }
        if not draft["insight"] or (is_customer_facing and not draft["email_body"]):
            return _fallback_draft(opportunity, business_name)
        return draft
    except Exception:
        logger.exception("LLM drafting failed for opportunity %s", opportunity.get("id"))
        return _fallback_draft(opportunity, business_name)


# ---------------------------------------------------------------------------
# Outcome tracking
# ---------------------------------------------------------------------------

def _record_outcomes(tenant_id: str, previous_opportunities: list[dict], new_opportunities: list[dict]) -> None:
    """Diff the last scan's opportunities against this one; anything that
    disappeared has been resolved (invoice paid, contact re-engaged, etc.) —
    log it as a CashFlowOutcome, the 'measurable business outcome' evidence
    surfaced on the dashboard. Runs on every regeneration, manual or
    autonomous (see helpers/cash_flow_scheduler.py).
    """
    if not previous_opportunities:
        return
    new_ids = {o["id"] for o in new_opportunities}
    resolved = [o for o in previous_opportunities if o["id"] not in new_ids]
    if not resolved:
        return

    try:
        from setup.models import CashFlowOutcome, CashFlowOutreachLog, db
    except Exception:
        logger.exception("Could not import models to record cash-flow outcomes")
        return

    try:
        for opp in resolved:
            outreach_sent = (
                CashFlowOutreachLog.query.filter_by(tenant_id=tenant_id, opportunity_id=opp["id"]).first()
                is not None
            )
            db.session.add(
                CashFlowOutcome(
                    tenant_id=tenant_id,
                    opportunity_id=opp["id"],
                    opportunity_type=opp.get("type", "unknown"),
                    contact_name=opp.get("contact_name"),
                    impact_amount=opp.get("impact_amount", 0.0),
                    outreach_sent=outreach_sent,
                )
            )
        db.session.commit()
    except Exception:
        logger.exception("Could not record cash-flow outcomes for tenant %s", tenant_id)
        db.session.rollback()


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------

def build_cash_flow_report(
    xero_client,
    tenant_id: str,
    business_name: str,
    force_refresh: bool = False,
    user_id: int | None = None,
) -> dict:
    """Load the saved recommendations for a tenant, only regenerating them
    against live Xero + the LLM when explicitly asked to (`force_refresh`,
    wired to the dashboard's "Generate New" button and to the autonomous
    scheduler) or when nothing has ever been generated for this tenant
    before. There is no time-based expiry — the same recommendations persist
    across visits until something asks for new ones, and every generation is
    recorded in `history`.

    `user_id`, when given, is the staff user whose Xero connection produced
    this report; it's persisted into the cache as `last_user_id` so a later
    autonomous rescan (which has no request/current_user) knows whose token
    to reuse for this tenant (see helpers/cash_flow_scheduler.py).
    """
    cached = load_cached(tenant_id)

    if cached and not force_refresh:
        return cached

    try:
        today = date.today()
        invoices = xero_client.get_invoices(tenant_id, statuses=["AUTHORISED", "PAID"]).get("Invoices", [])
        contacts_by_id = xero_client.get_contacts(tenant_id)

        by_contact = _aggregate_contacts(invoices, today)
        item_windows = _aggregate_item_windows(invoices, today)
        opportunities = _build_opportunities(by_contact, today, item_windows)

        for opp in opportunities:
            opp.update(draft_opportunity_message(opp, business_name))
            contact = contacts_by_id.get(opp["contact_id"], {}) if opp.get("contact_id") else {}
            opp["contact_email"] = contact.get("EmailAddress") or ""

        _record_outcomes(tenant_id, (cached or {}).get("opportunities", []), opportunities)

        generated_at = datetime.now(timezone.utc).isoformat()
        result = {
            "tenant_id": tenant_id,
            "generated_at": generated_at,
            "_cached_at": time.time(),
            "opportunities": opportunities,
            "stale": False,
            "history": _build_history(cached, generated_at, opportunities),
            "last_user_id": user_id if user_id is not None else (cached or {}).get("last_user_id"),
        }
        _save_cache(tenant_id, result)
        return result
    except Exception:
        logger.exception("Live cash-flow analysis failed for tenant %s", tenant_id)
        if cached:
            cached["stale"] = True
            return cached
        raise
