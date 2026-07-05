"""Report viewing, live event stream, and emailing the finished review."""
from __future__ import annotations

import json
import logging
import os
import time

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
)
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

report_bp = Blueprint("report", __name__)


def _run_pdf_path(run_id: str) -> str:
    return os.path.join(current_app.config["UPLOAD_FOLDER"], f"{run_id}.pdf")


def _run_pdf_bytes(run_id: str) -> bytes | None:
    """Load (or render on the fly) the PDF review notes for a run."""
    from helpers.pdf_report import load_or_render_pdf
    from setup.models import ReviewNote

    note = ReviewNote.query.filter_by(run_id=run_id).first()
    tenant_name = (note.tenant_name if note else None) or "Unknown Client"
    year_end = note.year_end if note else None
    year_start = note.year_start if note else None

    return load_or_render_pdf(
        current_app.config["UPLOAD_FOLDER"], run_id, tenant_name, year_end, year_start
    )


def _run_owner_path(run_id: str) -> str:
    return os.path.join(current_app.config["UPLOAD_FOLDER"], f"{run_id}.owner")


def _require_run_owner(run_id: str) -> None:
    """
    Abort with 404 unless the current user owns this run.

    Treating ownership failures as 404 (rather than 403) prevents leaking the
    fact that a given run_id exists for some other user.
    """
    owner_path = _run_owner_path(run_id)
    if not os.path.exists(owner_path):
        abort(404)
    try:
        with open(owner_path) as fh:
            owner_id = int(fh.read().strip())
    except (OSError, ValueError):
        abort(404)
    if owner_id != int(getattr(current_user, "id", -1)):
        abort(404)


@report_bp.route("/report/<run_id>")
@login_required
def report_stream(run_id: str):
    """Render the live review-notes page for a single run."""
    _require_run_owner(run_id)

    from setup.models import ReviewNote

    note = ReviewNote.query.filter_by(run_id=run_id).first()
    tenant_id = note.tenant_id if note else request.args.get("tenant_id")
    tenant_name = note.tenant_name if note else None

    # While the review is still running, there's no ReviewNote yet (it's only
    # written on completion) — resolve the client's display name from Xero so
    # the breadcrumb/back-arrow can still point at the client during the run.
    if tenant_id and not tenant_name:
        try:
            from integrations.xero_api import XeroClient

            token_data = current_user.get_xero_token()
            if token_data:
                xero_client = XeroClient(
                    client_id=os.environ.get("XERO_CLIENT_ID"),
                    client_secret=os.environ.get("XERO_CLIENT_SECRET"),
                    refresh_token=token_data.get("refresh_token"),
                    user=current_user,
                )
                for conn in xero_client.list_connections():
                    if conn["tenantId"] == tenant_id:
                        tenant_name = conn["tenantName"]
                        break
        except Exception:
            logger.warning("Could not resolve tenant name for in-progress run %s", run_id)

    return render_template(
        "report_stream.html", run_id=run_id, tenant_id=tenant_id, tenant_name=tenant_name
    )


@report_bp.route("/api/stream_report/<run_id>")
@login_required
def stream_report(run_id: str):
    """Server-sent events feed of progress for one review run.

    Sends a comment-line heartbeat every few seconds so proxies don't kill
    the connection during long quiet windows (LLM calls in flight).
    """
    _require_run_owner(run_id)
    log_file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"{run_id}.jsonl")
    poll_interval = 0.5
    heartbeat_every = 10.0  # seconds

    def generate():
        last_pos = 0
        last_heartbeat = time.time()
        # Tell the client we're connected immediately
        yield ": connected\n\n"
        while True:
            sent_anything = False
            if os.path.exists(log_file_path):
                with open(log_file_path) as fh:
                    fh.seek(last_pos)
                    lines = fh.readlines()
                    last_pos = fh.tell()
                    for line in lines:
                        if not line.strip():
                            continue
                        yield f"data: {line}\n\n"
                        sent_anything = True
                        try:
                            event = json.loads(line)
                            if event.get("type") in ("complete", "error"):
                                return
                        except Exception:
                            continue
            now = time.time()
            if not sent_anything and (now - last_heartbeat) >= heartbeat_every:
                # SSE comment lines are ignored by EventSource but keep proxies happy
                yield ": heartbeat\n\n"
                last_heartbeat = now
            elif sent_anything:
                last_heartbeat = now
            time.sleep(poll_interval)

    return Response(generate(), mimetype="text/event-stream")


@report_bp.route("/report/<run_id>/download")
@login_required
def download_report(run_id: str):
    """Download the review notes PDF for a single completed run."""
    _require_run_owner(run_id)
    pdf_bytes = _run_pdf_bytes(run_id)
    if pdf_bytes is None:
        abort(404)
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="review_notes_{run_id}.pdf"'
        },
    )


@report_bp.route("/api/send_report/<run_id>", methods=["POST"])
@login_required
def send_report(run_id: str):
    _require_run_owner(run_id)
    payload = request.get_json(silent=True) or {}
    email = payload.get("email")
    if not email:
        return jsonify({"status": "error", "message": "No email provided"}), 400

    try:
        from helpers.email_service import send_email

        pdf_bytes = _run_pdf_bytes(run_id)
        if pdf_bytes is None:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Review file is not ready yet — try again once the review completes.",
                    }
                ),
                404,
            )
        # _run_pdf_bytes normally caches the rendered PDF to disk; write it
        # ourselves too in case that cache write failed (send_email needs a path).
        file_path = _run_pdf_path(run_id)
        if not os.path.exists(file_path):
            with open(file_path, "wb") as fh:
                fh.write(pdf_bytes)

        firm_name = os.environ.get("FIRM_NAME", "Your Accounting Team")
        subject = f"Generated Review Notes | {firm_name}"
        body = (
            "Hello,\n\n"
            "Please find attached the review notes generated for your client file. "
            "These notes were prepared from live Xero data using our automated review tool.\n\n"
            f"Kind regards,\n{firm_name}"
        )
        recipient_list = [{"address": email, "displayName": "Client"}]
        sender_address = "donotreply@e444ea86-37e7-4a7d-857b-261cf490d7ce.azurecomm.net"

        send_email(
            subject=subject,
            file_path=file_path,
            body=body,
            recipient_list=recipient_list,
            sender_address=sender_address,
        )
        return jsonify({"status": "success", "message": "Email sent successfully."})
    except Exception as exc:
        logger.exception("send_report failed")
        return jsonify({"status": "error", "message": str(exc)}), 500


@report_bp.route("/revoke/<task_id>")
def revoke_task(task_id: str):
    """Legacy endpoint kept for client-side compatibility."""
    return jsonify({"task_id": task_id, "status": "Not supported in threading architecture"})
