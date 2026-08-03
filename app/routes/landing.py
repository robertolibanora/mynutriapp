"""Landing pubblica Noira (HTML bundled statico)."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, redirect, send_from_directory, session, url_for

landing_bp = Blueprint("landing", __name__)

_LANDING_DIR = Path(__file__).resolve().parents[2] / "static" / "landing"


@landing_bp.route("/", methods=["GET"])
@landing_bp.route("/landing", methods=["GET"])
def landing():
    """Serve la landing ufficiale. Utenti già loggati → dashboard corretta."""
    role = session.get("role")
    if role == "user":
        return redirect(url_for("dashboard.user_dashboard"))
    if role == "nutrizionista":
        return redirect(url_for("dashboard.admin_dashboard"))
    if role == "super_admin":
        return redirect(url_for("super_admin.dashboard"))
    # Compat: vecchia success URL Stripe → login (il flusso nuovo usa /billing/success)
    from flask import request

    if request.args.get("checkout") == "success":
        return redirect(url_for("auth.login"))
    directory = _LANDING_DIR
    if not directory.is_dir():
        # fallback rispetto a static_folder Flask
        directory = Path(current_app.static_folder) / "landing"
    return send_from_directory(directory, "index.html", mimetype="text/html")
