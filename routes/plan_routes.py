"""CRUD for per-client Plans and PlanSteps (the Plan/Timeline tabs)."""
from __future__ import annotations

import logging
import os
from datetime import datetime

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, request, url_for
from flask_login import current_user, login_required

from helpers.access import user_can_view_tenant
from helpers.plan_generator import generate_plan_from_review, suggest_plan_step
from setup.models import Plan, PlanStep, ReviewNote, db

logger = logging.getLogger(__name__)

plan_bp = Blueprint("plan", __name__)


def _require_view(tenant_id):
    if not user_can_view_tenant(current_user, tenant_id):
        abort(403)


def _require_manage(tenant_id):
    _require_view(tenant_id)
    if current_user.role == 'client':
        abort(403)


def _redirect_to_plan_tab(tenant_id):
    """All plan actions land back on the Plan tab, not whatever tab is default for the role."""
    return redirect(url_for("main.client_detail", tenant_id=tenant_id) + "#plan")


def _get_plan_or_404(tenant_id, plan_id):
    plan = Plan.query.filter_by(id=plan_id, tenant_id=tenant_id).first()
    if not plan:
        abort(404)
    return plan


def _get_step_or_404(tenant_id, plan_id, step_id):
    plan = _get_plan_or_404(tenant_id, plan_id)
    step = PlanStep.query.filter_by(id=step_id, plan_id=plan.id).first()
    if not step:
        abort(404)
    return plan, step


@plan_bp.route("/client/<tenant_id>/plans", methods=["POST"])
@login_required
def create_plan(tenant_id):
    _require_manage(tenant_id)

    title = (request.form.get("title") or "").strip()
    if not title:
        flash("A plan needs a title.")
        return _redirect_to_plan_tab(tenant_id)

    source_review_note_id = request.form.get("source_review_note_id") or None
    if source_review_note_id:
        note = ReviewNote.query.filter_by(id=source_review_note_id, tenant_id=tenant_id).first()
        source_review_note_id = note.id if note else None

    plan = Plan(
        tenant_id=tenant_id,
        title=title,
        created_by_user_id=current_user.id,
        source_review_note_id=source_review_note_id,
    )
    db.session.add(plan)
    db.session.flush()

    raw_steps = request.form.get("steps") or ""
    for i, line in enumerate(s.strip() for s in raw_steps.splitlines()):
        if line:
            db.session.add(PlanStep(plan_id=plan.id, position=i, description=line))

    db.session.commit()
    flash(f'Plan "{title}" created.')
    return _redirect_to_plan_tab(tenant_id)


@plan_bp.route("/client/<tenant_id>/plans/<int:plan_id>/toggle", methods=["POST"])
@login_required
def toggle_plan(tenant_id, plan_id):
    _require_manage(tenant_id)
    plan = _get_plan_or_404(tenant_id, plan_id)
    plan.status = 'inactive' if plan.status == 'active' else 'active'
    db.session.commit()
    return _redirect_to_plan_tab(tenant_id)


@plan_bp.route("/client/<tenant_id>/plans/<int:plan_id>/edit", methods=["POST"])
@login_required
def edit_plan(tenant_id, plan_id):
    _require_manage(tenant_id)
    plan = _get_plan_or_404(tenant_id, plan_id)

    title = (request.form.get("title") or "").strip()
    if title:
        plan.title = title
        db.session.commit()
    return _redirect_to_plan_tab(tenant_id)


@plan_bp.route("/client/<tenant_id>/plans/<int:plan_id>/delete", methods=["POST"])
@login_required
def delete_plan(tenant_id, plan_id):
    _require_manage(tenant_id)
    plan = _get_plan_or_404(tenant_id, plan_id)
    db.session.delete(plan)
    db.session.commit()
    flash("Plan deleted.")
    return _redirect_to_plan_tab(tenant_id)


@plan_bp.route("/client/<tenant_id>/plans/<int:plan_id>/steps", methods=["POST"])
@login_required
def add_step(tenant_id, plan_id):
    _require_manage(tenant_id)
    plan = _get_plan_or_404(tenant_id, plan_id)

    description = (request.form.get("description") or "").strip()
    if not description:
        flash("A step needs a description.")
        return _redirect_to_plan_tab(tenant_id)

    next_position = max((s.position for s in plan.steps), default=-1) + 1
    db.session.add(PlanStep(plan_id=plan.id, position=next_position, description=description))
    db.session.commit()
    return _redirect_to_plan_tab(tenant_id)


