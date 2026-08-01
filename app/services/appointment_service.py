"""Logica appuntamenti riusabile da web e API /api/v1."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from app.models.models import Appuntamento, Patient

TIPO_LABELS = {
    "allenamento_1to1": "Allenamento 1to1",
    "rinnovo_dieta": "Rinnovo dieta",
    "rinnovo_allenamento": "Rinnovo allenamento",
    "check": "Check",
    "altro": "Altro",
}

STATO_LABELS = {
    "in_attesa": "In attesa",
    "confermato": "Confermato",
    "completato": "Completato",
    "annullato": "Annullato",
}


def list_for_patient(patient_id: int) -> list[Appuntamento]:
    return (
        Appuntamento.query.filter_by(patient_id=patient_id)
        .order_by(Appuntamento.data_appuntamento.asc())
        .all()
    )


def get_for_patient(appointment_id: int, patient_id: int) -> Optional[Appuntamento]:
    """Ritorna l'appuntamento solo se appartiene al paziente; altrimenti None."""
    appt = Appuntamento.query.filter_by(id=appointment_id).first()
    if appt is None or appt.patient_id != patient_id:
        return None
    return appt


def _professionista_name(patient: Optional[Patient]) -> str:
    if patient is not None:
        nutr = getattr(patient, "nutrizionista", None)
        if nutr is not None:
            name = f"{getattr(nutr, 'nome', '')} {getattr(nutr, 'cognome', '')}".strip()
            if name:
                return name
    return (os.getenv("ADMIN_NAME") or "MyNutriApp").strip()


def can_cancel(appt: Appuntamento, *, now: Optional[datetime] = None) -> bool:
    """Indicazione UI: annullabile se futuro e non già chiuso.

    L'annullamento via API non è esposto in questo step (solo flag).
    """
    now = now or datetime.now()
    if appt.stato in ("completato", "annullato"):
        return False
    return appt.data_appuntamento >= now


def serialize_appointment(
    appt: Appuntamento,
    *,
    patient: Optional[Patient] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    dt = appt.data_appuntamento
    patient = patient if patient is not None else getattr(appt, "patient", None)
    return {
        "id": appt.id,
        "data_appuntamento": dt.isoformat(sep="T", timespec="seconds") if dt else None,
        "data": dt.strftime("%Y-%m-%d") if dt else None,
        "ora": dt.strftime("%H:%M") if dt else None,
        "stato": appt.stato,
        "stato_label": STATO_LABELS.get(appt.stato, appt.stato),
        "tipo": appt.tipo,
        "tipo_label": TIPO_LABELS.get(appt.tipo, appt.tipo),
        "titolo": TIPO_LABELS.get(appt.tipo, appt.tipo),
        "note": appt.note,
        "professionista": _professionista_name(patient),
        "cancellabile": can_cancel(appt, now=now),
        "created_by": appt.created_by,
    }
