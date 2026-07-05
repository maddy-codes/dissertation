"""Authentication blueprint: local login/registration plus Xero OAuth flow."""
from __future__ import annotations

import logging
import os

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from requests_oauthlib import OAuth2Session
from werkzeug.security import check_password_hash, generate_password_hash

# Permit HTTP for OAuth callback ONLY when not running a Replit deployment.
# In production (REPLIT_DEPLOYMENT set), the callback must be HTTPS.
if not os.environ.get("REPLIT_DEPLOYMENT"):
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from setup.models import User, db

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

XERO_CLIENT_ID = os.environ.get("XERO_CLIENT_ID")
XERO_CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET")
AUTHORIZATION_BASE_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"

IDENTITY_SCOPE = ["openid", "profile", "email"]
ACCOUNTING_SCOPE = [
    "openid",
    "profile",
    "email",
    "accounting.settings.read",
    "accounting.reports.profitandloss.read",
    "accounting.reports.trialbalance.read",
    "accounting.transactions.read",
    "accounting.journals.read",
    "accounting.banktransactions.read",
    "accounting.contacts.read",
    "offline_access",
]


def _xero_redirect_uri() -> str:
    """Pick the Xero callback URL based on the runtime environment."""
    explicit = os.environ.get("XERO_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    replit_domain = os.environ.get("REPLIT_DEV_DOMAIN", "").strip()
    if replit_domain:
        return f"https://{replit_domain}/auth/xero/callback"
    return "http://localhost:5000/auth/xero/callback"


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("main.dashboard"))
        flash("Invalid credentials. Please try again.")
    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if not email or not password:
            flash("Email and password required.")
            return redirect(url_for("auth.register"))
        if User.query.filter_by(email=email).first():
            flash("Email already registered.")
            return redirect(url_for("auth.register"))
        new_user = User(email=email, password_hash=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("main.dashboard"))
    return render_template("register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/auth/xero")
def xero_login():
    """Sign in with Xero (identity only)."""
    if not XERO_CLIENT_ID or not XERO_CLIENT_SECRET:
        flash("Xero credentials not configured.")
        return redirect(url_for("auth.login"))

    xero = OAuth2Session(XERO_CLIENT_ID, redirect_uri=_xero_redirect_uri(), scope=IDENTITY_SCOPE)
    authorization_url, state = xero.authorization_url(AUTHORIZATION_BASE_URL)
    session["oauth_state"] = state
    return redirect(authorization_url)


@auth_bp.route("/auth/xero/connect")
@login_required
def xero_connect():
    """Connect a Xero organisation (full accounting scope)."""
    if not XERO_CLIENT_ID or not XERO_CLIENT_SECRET:
        flash("Xero credentials not configured.")
        return redirect(url_for("main.dashboard"))

    xero = OAuth2Session(
        XERO_CLIENT_ID, redirect_uri=_xero_redirect_uri(), scope=ACCOUNTING_SCOPE
    )
    authorization_url, state = xero.authorization_url(AUTHORIZATION_BASE_URL)
    session["oauth_state"] = state
    return redirect(authorization_url)


@auth_bp.route("/auth/xero/callback")
def xero_callback():
    if not XERO_CLIENT_ID or not XERO_CLIENT_SECRET:
        return redirect(url_for("auth.login"))

    xero = OAuth2Session(
        XERO_CLIENT_ID,
        state=session.get("oauth_state"),
        redirect_uri=_xero_redirect_uri(),
    )
    try:
        from requests.auth import HTTPBasicAuth

        auth = HTTPBasicAuth(XERO_CLIENT_ID, XERO_CLIENT_SECRET)
        token = xero.fetch_token(TOKEN_URL, authorization_response=request.url, auth=auth)

        id_token = token.get("id_token")
        email = None
        xero_user_id = None
        if id_token:
            import jwt

            decoded = jwt.decode(id_token, options={"verify_signature": False})
            email = decoded.get("email")
            xero_user_id = decoded.get("xero_userid")

        if current_user.is_authenticated:
            target_user = current_user
        else:
            target_user = None
            if xero_user_id:
                target_user = User.query.filter_by(xero_user_id=xero_user_id).first()
            if not target_user and email:
                target_user = User.query.filter_by(email=email).first()
            if not target_user:
                target_user = User(email=email, xero_user_id=xero_user_id)
                db.session.add(target_user)
                db.session.commit()
            login_user(target_user)

        if xero_user_id:
            target_user.xero_user_id = xero_user_id

        scopes_received = token.get("scope", []) or []
        if any(str(s).startswith("accounting") for s in scopes_received) or not target_user.xero_token_data:
            target_user.set_xero_token(token)

        db.session.commit()

        flash("Signed in successfully.")
        return redirect(url_for("main.dashboard"))
    except Exception as exc:
        logger.exception("Xero authentication failed")
        flash(f"Xero sign-in failed: {exc}")
        return redirect(url_for("auth.login"))
