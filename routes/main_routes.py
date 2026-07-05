"""Dashboard and per-client landing pages, plus the analysis kick-off."""
from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
import uuid
import zipfile
from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from werkzeug.security import generate_password_hash

from helpers.access import user_can_view_tenant
from helpers.client_overview import summarize_review_sentiment
from setup.models import ClientAccess, Plan, PlanStep, ReviewNote, User, db

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
    run_output_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{run_id}.csv")
    run_pdf_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{run_id}.pdf")
    owner_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{run_id}.owner")

    # Bind this run to the kicking-off user so the SSE / report / email
    # endpoints can verify ownership and prevent cross-user data leaks.
    try:
        with open(owner_path, "w") as fh:
            fh.write(str(user_id))
    except OSError:
        logger.exception("Could not write run owner sidecar at %s", owner_path)

    emit_lock = threading.Lock()

    def emit(event_type: str, **kwargs) -> None:
        event = {"type": event_type, "timestamp": time.time(), **kwargs}
        line = json.dumps(event) + "\n"
        # Lock so concurrent worker threads don't interleave bytes mid-line
        with emit_lock:
            with open(log_file_path, "a") as fh:
                fh.write(line)

    emit("start", message="Starting review…")

    with app.app_context():
        try:
            user = User.query.get(user_id)
            xero_client = _xero_client_for(user)
            if not xero_client:
                emit("error", logic="No Xero token associated with user")
                return

            report_date = date.fromisoformat(current_year_end) if current_year_end else date.today()
            comparison_date = (
                date.fromisoformat(comparison_year_end) if comparison_year_end else None
            )

            # Per-stage progress events so the live page never sits silent.
            emit("progress", message="Fetching trial balance from Xero…")
            emit(
                "progress",
                message="Fetching profit & loss and prior-year comparatives…",
            )
            emit(
                "progress",
                message="Pulling current and prior-year transactions (bank, invoices, manual journals)…",
            )

            from helpers.xero_api_parser import fetch_and_format_xero_data

            messages, mp_df = fetch_and_format_xero_data(
                xero_client, tenant_id, report_date, comparison_date=comparison_date
            )

            emit(
                "progress",
                message=f"{len(messages)} accounts with activity identified.",
            )

            if selected_nominal_codes:
                # Match by either the account label OR the resolved code so
                # the workbench's "selection by name" form still works.
                selected = set(selected_nominal_codes)
                filtered = []
                for m, code in zip(messages, mp_df["xero_codes"]):
                    if m["name"] in selected or (code and str(code) in selected):
                        filtered.append(m)
                messages = filtered
                emit(
                    "progress",
                    message=f"Filtered to {len(messages)} accounts you selected.",
                )

            from main_crew import run_all_crew

            run_all_crew(
                messages,
                mp_df,
                FILE_PATH_OUT=run_output_path,
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
                tenant_name = "Unknown Client"

            try:
                from helpers.pdf_report import build_review_pdf_from_csv

                pdf_bytes = build_review_pdf_from_csv(
                    run_output_path,
                    tenant_name=tenant_name,
                    year_end=str(report_date),
                    year_start=str(comparison_date) if comparison_date else None,
                    run_id=run_id,
                )
                with open(run_pdf_path, "wb") as fh:
                    fh.write(pdf_bytes)
            except Exception:
                logger.exception("Failed to render review PDF for run %s", run_id)

            emit(
                "complete",
                message="Review notes generated.",
                result_file=run_output_path,
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
        # tenant_id is passed through as a query param so the report page's
        # breadcrumb/back-arrow can link back to the client before the
        # ReviewNote row exists (it's only written once the review completes).
        return redirect(url_for("report.report_stream", run_id=run_id, tenant_id=tenant_id))

    is_client_view = current_user.role == 'client'
    has_xero_token = current_user.get_xero_token() is not None
    connections = []
    if is_client_view:
        grants = ClientAccess.query.filter_by(user_id=current_user.id).all()
        connections = [
            {"tenantId": g.tenant_id, "tenantName": g.tenant_name or "Unnamed Client"}
            for g in grants
        ]
    elif has_xero_token:
        try:
            xero_client = _xero_client_for(current_user)
            if xero_client:
                connections = xero_client.list_connections()
        except Exception as exc:
            logger.warning("Could not load Xero connections: %s", exc)
            flash(f"Could not load Xero connections: {exc}")
            has_xero_token = False

    search = (request.args.get("q") or "").strip()
    if search:
        connections = [c for c in connections if search.lower() in (c.get("tenantName") or "").lower()]
    connections.sort(key=lambda c: (c.get("tenantName") or "").lower())

    page_size = 24
    total = len(connections)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(request.args.get("page", 1, type=int) or 1, total_pages))
    start = (page - 1) * page_size
    page_connections = connections[start : start + page_size]

    return render_template(
        "index.html",
        connections=page_connections,
        has_xero_token=has_xero_token,
        is_client_view=is_client_view,
        search=search,
        page=page,
        total_pages=total_pages,
        total_clients=total,
    )


@main_bp.route("/client/<tenant_id>")
@login_required
def client_detail(tenant_id):
    """Show the review history, plan and timeline for one client file."""
    if not user_can_view_tenant(current_user, tenant_id):
        abort(403)

    can_manage = current_user.role != 'client'
    tenant_name = "Unknown Client"
    xero_url = None
    history = []
    contacts = []
    access_grants = []

    if can_manage:
        xero_client = _xero_client_for(current_user)
        if not xero_client:
            flash("Please reconnect your Xero account.")
            return redirect(url_for("main.dashboard"))

        try:
            for conn in xero_client.list_connections():
                if conn["tenantId"] == tenant_id:
                    tenant_name = conn["tenantName"]
                    break

            org = xero_client.get_organisation(tenant_id)
            orgs = org.get("Organisations") or []
            short_code = orgs[0].get("ShortCode") if orgs else None
            if short_code:
                xero_url = f"https://go.xero.com/app/{short_code}/dashboard"
        except Exception as exc:
            logger.warning("Failed to look up tenant details: %s", exc)

        try:
            raw_contacts = xero_client.get_contacts(tenant_id).values()
            contacts = sorted(
                (
                    {"name": c.get("Name", ""), "email": c.get("EmailAddress", "")}
                    for c in raw_contacts
                    if c.get("EmailAddress")
                ),
                key=lambda c: c["name"].lower(),
            )
        except Exception as exc:
            logger.warning("Failed to load Xero contacts for %s: %s", tenant_id, exc)
            flash(
                "Could not load Xero contacts for the picker below — reconnect your Xero "
                "account if this keeps happening (contacts.read permission may be missing)."
            )

        history = (
            ReviewNote.query.filter_by(user_id=current_user.id, tenant_id=tenant_id)
            .order_by(ReviewNote.created_at.desc())
            .all()
        )
        access_grants = ClientAccess.query.filter_by(tenant_id=tenant_id).all()
    else:
        grant = ClientAccess.query.filter_by(user_id=current_user.id, tenant_id=tenant_id).first()
        tenant_name = (grant.tenant_name if grant else None) or "Unnamed Client"

    plans = (
        Plan.query.filter_by(tenant_id=tenant_id)
        .order_by(Plan.created_at.desc())
        .all()
    )
    timeline = (
        PlanStep.query.join(Plan)
        .filter(Plan.tenant_id == tenant_id, PlanStep.status == 'done')
        .order_by(PlanStep.completed_at.desc())
        .all()
    )

    return render_template(
        "client_detail.html",
        tenant_id=tenant_id,
        can_manage=can_manage,
        plans=plans,
        timeline=timeline,
        contacts=contacts,
        access_grants=access_grants,
        tenant_name=tenant_name,
        xero_url=xero_url,
        history=history,
    )


@main_bp.route("/client/<tenant_id>/access", methods=["POST"])
@login_required
def grant_client_access(tenant_id):
    """Give a business-owner login access to this tenant's Plan/Timeline."""
    if current_user.role == 'client':
        abort(403)

    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    tenant_display_name = (request.form.get("tenant_display_name") or "").strip()

    if not email or not password:
        flash("Email and password are required to grant access.")
        return redirect(url_for("main.client_detail", tenant_id=tenant_id))

    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, role='client')
        db.session.add(user)
    elif user.role not in ('client',):
        flash(f"{email} already has a staff/partner login and can't also be a client login.")
        return redirect(url_for("main.client_detail", tenant_id=tenant_id))

    user.password_hash = generate_password_hash(password)
    db.session.flush()

    grant = ClientAccess.query.filter_by(user_id=user.id, tenant_id=tenant_id).first()
    if not grant:
        grant = ClientAccess(
            user_id=user.id,
            tenant_id=tenant_id,
            granted_by_user_id=current_user.id,
        )
        db.session.add(grant)
    grant.tenant_name = tenant_display_name or grant.tenant_name

    db.session.commit()
    flash(f"Granted {email} access to this client.")
    return redirect(url_for("main.client_detail", tenant_id=tenant_id))


