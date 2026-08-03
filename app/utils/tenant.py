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


def is_staff_role(role: str | None = None) -> bool:
    return (role or session.get("role")) in ("admin", "nutrizionista")


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
    """Nutrizionista (o legacy admin) loggato — tenant corrente."""
    if not is_staff_role():
        abort(403)
    uid = current_utente_id()
    if not uid:
        abort(403)
    return uid


def tenant_filter_enabled() -> bool:
    return not Config.SINGLE_TENANT


def tenant_utente_id_or_none() -> int | None:
    """ID tenant da usare nei filtri query (None se single-tenant)."""
    if not tenant_filter_enabled():
        return None
    return current_utente_id()


def assert_patient_tenant(patient) -> None:
    """403 se il paziente non appartiene al nutrizionista loggato."""
    if not tenant_filter_enabled() or not is_staff_role():
        return
    uid = current_utente_id()
    if not uid or getattr(patient, "nutrizionista_id", None) != uid:
        abort(403)
