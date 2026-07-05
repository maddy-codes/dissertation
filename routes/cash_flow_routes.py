"""Cash Flow Accelerator: revenue-opportunity detection + outreach action."""
from __future__ import annotations

import logging
import os
import threading
import time

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from helpers.cash_flow_insights import (
    build_cash_flow_report,
    get_last_autoscan_at,
    get_status,
    is_autoscan_enabled_for_tenant,
    load_cached,
    set_autoscan_enabled_for_tenant,
    set_status,
)
from helpers.xero_links import build_entity_link

logger = logging.getLogger(__name__)

cash_flow_bp = Blueprint("cash_flow", __name__)


def _xero_client_for(user):
    from integrations.xero_api import XeroClient

    token_data = user.get_xero_token()
    if not token_data:
        return None
    return XeroClient(
        client_id=os.environ.get("XERO_CLIENT_ID"),
        client_secret=os.environ.get("XERO_CLIENT_SECRET"),
        refresh_token=token_data.get("refresh_token"),
        user=user,
    )


def _xero_client():
    return _xero_client_for(current_user)


def _relative_time_display(epoch_seconds: float | None) -> str | None:
    if not epoch_seconds:
        return None
    minutes_ago = max(0, int((time.time() - epoch_seconds) / 60))
    if minutes_ago < 60:
        return f"{minutes_ago}m ago"
    if minutes_ago < 1440:
        return f"{minutes_ago // 60}h ago"
    return f"{minutes_ago // 1440}d ago"


def _resolve_tenant_name(xero_client, tenant_id: str) -> str:
    try:
        for conn in xero_client.list_connections():
            if conn["tenantId"] == tenant_id:
                return conn["tenantName"]
    except Exception as exc:
        logger.warning("Could not look up tenant name for %s: %s", tenant_id, exc)
    return "Unknown Client"


def _generate_in_background(app, user_id: int, tenant_id: str, tenant_name: str) -> None:
    """Runs the (potentially slow: Xero fetch + one LLM call per opportunity)
    report build off the request thread, so a big client never leaves the
    page hanging. Started fresh from the DB user, not the request-bound
    `current_user` proxy, since this outlives the request (see the identical
    pattern in routes/main_routes.py's `_run_analysis`)."""
    with app.app_context():
        try:
            from setup.models import User

            user = User.query.get(user_id)
            xero_client = _xero_client_for(user) if user else None
            if not xero_client:
                set_status(tenant_id, "error", "No Xero connection found.")
                return
            build_cash_flow_report(xero_client, tenant_id, tenant_name, force_refresh=True, user_id=user_id)
            set_status(tenant_id, "done")
        except Exception as exc:
            logger.exception("Background cash-flow generation failed for %s", tenant_id)
            set_status(tenant_id, "error", str(exc))


@cash_flow_bp.route("/cash-flow/<tenant_id>", methods=["GET"])
@login_required
def cash_flow_dashboard(tenant_id):
    xero_client = _xero_client()
    tenant_name = "Unknown Client"
    error = None

    if not xero_client:
        error = "Please reconnect your Xero account."
    else:
        tenant_name = _resolve_tenant_name(xero_client, tenant_id)

    # Never compute the report inline here — that's what made this page hang
    # for large clients. Just show whatever's cached; generation happens
    # asynchronously via /api/cash-flow/<tenant_id>/generate (see cash_flow.js).
    report = load_cached(tenant_id)
    status = get_status(tenant_id)
    generating = status.get("status") == "running"

    from setup.models import CashFlowOutcome, CashFlowOutreachLog

    if report and report.get("opportunities") and xero_client:
        try:
            short_code = xero_client.get_organisation_short_code(tenant_id)
        except Exception as exc:
            logger.warning("Could not resolve Xero short code for %s: %s", tenant_id, exc)
            short_code = None

        # Persist "already sent" state per opportunity so it survives a page
        # reload instead of only living in the JS button's ephemeral status
        # text (today's opportunity ids are stable across regenerations for
        # unresolved signals, so a prior log entry still applies).
        sent_log_by_opp = {
            row.opportunity_id: row
            for row in CashFlowOutreachLog.query.filter(
                CashFlowOutreachLog.tenant_id == tenant_id,
                CashFlowOutreachLog.opportunity_id.in_([o["id"] for o in report["opportunities"]]),
            ).all()
        }
        for opp in report["opportunities"]:
            opp["contact_xero_url"] = build_entity_link(short_code, "contact", opp.get("contact_id"))
            sent_row = sent_log_by_opp.get(opp["id"])
            opp["outreach_sent_at"] = sent_row.sent_at.isoformat() if sent_row else None

    outcomes = (
        CashFlowOutcome.query.filter_by(tenant_id=tenant_id)
        .order_by(CashFlowOutcome.resolved_at.desc())
        .limit(10)
        .all()
    )

    autoscan_enabled = is_autoscan_enabled_for_tenant(tenant_id)
    last_autoscan_display = (
        _relative_time_display(get_last_autoscan_at(tenant_id)) if autoscan_enabled else None
    )

    return render_template(
        "cash_flow.html",
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        report=report,
        error=error,
        generating=generating,
        generation_error=status.get("message") if status.get("status") == "error" else None,
        outcomes=outcomes,
        autoscan_enabled=autoscan_enabled,
        last_autoscan_display=last_autoscan_display,
    )


