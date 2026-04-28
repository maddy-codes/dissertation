"""Report viewing, live event stream, and emailing the finished review."""
from __future__ import annotations

import json
import logging
import os
import time

from flask import Blueprint, Response, current_app, jsonify, render_template, request
from flask_login import login_required

from strings.paths import FILE_PATH_OUT

logger = logging.getLogger(__name__)

report_bp = Blueprint("report", __name__)


@report_bp.route("/report/<run_id>")
def report_stream(run_id: str):
    """Render the live review-notes page for a single run."""
    return render_template("report_stream.html", run_id=run_id)


@report_bp.route("/api/stream_report/<run_id>")
def stream_report(run_id: str):
    """Server-sent events feed of progress for one review run."""
    log_file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"{run_id}.jsonl")

    def generate():
        last_pos = 0
        # Tail the file until we see a terminal event
        while True:
            if os.path.exists(log_file_path):
                with open(log_file_path) as fh:
                    fh.seek(last_pos)
                    lines = fh.readlines()
                    last_pos = fh.tell()
                    for line in lines:
                        if not line.strip():
                            continue
                        yield f"data: {line}\n\n"
                        try:
                            event = json.loads(line)
                            if event.get("type") in ("complete", "error"):
                                return
                        except Exception:
                            continue
            time.sleep(0.5)

    return Response(generate(), mimetype="text/event-stream")


@report_bp.route("/api/send_report/<run_id>", methods=["POST"])
@login_required
def send_report(run_id: str):
    payload = request.get_json(silent=True) or {}
    email = payload.get("email")
    if not email:
        return jsonify({"status": "error", "message": "No email provided"}), 400

    try:
        from helpers.email_service import send_email

        subject = "Generated Review Notes | PHM Accountants"
        body = (
            "Hello,\n\n"
            "Please find attached the review notes generated for your client file. "
            "These notes were prepared from live Xero data using our automated review tool.\n\n"
            "Kind regards,\nPHM Accountants"
        )
        recipient_list = [{"address": email, "displayName": "Client"}]
        sender_address = "donotreply@e444ea86-37e7-4a7d-857b-261cf490d7ce.azurecomm.net"

        send_email(
            subject=subject,
            file_path=FILE_PATH_OUT,
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
