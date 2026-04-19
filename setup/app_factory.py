import os
import secrets
from typing import Any
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from celery import Celery, Task
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

    app.config["CELERY"] = {
        "broker_url": f'rediss://{os.environ.get("AZURE_REDIS_PASSWORD")}@phmai.redis.cache.windows.net:6380/0?ssl_cert_reqs=CERT_NONE',
        "result_backend": f'rediss://{os.environ.get("AZURE_REDIS_PASSWORD")}@phmai.redis.cache.windows.net:6380/0?ssl_cert_reqs=CERT_NONE',
        "task_ignore_result": False,
    }
    
    # config if the app is running local redis
    # app.config["CELERY"] = {
    #     "broker_url": "redis://localhost:6379/0",
    #     "result_backend": "redis://localhost:6379/0",
    #     "task_ignore_result": False,
    # }
    
    csrf = CSRFProtect(app)

    return app


def create_celery_app(app: Flask) -> Celery:
    """Initialize and configure the Celery application."""

    class FlaskTask(Task):
        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.Task = FlaskTask
    celery_app.set_default()
    app.extensions["celery"] = celery_app

    return celery_app
