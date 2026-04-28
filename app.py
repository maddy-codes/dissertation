"""PHM Accountants AI Review Notes Portal — Flask entrypoint."""
from __future__ import annotations

import logging
import os

import dotenv

dotenv.load_dotenv()
os.chdir(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from setup.app_factory import create_app  # noqa: E402

app = create_app()


def _ensure_schema() -> None:
    with app.app_context():
        from setup.models import db

        db.create_all()


_ensure_schema()


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=5000, debug=debug, use_reloader=False)