@plan_bp.route("/client/<tenant_id>/plans/<int:plan_id>/steps/<int:step_id>/edit", methods=["POST"])
@login_required
def edit_step(tenant_id, plan_id, step_id):
    _require_manage(tenant_id)
    _plan, step = _get_step_or_404(tenant_id, plan_id, step_id)

    description = (request.form.get("description") or "").strip()
    if description:
        step.description = description
        db.session.commit()
    return _redirect_to_plan_tab(tenant_id)


@plan_bp.route("/client/<tenant_id>/plans/<int:plan_id>/steps/<int:step_id>/delete", methods=["POST"])
@login_required
def delete_step(tenant_id, plan_id, step_id):
    _require_manage(tenant_id)
    _plan, step = _get_step_or_404(tenant_id, plan_id, step_id)
    db.session.delete(step)
    db.session.commit()
    return _redirect_to_plan_tab(tenant_id)


@plan_bp.route("/client/<tenant_id>/plans/<int:plan_id>/steps/<int:step_id>/complete", methods=["POST"])
@login_required
def complete_step(tenant_id, plan_id, step_id):
    # Anyone with view access (staff/partner, or the granted client) can mark
    # their own work done — this is what feeds the Timeline tab.
    _require_view(tenant_id)
    _plan, step = _get_step_or_404(tenant_id, plan_id, step_id)

    step.status = 'done'
    step.completed_by_user_id = current_user.id
    step.completed_at = datetime.utcnow()
    step.completion_note = (request.form.get("completion_note") or "").strip() or None
    db.session.commit()
    return _redirect_to_plan_tab(tenant_id)


@plan_bp.route("/client/<tenant_id>/plans/<int:plan_id>/steps/<int:step_id>/reopen", methods=["POST"])
@login_required
def reopen_step(tenant_id, plan_id, step_id):
    _require_view(tenant_id)
    _plan, step = _get_step_or_404(tenant_id, plan_id, step_id)

    step.status = 'pending'
    step.completed_by_user_id = None
    step.completed_at = None
    step.completion_note = None
    db.session.commit()
    return _redirect_to_plan_tab(tenant_id)


@plan_bp.route("/client/<tenant_id>/plans/generate", methods=["POST"])
@login_required
def generate_plan(tenant_id):
    """AI-draft a plan from a completed review's weakest nominals.

    Always created inactive — the accountant reviews/edits the draft in the
    Plan tab and explicitly Activates it when they're happy with it.
    """
    _require_manage(tenant_id)

    run_id = request.form.get("run_id")
    note = ReviewNote.query.filter_by(run_id=run_id, tenant_id=tenant_id).first() if run_id else None
    if not note:
        flash("Could not find that review to generate a plan from.")
        return _redirect_to_plan_tab(tenant_id)

    run_csv_path = os.path.join(current_app.config["UPLOAD_FOLDER"], f"{run_id}.csv")
    if not os.path.exists(run_csv_path):
        flash("This review's data file is missing, so a plan can't be generated from it.")
        return _redirect_to_plan_tab(tenant_id)

    try:
        drafted = generate_plan_from_review(run_csv_path)
    except Exception as exc:
        logger.exception("Plan generation failed for run %s", run_id)
        flash(f"AI plan generation failed: {exc}")
        return _redirect_to_plan_tab(tenant_id)

    plan = Plan(
        tenant_id=tenant_id,
        title=drafted["title"],
        status='inactive',
        created_by_user_id=current_user.id,
        source_review_note_id=note.id,
    )
    db.session.add(plan)
    db.session.flush()
    for i, step_text in enumerate(drafted["steps"]):
        db.session.add(PlanStep(plan_id=plan.id, position=i, description=step_text))
    db.session.commit()

    flash(f'AI drafted "{plan.title}" — review it below, then Activate when ready.')
    return _redirect_to_plan_tab(tenant_id)


@plan_bp.route("/client/<tenant_id>/plans/<int:plan_id>/suggest_step", methods=["POST"])
@login_required
def suggest_step(tenant_id, plan_id):
    """AI-draft one additional step from a free-text instruction. Read-only — no DB write."""
    _require_manage(tenant_id)
    plan = _get_plan_or_404(tenant_id, plan_id)

    instruction = ((request.get_json(silent=True) or {}).get("instruction") or "").strip()
    if not instruction:
        return jsonify({"status": "Error", "message": "Describe what you want the step to cover."}), 400

    try:
        suggestion = suggest_plan_step([s.description for s in plan.steps], instruction)
    except Exception as exc:
        logger.exception("Step suggestion failed for plan %s", plan_id)
        return jsonify({"status": "Error", "message": str(exc)}), 500

    return jsonify({"status": "Success", "suggestion": suggestion})
