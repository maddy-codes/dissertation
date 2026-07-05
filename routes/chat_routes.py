"""AI Chat page: pick a client, converse about it via the official Xero MCP server."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from flask import Blueprint, abort, flash, jsonify, render_template, request
from flask_login import current_user, login_required

from setup.models import ChatMessage, ChatSession, ClientMemory, db

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)

MEMORY_FACT_LIMIT = 50  # most recent facts injected into the system prompt


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


def _resolve_tenant_name(xero_client, tenant_id: str, connections: list[dict] | None = None) -> str | None:
    try:
        connections = connections if connections is not None else xero_client.list_connections()
        return next((c.get("tenantName") for c in connections if c.get("tenantId") == tenant_id), None)
    except Exception as exc:
        logger.warning("Could not resolve tenant name for %s: %s", tenant_id, exc)
        return None


def _load_session(user_id: int, tenant_id: str, session_id) -> ChatSession | None:
    """Load a specific session (validating ownership) or fall back to the most recent one."""
    if session_id:
        session_obj = ChatSession.query.filter_by(
            id=session_id, user_id=user_id, tenant_id=tenant_id
        ).first()
        if session_obj:
            return session_obj
    return (
        ChatSession.query.filter_by(user_id=user_id, tenant_id=tenant_id)
        .order_by(ChatSession.updated_at.desc())
        .first()
    )


def _session_preview(session_obj: ChatSession) -> str:
    first_user_msg = next((m for m in session_obj.messages if m.role == "user"), None)
    if not first_user_msg:
        return "New conversation"
    text = first_user_msg.content.strip()
    return text if len(text) <= 60 else text[:57] + "..."


# This feature reads/writes live Xero data through the accountant's own OAuth
# connection, same as the workbench/dashboard — the restricted 'client' role
# has no Xero token of its own (see setup/models.py), so it's staff/partner only.
def _chat_available_to(user) -> bool:
    return user.role != "client" and user.get_xero_token() is not None


@chat_bp.route("/chat")
@login_required
def chat_page():
    has_xero_token = _chat_available_to(current_user)
    connections = []
    if has_xero_token:
        try:
            xero_client = _xero_client()
            if xero_client:
                connections = xero_client.list_connections()
                connections.sort(key=lambda c: (c.get("tenantName") or "").lower())
        except Exception as exc:
            logger.warning("Could not load Xero connections for chat: %s", exc)
            flash(f"Could not load Xero connections: {exc}")
            has_xero_token = False

    tenant_id = request.args.get("tenant_id") or (connections[0]["tenantId"] if connections else None)
    tenant_name = next((c.get("tenantName") for c in connections if c.get("tenantId") == tenant_id), None)

    session_id = None
    if tenant_id:
        requested_session_id = request.args.get("session_id", type=int)
        session_obj = _load_session(current_user.id, tenant_id, requested_session_id)
        session_id = session_obj.id if session_obj else None

    return render_template(
        "chat.html",
        has_xero_token=has_xero_token,
        connections=connections,
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        session_id=session_id,
    )


@chat_bp.route("/api/chat/<tenant_id>/new", methods=["POST"])
@login_required
def chat_new_session(tenant_id):
    """Create and return a genuinely blank session.

    Just navigating to /chat with no session_id was never enough on its own
    — both this page and /history fall back to the most recently updated
    session whenever no session_id is given (so a plain reload resumes where
    you left off), which meant "New Chat" silently reopened the same
    conversation instead of starting a fresh one. Creating the row here and
    having the frontend redirect with its real id sidesteps that fallback.
    """
    if not _chat_available_to(current_user):
        return jsonify({"status": "Error", "message": "Not available for this account."}), 403

    xero_client = _xero_client()
    tenant_name = _resolve_tenant_name(xero_client, tenant_id) if xero_client else None
    session_obj = ChatSession(user_id=current_user.id, tenant_id=tenant_id, tenant_name=tenant_name)
    db.session.add(session_obj)
    db.session.commit()
    return jsonify({"status": "Success", "session_id": session_obj.id})


@chat_bp.route("/api/chat/<tenant_id>/sessions")
@login_required
def chat_sessions(tenant_id):
    if not _chat_available_to(current_user):
        return jsonify({"status": "Error", "message": "Not available for this account."}), 403

    sessions = (
        ChatSession.query.filter_by(user_id=current_user.id, tenant_id=tenant_id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return jsonify(
        {
            "status": "Success",
            "sessions": [
                {
                    "id": s.id,
                    "preview": _session_preview(s),
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                    "message_count": len(s.messages),
                }
                for s in sessions
            ],
        }
    )


@chat_bp.route("/api/chat/<tenant_id>/history")
@login_required
def chat_history(tenant_id):
    if not _chat_available_to(current_user):
        return jsonify({"status": "Error", "message": "Not available for this account."}), 403

    session_id = request.args.get("session_id", type=int)
    session_obj = _load_session(current_user.id, tenant_id, session_id)
    messages = []
    if session_obj:
        for m in session_obj.messages:
            messages.append(
                {
                    "role": m.role,
                    "content": m.content,
                    "artifact": json.loads(m.artifact_json) if m.artifact_json else None,
                }
            )
    return jsonify(
        {
            "status": "Success",
            "session_id": session_obj.id if session_obj else None,
            "messages": messages,
        }
    )


@chat_bp.route("/api/chat/<tenant_id>/message", methods=["POST"])
@login_required
def chat_message(tenant_id):
    if not _chat_available_to(current_user):
        return jsonify({"status": "Error", "message": "Not available for this account."}), 403

    xero_client = _xero_client()
    if not xero_client:
        return jsonify({"status": "Error", "message": "No Xero connection found."}), 400

    payload = request.get_json(silent=True) or {}
    user_message = (payload.get("message") or "").strip()
    if not user_message:
        return jsonify({"status": "Error", "message": "Message cannot be empty."}), 400

    requested_session_id = payload.get("session_id")
    session_obj = None
    if requested_session_id:
        session_obj = ChatSession.query.filter_by(
            id=requested_session_id, user_id=current_user.id, tenant_id=tenant_id
        ).first()
        if not session_obj:
            return jsonify({"status": "Error", "message": "Chat session not found."}), 404

    # Anything touching the DB here is wrapped: an unhandled exception (a
    # constraint violation, a dropped connection, anything) would otherwise
    # bubble up as a raw 500 HTML page, which the frontend's `res.json()`
    # can't parse — the user just sees a generic "network error" with no clue
    # what actually broke (see app.py's _reconcile_legacy_chat_schema for one
    # concrete case this bit us with).
    try:
        if not session_obj:
            tenant_name = _resolve_tenant_name(xero_client, tenant_id)
            session_obj = ChatSession(user_id=current_user.id, tenant_id=tenant_id, tenant_name=tenant_name)
            db.session.add(session_obj)
            db.session.commit()

        history = [{"role": m.role, "content": m.content} for m in session_obj.messages]
        history.append({"role": "user", "content": user_message})

        db.session.add(ChatMessage(session_id=session_obj.id, role="user", content=user_message))
        db.session.commit()

        memory_rows = (
            ClientMemory.query.filter_by(tenant_id=tenant_id)
            .order_by(ClientMemory.created_at.desc())
            .limit(MEMORY_FACT_LIMIT)
            .all()
        )
        memory_facts = [m.content for m in reversed(memory_rows)]
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to persist chat message for tenant %s", tenant_id)
        return jsonify({"status": "Error", "message": f"Could not save your message: {exc}"}), 500

    try:
        from integrations.xero_mcp_client import run_chat_turn

        access_token = xero_client.get_valid_access_token()
        try:
            short_code = xero_client.get_organisation_short_code(tenant_id)
        except Exception as exc:
            logger.warning("Could not resolve short code for %s: %s", tenant_id, exc)
            short_code = None
        result = run_chat_turn(
            tenant_id, access_token, history, short_code=short_code, memory_facts=memory_facts
        )
    except Exception as exc:
        logger.exception("Chat turn failed for tenant %s", tenant_id)
        return jsonify({"status": "Error", "message": str(exc)}), 500

    artifact = result.get("artifact")
    db.session.add(
        ChatMessage(
            session_id=session_obj.id,
            role="assistant",
            content=result.get("reply", ""),
            artifact_json=json.dumps(artifact) if artifact else None,
        )
    )
    session_obj.updated_at = datetime.utcnow()

    new_fact_rows = [
        ClientMemory(tenant_id=tenant_id, content=fact, source="ai", created_by_user_id=current_user.id)
        for fact in result.get("remembered_facts", [])
        if fact
    ]
    db.session.add_all(new_fact_rows)
    db.session.commit()

    return jsonify(
        {
            "status": "Success",
            "session_id": session_obj.id,
            "reply": result.get("reply", ""),
            "artifact": artifact,
            "tool_log": result.get("tool_log", []),
            "remembered_facts": [{"id": r.id, "content": r.content} for r in new_fact_rows],
        }
    )


@chat_bp.route("/api/chat/<tenant_id>/memory", methods=["GET", "POST"])
@login_required
def chat_memory(tenant_id):
    if not _chat_available_to(current_user):
        return jsonify({"status": "Error", "message": "Not available for this account."}), 403

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        content = (payload.get("content") or "").strip()
        if not content:
            return jsonify({"status": "Error", "message": "Fact cannot be empty."}), 400
        fact = ClientMemory(
            tenant_id=tenant_id,
            content=content[:500],
            source="manual",
            created_by_user_id=current_user.id,
        )
        db.session.add(fact)
        db.session.commit()
        return jsonify(
            {
                "status": "Success",
                "fact": {"id": fact.id, "content": fact.content, "source": fact.source},
            }
        )

    facts = (
        ClientMemory.query.filter_by(tenant_id=tenant_id)
        .order_by(ClientMemory.created_at.desc())
        .all()
    )
    return jsonify(
        {
            "status": "Success",
            "facts": [
                {"id": f.id, "content": f.content, "source": f.source} for f in facts
            ],
        }
    )


@chat_bp.route("/api/chat/<tenant_id>/memory/<int:memory_id>", methods=["DELETE"])
@login_required
def chat_memory_delete(tenant_id, memory_id):
    if not _chat_available_to(current_user):
        return jsonify({"status": "Error", "message": "Not available for this account."}), 403

    fact = ClientMemory.query.filter_by(id=memory_id, tenant_id=tenant_id).first()
    if not fact:
        abort(404)
    db.session.delete(fact)
    db.session.commit()
    return jsonify({"status": "Success"})
