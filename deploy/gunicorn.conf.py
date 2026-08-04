import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8099")
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "2"))
worker_class = "gthread"
timeout = int(os.getenv("GUNICORN_TIMEOUT", "30"))
preload_app = True
accesslog = "-"
errorlog = "-"
capture_output = True


def post_fork(server, worker):
    """Dopo il fork: reset pool SQLAlchemy (connessioni MySQL non sono fork-safe)."""
    try:
        from wsgi import app
        from app.models import db

        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        server.log.info("SQLAlchemy engine disposed after fork (worker pid=%s)", worker.pid)
    except Exception as exc:
        server.log.warning("post_fork dispose fallito: %s", exc)
