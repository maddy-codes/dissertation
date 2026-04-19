from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from requests_oauthlib import OAuth2Session
import os

# Allow OAuth2 over HTTP for local development
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from setup.models import db, User

auth_bp = Blueprint('auth', __name__)

XERO_CLIENT_ID = os.environ.get("XERO_CLIENT_ID")
XERO_CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET")
AUTHORIZATION_BASE_URL = 'https://login.xero.com/identity/connect/authorize'
TOKEN_URL = 'https://identity.xero.com/connect/token'
REDIRECT_URI = os.environ.get("XERO_REDIRECT_URI", "http://localhost:5000/auth/xero/callback")
# scopes needed
SCOPE = ["openid", "profile", "email", "accounting.settings.read", "accounting.reports.profitandloss.read", "accounting.reports.trialbalance.read", "accounting.banktransactions.read", "offline_access"]

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('upload')) # Will redirect to dashboard logic later
        flash('Invalid credentials')
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
        return redirect(url_for('upload')) # Redirect to root dashboard
    return render_template('register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/auth/xero')
@login_required
def xero_login():
    if not XERO_CLIENT_ID or not XERO_CLIENT_SECRET:
        flash("Xero credentials not configured in env.")
        return redirect(url_for('upload'))
    xero = OAuth2Session(XERO_CLIENT_ID, redirect_uri=REDIRECT_URI, scope=SCOPE)
    authorization_url, state = xero.authorization_url(AUTHORIZATION_BASE_URL)
    session['oauth_state'] = state
    return redirect(authorization_url)

@auth_bp.route('/auth/xero/callback')
@login_required
def xero_callback():
    if not XERO_CLIENT_ID or not XERO_CLIENT_SECRET:
        return redirect(url_for('upload'))
    xero = OAuth2Session(XERO_CLIENT_ID, state=session.get('oauth_state'), redirect_uri=REDIRECT_URI)
    try:
        from requests.auth import HTTPBasicAuth
        auth = HTTPBasicAuth(XERO_CLIENT_ID, XERO_CLIENT_SECRET)
        token = xero.fetch_token(TOKEN_URL, authorization_response=request.url, auth=auth)
        
        current_user.set_xero_token(token)
        db.session.commit()
        flash("Xero Connected successfully!")
        return redirect(url_for('upload'))
    except Exception as e:
        flash(f"Xero Auth Failed: {str(e)}")
        return redirect(url_for('upload'))
