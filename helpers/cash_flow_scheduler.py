"""Autonomous Cash Flow Accelerator scanning: detection + drafting only.

Periodically re-runs build_cash_flow_report for clients whose firm has
switched on the "Autonomous Scan" toggle on that client's Cash Flow
Accelerator page (routes/cash_flow_routes.py), so fresh opportunities are
waiting next time someone opens the dashboard instead of requiring a manual
"Generate" click every time. This module NEVER sends outreach or email —
sending stays a human-clicked action (send_outreach) by design; autonomy
here only covers the safe, reversible half of the workflow.

The scheduler infrastructure itself always runs (ticking frequently); what's
actually opt-in is each *client*, via the per-tenant flag below — there is
deliberately no server-side env var gate a user would need to find and set
to see this feature work.
"""
from __future__ import annotations

import glob
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

from helpers.cash_flow_insights import (
    CACHE_DIR,
    build_cash_flow_report,
    is_autoscan_enabled_for_tenant,
    load_cached,
    try_acquire_autoscan_lock,
)

logger = logging.getLogger(__name__)

_scheduler_started = False


_CACHE_SIDECAR_SUFFIXES = (".status.json", ".autoscan.json", ".autoscan_enabled.json")


def _autoscan_eligible_tenant_ids() -> list[str]:
    """Tenants with a report generated at least once AND the per-client
    autoscan toggle switched on."""
    if not os.path.isdir(CACHE_DIR):
        return []
    tenant_ids = []
    for path in glob.glob(os.path.join(CACHE_DIR, "*.json")):
        name = os.path.basename(path)
        if any(name.endswith(suffix) for suffix in _CACHE_SIDECAR_SUFFIXES):
            continue
        tenant_id = name[: -len(".json")]
        if is_autoscan_enabled_for_tenant(tenant_id):
            tenant_ids.append(tenant_id)
    return tenant_ids


def _run_autoscan(app, interval_hours: float) -> None:
    with app.app_context():
        from setup.models import User

        from integrations.xero_api import XeroClient

        for tenant_id in _autoscan_eligible_tenant_ids():
            if not try_acquire_autoscan_lock(tenant_id, interval_hours):
                continue

            try:
                cached = load_cached(tenant_id) or {}
                user_id = cached.get("last_user_id")
                if not user_id:
                    logger.info("Skipping autoscan for %s: no known user to run as.", tenant_id)
                    continue

                user = User.query.get(user_id)
                token_data = user.get_xero_token() if user else None
                if not token_data:
                    logger.info("Skipping autoscan for %s: user %s has no Xero token.", tenant_id, user_id)
                    continue

                xero_client = XeroClient(
                    client_id=os.environ.get("XERO_CLIENT_ID"),
                    client_secret=os.environ.get("XERO_CLIENT_SECRET"),
                    refresh_token=token_data.get("refresh_token"),
                    user=user,
                )
                try:
                    tenant_name = next(
                        (c["tenantName"] for c in xero_client.list_connections() if c["tenantId"] == tenant_id),
                        "Unknown Client",
                    )
                except Exception:
                    tenant_name = "Unknown Client"

                # Detection + drafting only — never send_outreach/email.
                build_cash_flow_report(
                    xero_client, tenant_id, tenant_name, force_refresh=True, user_id=user_id
                )
                logger.info("Autoscan refreshed cash-flow opportunities for tenant %s.", tenant_id)
            except Exception:
                logger.exception("Autoscan failed for tenant %s", tenant_id)


def start_cash_flow_autoscan(app) -> None:
    """Start the background autoscan job.

    This runs by default — what's actually opt-in is each *client*, via the
    "Autonomous Scan" toggle on that client's Cash Flow Accelerator page
    (which is what actually populates is_autoscan_enabled_for_tenant). Set
    CASH_FLOW_AUTOSCAN_ENABLED=false to disable the whole scheduler as an
    ops-level kill switch; otherwise this is always on but idles (near-zero
    cost) whenever no client has opted in.

    Ticks frequently (CASH_FLOW_AUTOSCAN_TICK_MINUTES, default 5) so
    switching a client's toggle on gets picked up soon; each individual
    client is still only actually refreshed at most every
    CASH_FLOW_AUTOSCAN_INTERVAL_HOURS (default 1), enforced by
    try_acquire_autoscan_lock.
    """
    global _scheduler_started
    if _scheduler_started:
        return

    kill_switch = os.environ.get("CASH_FLOW_AUTOSCAN_ENABLED", "").strip().lower()
    if kill_switch in ("0", "false", "no"):
        logger.info("Cash flow autoscan scheduler disabled via CASH_FLOW_AUTOSCAN_ENABLED=false.")
        return

    interval_hours = float(os.environ.get("CASH_FLOW_AUTOSCAN_INTERVAL_HOURS", "1"))
    tick_minutes = float(os.environ.get("CASH_FLOW_AUTOSCAN_TICK_MINUTES", "5"))

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        lambda: _run_autoscan(app, interval_hours),
        "interval",
        minutes=tick_minutes,
        id="cash_flow_autoscan",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    _scheduler_started = True
    logger.info(
        "Cash flow autoscan scheduler running (checks every %.0fm; each opted-in client refreshes "
        "at most every %.1fh; detection + drafting only, never sends).",
        tick_minutes,
        interval_hours,
    )
