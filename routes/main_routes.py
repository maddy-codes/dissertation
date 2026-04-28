"""Dashboard and per-client landing pages, plus the analysis kick-off."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import date

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

from setup.models import ReviewNote, User, db
from strings.paths import FILE_PATH_OUT

logger = logging.getLogger(__name__)

main_bp = Blueprint("main", __name__)


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


def _run_analysis(
    app,
    tenant_id: str,
    user_id: int,
    selected_nominal_codes,
    run_id: str,
    current_year_end,
    comparison_year_end,
):
    """Background worker that streams progress events into uploads/<run_id>.jsonl."""
    log_file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{run_id}.jsonl")

    def emit(event_type: str, **kwargs) -> None:
        event = {"type": event_type, "timestamp": time.time(), **kwargs}
        with open(log_file_path, "a") as fh:
            fh.write(json.dumps(event) + "\n")

    emit("start", message="Review starting…")

    with app.app_context():
        try:
            user = User.query.get(user_id)
            xero_client = _xero_client_for(user)
            if not xero_client:
                emit("error", logic="No Xero token associated with user")
                return

            emit("progress", message="Fetching trial balance and building per-account context…")
            report_date = date.fromisoformat(current_year_end) if current_year_end else date.today()
            comparison_date = (
                date.fromisoformat(comparison_year_end) if comparison_year_end else None
            )

            from helpers.xero_api_parser import fetch_and_format_xero_data

            messages, mp_df = fetch_and_format_xero_data(
                xero_client, tenant_id, report_date, comparison_date=comparison_date
            )
            if selected_nominal_codes:
                messages = [m for m in messages if m["name"] in selected_nominal_codes]

            emit(
                "progress",
                message=f"Reviewing {len(messages)} accounts. Generating notes…",
            )

            from main_crew import run_all_crew

            run_all_crew(
                messages,
                mp_df,
                FILE_PATH_OUT=FILE_PATH_OUT,
                emit_event=emit,
            )

            try:
                connections = xero_client.list_connections()
                tenant_name = next(
                    (c["tenantName"] for c in connections if c["tenantId"] == tenant_id),
                    "Unknown Client",
                )
                note = ReviewNote(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    run_id=run_id,
                    year_start=str(comparison_date) if comparison_date else "N/A",
                    year_end=str(report_date),
                    status="COMPLETED",
                )
                db.session.add(note)
                db.session.commit()
            except Exception:
                logger.exception("Failed to save review history record")

            emit(
                "complete",
                message="Review notes successfully generated.",
                result_file=FILE_PATH_OUT,
            )
        except Exception as exc:
            logger.exception("Background review failed")
            emit("error", logic=str(exc))


@main_bp.route("/", methods=["GET", "POST"])
@login_required
def dashboard():
    """Dashboard listing connected client files and triggering reviews."""
    if request.method == "POST":
        tenant_id = request.form.get("tenant_id")
        current_year_end = request.form.get("current_year_end")
        comparison_year_end = request.form.get("comparison_year_end")
        selected_nominal_codes = request.form.getlist("selected_nominal_codes")

        if not tenant_id:
            flash("Please choose a client before starting a review.")
            return redirect(url_for("main.dashboard"))

        run_id = str(uuid.uuid4())
        existing_draft = ReviewNote.query.filter_by(
            user_id=current_user.id, tenant_id=tenant_id, status="DRAFT"
        ).first()
        if existing_draft:
            db.session.delete(existing_draft)
            db.session.commit()

        thread = threading.Thread(
            target=_run_analysis,
            args=(
                current_app._get_current_object(),
                tenant_id,
                current_user.id,
                selected_nominal_codes,
                run_id,
                current_year_end,
                comparison_year_end,
            ),
            daemon=True,
        )
        thread.start()
        return redirect(url_for("report.report_stream", run_id=run_id))

    has_xero_token = current_user.get_xero_token() is not None
    connections = []
    if has_xero_token:
        try:
            xero_client = _xero_client_for(current_user)
            if xero_client:
                connections = xero_client.list_connections()
        except Exception as exc:
            logger.warning("Could not load Xero connections: %s", exc)
            flash(f"Could not load Xero connections: {exc}")
            has_xero_token = False

    return render_template(
        "index.html", connections=connections, has_xero_token=has_xero_token
    )


@main_bp.route("/client/<tenant_id>")
@login_required
def client_detail(tenant_id):
    """Show the review history for one client file."""
    tenant_name = "Unknown Client"
    try:
        xero_client = _xero_client_for(current_user)
        if not xero_client:
            flash("Please reconnect your Xero account.")
            return redirect(url_for("main.dashboard"))
        for conn in xero_client.list_connections():
            if conn["tenantId"] == tenant_id:
                tenant_name = conn["tenantName"]
                break
    except Exception as exc:
        logger.warning("Failed to look up tenant name: %s", exc)

    history = (
        ReviewNote.query.filter_by(user_id=current_user.id, tenant_id=tenant_id)
        .order_by(ReviewNote.created_at.desc())
        .all()
    )

    return render_template(
        "client_detail.html",
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        history=history,
    )
