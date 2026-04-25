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
            
            params = urllib.parse.quote_plus(db_conn)
            app.config["SQLALCHEMY_DATABASE_URI"] = f"mssql+pyodbc:///?odbc_connect={params}"
        else:
            # Assume it's a standard SQLAlchemy URI
            app.config["SQLALCHEMY_DATABASE_URI"] = db_conn
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    from setup.models import db
    db.init_app(app)

    if db_schema:
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
    
    with app.app_context():
        if db_schema and "mssql" in app.config["SQLALCHEMY_DATABASE_URI"]:
            from sqlalchemy import text
            try:
                # Check if schema exists
                check_schema = db.session.execute(text(f"SELECT name FROM sys.schemas WHERE name = '{db_schema}'")).fetchone()
                if not check_schema:
                    # Create schema if it doesn't exist
                    db.session.execute(text(f"CREATE SCHEMA {db_schema}"))
                    db.session.commit()
            except Exception as e:
                print(f"Warning: Could not ensure schema {db_schema} exists: {e}")
                db.session.rollback()

        db.create_all()

    csrf = CSRFProtect(app)

    return app

