"""Serve la build Flutter web (PWA) sotto /m/ per QA da iPhone via QR."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Response, abort, send_from_directory

mobile_web_bp = Blueprint("mobile_web", __name__)

_WEB_ROOT = Path(__file__).resolve().parents[2] / "mobile_app" / "build" / "web"


def _web_root() -> Path:
    return _WEB_ROOT


@mobile_web_bp.route("/m/")
@mobile_web_bp.route("/m/<path:asset_path>")
def serve_flutter(asset_path: str = ""):
    root = _web_root()
    if not root.is_dir():
        abort(503, description="Build Flutter web assente. Esegui: flutter build web --base-href=/m/")

    # Asset esistenti (js, png, canvaskit, …)
    if asset_path:
        candidate = (root / asset_path).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            abort(404)
        if candidate.is_file():
            return send_from_directory(root, asset_path)

    # SPA / deep link → index.html
    return send_from_directory(root, "index.html")


@mobile_web_bp.after_request
def _flutter_cache_headers(response: Response):
    """Evita cache stale di index/bootstrap dopo ogni rebuild."""
    if response.mimetype in ("text/html", "application/javascript", "text/javascript"):
        response.headers["Cache-Control"] = "no-cache"
    return response
