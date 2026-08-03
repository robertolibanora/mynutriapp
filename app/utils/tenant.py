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


def patients_query_for_tenant():
    """Query pazienti scoped al tenant corrente (o globale se single-tenant)."""
    from app.models.models import Patient

    q = Patient.query
    if tenant_filter_enabled() and is_staff_role():
        uid = current_utente_id()
        if not uid:
            abort(403)
        q = q.filter(Patient.nutrizionista_id == uid)
    return q


def get_tenant_patient_or_404(patient_id: int):
    """Carica paziente e verifica appartenenza al tenant."""
    from app.models.models import Patient

    patient = Patient.query.get_or_404(patient_id)
    assert_patient_tenant(patient)
    return patient


def assert_resource_patient_tenant(resource) -> None:
    """403 se la risorsa (con patient / patient_id) non appartiene al tenant."""
    if not tenant_filter_enabled() or not is_staff_role():
        return
    patient = getattr(resource, "patient", None)
    if patient is not None:
        assert_patient_tenant(patient)
        return
    patient_id = getattr(resource, "patient_id", None)
    if patient_id is None:
        abort(403)
    get_tenant_patient_or_404(int(patient_id))


def assert_appuntamento_tenant(appuntamento) -> None:
    """403 se l'appuntamento non appartiene al nutrizionista loggato."""
    if not tenant_filter_enabled() or not is_staff_role():
        return
    uid = current_utente_id()
    if not uid or getattr(appuntamento, "utente_id", None) != uid:
        abort(403)


def assert_diet_plan_tenant(plan) -> None:
    """403 se il diet plan non appartiene al tenant (via paziente / professional_id)."""
    if not tenant_filter_enabled() or not is_staff_role():
        return
    uid = current_utente_id()
    if not uid:
        abort(403)
    patient = getattr(plan, "patient", None)
    if patient is not None:
        assert_patient_tenant(patient)
    elif getattr(plan, "patient_id", None) is not None:
        get_tenant_patient_or_404(int(plan.patient_id))
    else:
        abort(403)
    professional_id = getattr(plan, "professional_id", None)
    if professional_id is not None and int(professional_id) != uid:
        abort(403)


def current_professional_id() -> int | None:
    """ID professionista in sessione (utente_id, fallback legacy professional_id)."""
    uid = current_utente_id()
    if uid is not None:
        return uid
    pid = session.get("professional_id")
    if pid is None:
        return None
    try:
        return int(pid)
    except (TypeError, ValueError):
        return None