@main_bp.route("/client/<tenant_id>/access/<int:access_id>/revoke", methods=["POST"])
@login_required
def revoke_client_access(tenant_id, access_id):
    if current_user.role == 'client':
        abort(403)

    grant = ClientAccess.query.filter_by(id=access_id, tenant_id=tenant_id).first()
    if not grant:
        abort(404)

    db.session.delete(grant)
    db.session.commit()
    flash("Access revoked.")
    return redirect(url_for("main.client_detail", tenant_id=tenant_id))


@main_bp.route("/client/<tenant_id>/review/<run_id>/delete", methods=["POST"])
@login_required
def delete_review(tenant_id, run_id):
    """Permanently delete a review run and its on-disk artifacts."""
    note = ReviewNote.query.filter_by(
        run_id=run_id, tenant_id=tenant_id, user_id=current_user.id
    ).first()
    if not note:
        abort(404)

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    for suffix in (".csv", ".jsonl", ".owner", "_draft.json"):
        path = os.path.join(upload_folder, f"{run_id}{suffix}")
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError as exc:
                logger.warning("Failed to remove run artifact %s: %s", path, exc)

    db.session.delete(note)
    db.session.commit()
    flash("Review deleted.")
    return redirect(url_for("main.client_detail", tenant_id=tenant_id))


