"""Allenamenti paziente (piani PDF)."""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Optional

from app.config.config import get_full_path
from app.models.models import Allenamento


def list_for_patient(patient_id: int) -> list[Allenamento]:
    return (
        Allenamento.query.filter_by(patient_id=patient_id)
        .order_by(Allenamento.created_at.desc())
        .all()
    )


def get_active_for_patient(patient_id: int) -> Optional[Allenamento]:
    """Come dashboard web: ultimo per created_at."""
    return (
        Allenamento.query.filter_by(patient_id=patient_id)
        .order_by(Allenamento.created_at.desc())
        .first()
    )


def get_for_patient(workout_id: int, patient_id: int) -> Optional[Allenamento]:
    row = Allenamento.query.filter_by(id=workout_id).first()
    if row is None or row.patient_id != patient_id:
        return None
    return row


def resolve_pdf_path(allenamento: Allenamento) -> Optional[str]:
    if not allenamento.pdf_path:
        return None
    path = get_full_path(allenamento.pdf_path)
    if os.path.isfile(path):
        return path
    if os.path.isfile(allenamento.pdf_path):
        return allenamento.pdf_path
    return None


def _iso_dt(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep="T", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def serialize_workout(
    allenamento: Allenamento,
    *,
    attiva: bool = False,
) -> dict[str, Any]:
    return {
        "id": allenamento.id,
        "data_inizio": _iso_dt(allenamento.data_inizio),
        "data_fine": _iso_dt(allenamento.data_fine),
        "note": allenamento.note,
        "attiva": attiva,
        "has_pdf": bool(allenamento.pdf_path),
        "created_at": _iso_dt(allenamento.created_at),
    }


def build_list_payload(patient_id: int) -> dict[str, Any]:
    rows = list_for_patient(patient_id)
    active = get_active_for_patient(patient_id)
    active_id = active.id if active is not None else None
    return {
        "active": {"id": active_id} if active_id is not None else None,
        "workouts": [
            serialize_workout(w, attiva=(w.id == active_id)) for w in rows
        ],
    }
