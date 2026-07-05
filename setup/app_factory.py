"""Flask application factory and global configuration."""
from __future__ import annotations

import logging
import os
import secrets
import urllib.parse

import dotenv
from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

dotenv.load_dotenv()

logger = logging.getLogger(__name__)


def _resolve_secret_key() -> str:
    """Use a stable secret key from env so user sessions survive restarts."""
    key = os.environ.get("FLASK_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if key:
        return key
    logger.warning(
        "FLASK_SECRET_KEY is not set; generating an ephemeral key. "
        "User sessions WILL NOT survive process restarts. Set FLASK_SECRET_KEY in production."
    )
    return secrets.token_urlsafe(32)


def _resolve_database_uri() -> str:
    """Build a SQLAlchemy URI from the configured env vars, falling back to SQLite.

    In production (REPLIT_DEPLOYMENT set) we refuse to silently fall back to a
    local SQLite file: that would split user/session data across container
    restarts and mask real infrastructure problems. Instead we raise loudly.
    """
    is_production = bool(os.environ.get("REPLIT_DEPLOYMENT"))
    db_conn = os.environ.get("DATABASE_CONNECTION_STRING", "").strip()
    if not db_conn:
        if is_production:
            raise RuntimeError(
                "DATABASE_CONNECTION_STRING is not set in production. "
                "Refusing to fall back to local SQLite."
            )
        return "sqlite:///users.db"

    if "Server=tcp:" in db_conn:
        # Azure SQL via ODBC. Sanitise common quirks.
        db_conn = (
            db_conn.replace("Encrypt=True", "Encrypt=yes")
            .replace("Encrypt=False", "Encrypt=no")
            .replace("TrustServerCertificate=True", "TrustServerCertificate=yes")
            .replace("TrustServerCertificate=False", "TrustServerCertificate=no")
            .replace("User ID=", "UID=")
            .replace("Password=", "PWD=")
            .replace("Initial Catalog=", "Database=")
        )
        if "Driver=" not in db_conn:
            import subprocess

            try:
                drivers_out = subprocess.check_output(["odbcinst", "-q", "-d"]).decode()
                if "ODBC Driver 18 for SQL Server" in drivers_out:
                    db_conn = "Driver={ODBC Driver 18 for SQL Server};" + db_conn
                elif "ODBC Driver 17 for SQL Server" in drivers_out:
                    db_conn = "Driver={ODBC Driver 17 for SQL Server};" + db_conn
            except Exception as exc:
                logger.warning("Could not list ODBC drivers: %s", exc)

        try:
            import pyodbc

            pyodbc.connect(db_conn, timeout=5)
            params = urllib.parse.quote_plus(db_conn)
            return f"mssql+pyodbc:///?odbc_connect={params}"
        except Exception as exc:
            if is_production:
                raise RuntimeError(
                    f"Azure SQL connection failed in production: {exc}"
                ) from exc
            logger.warning(
                "Azure SQL connection unavailable (%s); falling back to SQLite for dev.",
                exc,
            )
            return "sqlite:///users.db"

    return db_conn


def create_app() -> Flask:
    """Create and configure the Flask application."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
    )

    app.config["SECRET_KEY"] = _resolve_secret_key()
    app.config["UPLOAD_FOLDER"] = os.path.join(base_dir, "uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    app.config["SQLALCHEMY_DATABASE_URI"] = _resolve_database_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    from setup.models import User, db

    db.init_app(app)

    db_schema = os.environ.get("DATABASE_SCHEMA")
    is_sqlite = "sqlite" in app.config["SQLALCHEMY_DATABASE_URI"]
    if db_schema and not is_sqlite:
        db.metadata.schema = db_schema
        for table in db.metadata.tables.values():
            if table.schema is None:
                table.schema = db_schema

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def _load_user(user_id):
        return User.query.get(int(user_id))

    CSRFProtect(app)

    # Register all blueprints
    from routes.auth_routes import auth_bp
    from routes.cash_flow_routes import cash_flow_bp
    from routes.chat_routes import chat_bp
    from routes.main_routes import main_bp
    from routes.plan_routes import plan_bp
    from routes.report_routes import report_bp
    from routes.workbench_routes import workbench_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(workbench_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(cash_flow_bp)
    app.register_blueprint(plan_bp)
    app.register_blueprint(chat_bp)

    # Opt-in autonomous Cash Flow Accelerator rescans (detection + drafting
    # only, never sends outreach) — a genuine no-op unless
    # CASH_FLOW_AUTOSCAN_ENABLED is set (see helpers/cash_flow_scheduler.py).
    from helpers.cash_flow_scheduler import start_cash_flow_autoscan

    start_cash_flow_autoscan(app)

    return app