@main_bp.route("/client/<tenant_id>/reports/download")
@login_required
def download_all_reports(tenant_id):
    """Zip up every completed review's PDF for this client and download it."""
    notes = (
        ReviewNote.query.filter_by(
            user_id=current_user.id, tenant_id=tenant_id, status="COMPLETED"
        )
        .order_by(ReviewNote.created_at.asc())
        .all()
    )

    from helpers.pdf_report import load_or_render_pdf

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    buffer = io.BytesIO()
    added_any = False
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for note in notes:
            pdf_bytes = load_or_render_pdf(
                upload_folder, note.run_id, note.tenant_name or tenant_id, note.year_end, note.year_start,
            )
            if pdf_bytes is None:
                continue
            date_label = note.created_at.strftime("%Y-%m-%d")
            year_label = note.year_end or note.run_id
            arcname = f"{date_label}_{year_label}_{note.run_id}.pdf"
            zf.writestr(arcname, pdf_bytes)
            added_any = True

    if not added_any:
        flash("No completed reviews to download yet.")
        return redirect(url_for("main.client_detail", tenant_id=tenant_id))

    buffer.seek(0)
    tenant_name = notes[0].tenant_name or tenant_id
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in tenant_name)
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{safe_name}_reviews.zip",
    )


@main_bp.route("/api/client/<tenant_id>/year_ends")
@login_required
def client_year_ends(tenant_id):
    """Recent fiscal year-end dates from Xero, for the New Review dropdown."""
    xero_client = _xero_client_for(current_user)
    if not xero_client:
        return jsonify({"year_ends": []})

    try:
        org = xero_client.get_organisation(tenant_id)
        orgs = org.get("Organisations") or []
        day = orgs[0].get("FinancialYearEndDay") if orgs else None
        month = orgs[0].get("FinancialYearEndMonth") if orgs else None
        if not day or not month:
            return jsonify({"year_ends": []})

        from integrations.xero_api import recent_fiscal_year_ends

        year_ends = recent_fiscal_year_ends(int(day), int(month))
        return jsonify({"year_ends": [d.isoformat() for d in year_ends]})
    except Exception as exc:
        logger.warning("Failed to fetch year ends for %s: %s", tenant_id, exc)
        return jsonify({"year_ends": []})


@main_bp.route("/partner/clients")
@login_required
def partner_clients():
    """Firm-wide client overview for partners: latest review per client,
    across all staff, with a positive/negative rollup — not scoped to the
    signed-in user like the regular dashboard."""
    if not current_user.is_partner:
        abort(403)

    all_notes = (
        ReviewNote.query.filter_by(status="COMPLETED")
        .order_by(ReviewNote.created_at.desc())
        .all()
    )

    latest_by_tenant = {}
    for note in all_notes:
        if note.tenant_id not in latest_by_tenant:
            latest_by_tenant[note.tenant_id] = note

    rows = []
    for note in latest_by_tenant.values():
        csv_path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"{note.run_id}.csv")
        sentiment = summarize_review_sentiment(csv_path)
        rows.append(
            {
                "tenant_id": note.tenant_id,
                "tenant_name": note.tenant_name or "Unknown Client",
                "run_id": note.run_id,
                "created_at": note.created_at,
                "reviewed_by": note.user.email if note.user else "Unknown",
                "sentiment": sentiment,
            }
        )

    rows.sort(key=lambda r: r["created_at"], reverse=True)

    return render_template("partner_clients.html", rows=rows)
