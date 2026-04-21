import os
import secrets
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

    # Configure SQLAlchemy
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    from setup.models import db
    db.init_app(app)

    # Configure Login Manager
    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    from setup.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    with app.app_context():
        db.create_all()

    csrf = CSRFProtect(app)

    return app

