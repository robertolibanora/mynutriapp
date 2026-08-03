"""Landing pubblica Noira (HTML bundled statico)."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, redirect, send_from_directory, session, url_for

landing_bp = Blueprint("landing", __name__)

_LANDING_DIR = Path(__file__).resolve().parents[2] / "static" / "landing"


@landing_bp.route("/", methods=["GET"])
@landing_bp.route("/landing", methods=["GET"])
def landing():
    """Serve la landing ufficiale. Paziente già loggato → dashboard."""
    if session.get("role") == "user":
        return redirect(url_for("dashboard.user_dashboard"))
    directory = _LANDING_DIR
    if not directory.is_dir():
        # fallback rispetto a static_folder Flask
        directory = Path(current_app.static_folder) / "landing"
    return send_from_directory(directory, "index.html", mimetype="text/html")
