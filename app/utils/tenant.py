"""Helper isolamento multi-tenant."""

from __future__ import annotations

from flask import abort, session

from app.config.config import Config


def current_utente_id() -> int | None:
    uid = session.get("utente_id")
    if uid is None:
        return None
    try:
        return int(uid)
    except (TypeError, ValueError):
        return None


def current_role() -> str | None:
    return session.get("role")


def require_super_admin() -> int:
    if session.get("role") != "super_admin":
        abort(403)
    uid = current_utente_id()
    if not uid:
        abort(403)
    return uid


def require_nutrizionista() -> int:
    if session.get("role") != "nutrizionista":
        abort(403)
    uid = current_utente_id()
    if not uid:
        abort(403)
    return uid


def require_tenant() -> int:
    """Nutrizionista loggato (tenant corrente)."""
    return require_nutrizionista()


def tenant_filter_enabled() -> bool:
    return not Config.SINGLE_TENANT
