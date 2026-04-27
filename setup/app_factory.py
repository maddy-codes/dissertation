import os
import secrets
import urllib.parse
from typing import Any
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager
import dotenv

dotenv.load_dotenv()

def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates"
        ),
        static_folder=os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "static"
        ),
    )
    app.config["SECRET_KEY"] = secrets.token_urlsafe(16)
    app.config["UPLOAD_FOLDER"] = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "uploads" 
    )
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Configure Database
    db_conn = os.environ.get("DATABASE_CONNECTION_STRING")
    db_schema = os.environ.get("DATABASE_SCHEMA")

    if db_conn:
        db_conn = db_conn.strip()
        if "Server=tcp:" in db_conn:
            # Handle Azure SQL / ODBC connection string
            
            # Sanitization for ODBC Driver 18+ compatibility
            db_conn = db_conn.replace("Encrypt=True", "Encrypt=yes")
            db_conn = db_conn.replace("Encrypt=False", "Encrypt=no")
            db_conn = db_conn.replace("TrustServerCertificate=True", "TrustServerCertificate=yes")
            db_conn = db_conn.replace("TrustServerCertificate=False", "TrustServerCertificate=no")

            # Normalize keys to standard ODBC abbreviations to avoid parsing ambiguity
            db_conn = db_conn.replace("User ID=", "UID=")
            db_conn = db_conn.replace("Password=", "PWD=")
            db_conn = db_conn.replace("Initial Catalog=", "Database=")

            if "Driver=" not in db_conn:
                # Inject the driver if missing (prefer 18, then 17)
                import subprocess
                try:
                    drivers_out = subprocess.check_output(["odbcinst", "-q", "-d"]).decode()
                    if "ODBC Driver 18 for SQL Server" in drivers_out:
                        db_conn = "Driver={ODBC Driver 18 for SQL Server};" + db_conn
                    elif "ODBC Driver 17 for SQL Server" in drivers_out:
                        db_conn = "Driver={ODBC Driver 17 for SQL Server};" + db_conn
                except Exception:
                    # Fallback or silent fail if odbcinst fails
                    pass

            # Check if pyodbc can actually connect; fall back to SQLite if not
            try:
                import pyodbc
                pyodbc.connect(db_conn, timeout=5)
                params = urllib.parse.quote_plus(db_conn)
                app.config["SQLALCHEMY_DATABASE_URI"] = f"mssql+pyodbc:///?odbc_connect={params}"
            except Exception:
                import logging
                logging.warning("Azure SQL connection unavailable; falling back to SQLite.")
                app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
        else:
            # Assume it's a standard SQLAlchemy URI
            app.config["SQLALCHEMY_DATABASE_URI"] = db_conn
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    from setup.models import db
    db.init_app(app)

    # Only apply schema prefix when using a non-SQLite backend
    is_sqlite = "sqlite" in app.config["SQLALCHEMY_DATABASE_URI"]
    if db_schema and not is_sqlite:
        # Set the default schema for metadata and all existing tables
        db.metadata.schema = db_schema
        for table in db.metadata.tables.values():
            if table.schema is None:
                table.schema = db_schema
        
    # Configure Login Manager
    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    from setup.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    csrf = CSRFProtect(app)

    return app

