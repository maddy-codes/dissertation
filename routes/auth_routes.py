from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from requests_oauthlib import OAuth2Session
import os
import json

# Allow OAuth2 over HTTP for local development
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from setup.models import db, User

auth_bp = Blueprint('auth', __name__)

XERO_CLIENT_ID = os.environ.get("XERO_CLIENT_ID")
XERO_CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET")
AUTHORIZATION_BASE_URL = 'https://login.xero.com/identity/connect/authorize'
TOKEN_URL = 'https://identity.xero.com/connect/token'
REDIRECT_URI = os.environ.get("XERO_REDIRECT_URI", "http://localhost:5000/auth/xero/callback")

# Scope Definitions
# 1. Identity Only (Pure Sign In) - No Organization Selection
IDENTITY_SCOPE = ["openid", "profile", "email"]

# 2. Accounting Access (Connect Client) - Triggers Organization Selection
ACCOUNTING_SCOPE = [
    "openid", "profile", "email", 
    "accounting.settings.read", 
    "accounting.reports.profitandloss.read", 
    "accounting.reports.trialbalance.read", 
    "accounting.banktransactions.read", 
    "offline_access"
]

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('upload'))
        flash('Invalid credentials. Please try again.')
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if not email or not password:
            flash('Email and password required')
            return redirect(url_for('auth.register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('auth.register'))
        new_user = User(email=email, password_hash=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('upload'))
    return render_template('register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/auth/xero')
def xero_login():
    """Sign In with Xero - Identity Only."""
    if not XERO_CLIENT_ID or not XERO_CLIENT_SECRET:
        flash("Xero credentials not configured in env.")
        return redirect(url_for('auth.login'))
    
    xero = OAuth2Session(XERO_CLIENT_ID, redirect_uri=REDIRECT_URI, scope=IDENTITY_SCOPE)
    authorization_url, state = xero.authorization_url(AUTHORIZATION_BASE_URL)
    session['oauth_state'] = state
    return redirect(authorization_url)

@auth_bp.route('/auth/xero/connect')
@login_required
def xero_connect():
    """Connect to Xero Organization - Accounting Access."""
    if not XERO_CLIENT_ID or not XERO_CLIENT_SECRET:
        flash("Xero credentials not configured in env.")
        return redirect(url_for('upload'))
    
    xero = OAuth2Session(XERO_CLIENT_ID, redirect_uri=REDIRECT_URI, scope=ACCOUNTING_SCOPE)
    # Use 'consent' to force selection if needed, but normally 'select_account' might be better for identity.
    # However, for accounting, default behavior is organization selection.
    authorization_url, state = xero.authorization_url(AUTHORIZATION_BASE_URL)
    session['oauth_state'] = state
    return redirect(authorization_url)

@auth_bp.route('/auth/xero/callback')
def xero_callback():
    if not XERO_CLIENT_ID or not XERO_CLIENT_SECRET:
        return redirect(url_for('auth.login'))
    
    xero = OAuth2Session(XERO_CLIENT_ID, state=session.get('oauth_state'), redirect_uri=REDIRECT_URI)
    try:
        from requests.auth import HTTPBasicAuth
        auth = HTTPBasicAuth(XERO_CLIENT_ID, XERO_CLIENT_SECRET)
        token = xero.fetch_token(TOKEN_URL, authorization_response=request.url, auth=auth)
        
        # Identity Discovery
        id_token = token.get('id_token')
        email = None
        xero_user_id = None
        
        if id_token:
            import jwt
            decoded = jwt.decode(id_token, options={"verify_signature": False})
            email = decoded.get('email')
            xero_user_id = decoded.get('xero_userid')

        target_user = None
        
        if current_user.is_authenticated:
            target_user = current_user
        else:
            if xero_user_id:
                target_user = User.query.filter_by(xero_user_id=xero_user_id).first()
            if not target_user and email:
                target_user = User.query.filter_by(email=email).first()
            
            if not target_user:
                target_user = User(email=email, xero_user_id=xero_user_id)
                db.session.add(target_user)
                db.session.commit()
            
            login_user(target_user)

        # Update user attributes
        if xero_user_id:
            target_user.xero_user_id = xero_user_id
        
        # Only overwrite token if this flow included accounting access (offline_access/accounting.*)
        # Or if we don't have a token yet.
        scopes_received = token.get('scope', [])
        if any(s.startswith('accounting') for s in scopes_received) or not target_user.xero_token_data:
            target_user.set_xero_token(token)
            
        db.session.commit()
        
        flash("Authentication successful.")
        return redirect(url_for('upload'))
        
    except Exception as e:
        flash(f"Xero Authentication Failed: {str(e)}")
        return redirect(url_for('auth.login'))
