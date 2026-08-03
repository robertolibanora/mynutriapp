"""Licensing: conteggio pazienti attivi e enforcement limiti piano.

Definizione unica: un paziente è ATTIVO se ha almeno una dieta attiva:
- DietPlan con status='published', oppure
- Dieta PDF con data_fine >= oggi.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from flask import jsonify
from sqlalchemy import exists, func, or_

from app.billing.plans import get_patient_limit, normalize_plan
from app.models.diario import Utente
from app.models.models import Dieta, DietPlan, Patient, db

PLAN_LIMIT_MESSAGE = (
    "Hai raggiunto il limite di pazienti attivi previsto dal tuo piano."
)
PLAN_LIMIT_ERROR = "plan_limit_reached"


class PlanLimitError(Exception):
    """Limite del piano raggiunto."""

    def __init__(self, message: str = PLAN_LIMIT_MESSAGE):
        self.message = message
        self.error = PLAN_LIMIT_ERROR
        super().__init__(message)

    def to_response(self):
        """Payload HTTP 403 standard."""
        return (
            jsonify({"error": self.error, "message": self.message}),
            403,
        )


def _active_diet_exists_clause(today: Optional[date] = None):
    today = today or date.today()
    published = exists().where(
        DietPlan.patient_id == Patient.id,
        DietPlan.status == "published",
    )
    pdf_active = exists().where(
        Dieta.patient_id == Patient.id,
        Dieta.data_fine >= today,
    )
    return or_(published, pdf_active)


def count_active_patients(user_id: int, *, today: Optional[date] = None) -> int:
    """Numero di pazienti unici del nutrizionista con almeno una dieta attiva."""
    if not user_id:
        return 0
    clause = _active_diet_exists_clause(today)
    total = (
        db.session.query(func.count(Patient.id))
        .filter(Patient.nutrizionista_id == int(user_id), clause)
        .scalar()
    )
    return int(total or 0)


def is_patient_active(patient_id: int, *, today: Optional[date] = None) -> bool:
    """True se il paziente ha almeno una dieta attiva."""
    if not patient_id:
        return False
    today = today or date.today()
    has_published = (
        db.session.query(DietPlan.id)
        .filter_by(patient_id=int(patient_id), status="published")
        .limit(1)
        .first()
        is not None
    )
    if has_published:
        return True
    has_pdf = (
        db.session.query(Dieta.id)
        .filter(
            Dieta.patient_id == int(patient_id),
            Dieta.data_fine >= today,
        )
        .limit(1)
        .first()
        is not None
    )
    return has_pdf


def get_utente_plan(user_id: int) -> str:
    row = db.session.get(Utente, int(user_id))
    if row is None:
        return normalize_plan(None)
    return normalize_plan(getattr(row, "plan", None))


def get_subscription_usage(user_id: int, *, today: Optional[date] = None) -> dict[str, Any]:
    """Snapshot consumo piano per API/dashboard."""
    plan = get_utente_plan(user_id)
    active = count_active_patients(user_id, today=today)
    limit = get_patient_limit(plan)

    if limit is None:
        remaining = None
        percentage = 0
    else:
        remaining = max(0, limit - active)
        percentage = int(round((active / limit) * 100)) if limit > 0 else 0
        if percentage > 100:
            percentage = 100

    return {
        "plan": plan,
        "active_patients": active,
        "patient_limit": limit,
        "remaining": remaining,
        "percentage": percentage,
    }


def assert_within_plan_limit(user_id: int) -> None:
    """Blocca se il conteggio attuale è già al/oltre il limite (es. creazione paziente)."""
    plan = get_utente_plan(user_id)
    limit = get_patient_limit(plan)
    if limit is None:
        return
    if count_active_patients(user_id) >= limit:
        raise PlanLimitError()


def assert_can_increase_active_patients(
    user_id: int,
    *,
    patient_id: Optional[int] = None,
) -> None:
    """Blocca se l'azione renderebbe attivo un paziente nuovo oltre il limite.

    Se ``patient_id`` è già attivo, non aumenta il conteggio → ok.
    """
    plan = get_utente_plan(user_id)
    limit = get_patient_limit(plan)
    if limit is None:
        return
    if patient_id is not None and is_patient_active(int(patient_id)):
        return
    if count_active_patients(user_id) >= limit:
        raise PlanLimitError()
