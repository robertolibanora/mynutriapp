import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8999")
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "2"))
worker_class = "gthread"
timeout = int(os.getenv("GUNICORN_TIMEOUT", "30"))
preload_app = True
accesslog = "-"
errorlog = "-"
capture_output = True