def _start_generation_thread(tenant_id: str) -> tuple[bool, str | None]:
    """Kicks off a background regeneration for the current user's Xero
    connection. Shared by the manual 'Generate New' button and by switching
    the autoscan toggle on (which fires an immediate first scan so enabling
    it is visibly real, not just a silent flag flip)."""
    if get_status(tenant_id).get("status") == "running":
        return True, None

    xero_client = _xero_client()
    if not xero_client:
        return False, "Please reconnect your Xero account."

    tenant_name = _resolve_tenant_name(xero_client, tenant_id)

    # Flip to "running" here (not inside the thread) so a status poll that
    # lands immediately after this response never sees a stale "idle".
    set_status(tenant_id, "running")
    thread = threading.Thread(
        target=_generate_in_background,
        args=(current_app._get_current_object(), current_user.id, tenant_id, tenant_name),
        daemon=True,
    )
    thread.start()
    return True, None


@cash_flow_bp.route("/api/cash-flow/<tenant_id>/generate", methods=["POST"])
@login_required
def generate_cash_flow(tenant_id):
    started, error = _start_generation_thread(tenant_id)
    if not started:
        return jsonify({"status": "error", "message": error}), 400
    return jsonify({"status": "started"})


@cash_flow_bp.route("/api/cash-flow/<tenant_id>/status")
@login_required
def cash_flow_status(tenant_id):
    return jsonify(get_status(tenant_id))


@cash_flow_bp.route("/api/cash-flow/<tenant_id>/autoscan", methods=["POST"])
@login_required
def toggle_autoscan(tenant_id):
    """Flip this client's autonomous-scan opt-in — the real, visible control
    for the feature (see helpers/cash_flow_scheduler.py); there is no server
    env var a user needs to find and set. Turning it on also fires an
    immediate scan so the effect is visible right away instead of only
    showing up whenever the background scheduler next ticks.
    """
    payload = request.get_json(silent=True) or {}
    enabled = bool(payload.get("enabled"))
    set_autoscan_enabled_for_tenant(tenant_id, enabled)

    started = False
    error = None
    if enabled:
        started, error = _start_generation_thread(tenant_id)

    return jsonify({"status": "Success", "enabled": enabled, "scan_started": started, "message": error})


@cash_flow_bp.route("/api/cash-flow/<tenant_id>/send/<opportunity_id>", methods=["POST"])
@login_required
def send_outreach(tenant_id, opportunity_id):
    cached = load_cached(tenant_id)
    if not cached:
        return jsonify({"status": "error", "message": "No opportunities loaded yet."}), 404

    opportunity = next((o for o in cached.get("opportunities", []) if o["id"] == opportunity_id), None)
    if not opportunity:
        return jsonify({"status": "error", "message": "Opportunity not found."}), 404

    test_inbox = os.environ.get("CASH_FLOW_TEST_INBOX", "").strip()
    if not test_inbox:
        return jsonify({"status": "error", "message": "CASH_FLOW_TEST_INBOX is not configured."}), 400

    try:
        from helpers.email_service import send_plain_email

        send_plain_email(
            subject=opportunity.get("email_subject") or f"Following up, {opportunity['contact_name']}",
            body=opportunity.get("email_body") or opportunity["detail"],
            recipient_list=[{"address": test_inbox, "displayName": opportunity["contact_name"]}],
        )

        from setup.models import CashFlowOutreachLog, db

        db.session.add(
            CashFlowOutreachLog(
                tenant_id=tenant_id,
                opportunity_id=opportunity_id,
                opportunity_type=opportunity.get("type", "unknown"),
                contact_name=opportunity.get("contact_name"),
                sent_to=test_inbox,
                sent_by_user_id=current_user.id,
            )
        )
        db.session.commit()

        return jsonify(
            {
                "status": "success",
                "message": (
                    f"Outreach sent to test inbox ({test_inbox}). "
                    f"Real customer address on file: {opportunity.get('contact_email') or 'none'}."
                ),
            }
        )
    except Exception as exc:
        logger.exception("Failed to send outreach for %s/%s", tenant_id, opportunity_id)
        return jsonify({"status": "error", "message": str(exc)}), 500
