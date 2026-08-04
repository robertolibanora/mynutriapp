"""Logica appuntamenti riusabile da web e API /api/v1."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from app.models.models import Appuntamento, Patient, db
from app.services.agenda_service import AgendaService

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

# Tipi prenotabili dal paziente autenticato (allineati a /prenota pubblico).
TIPI_PRENOTABILI = {
    "altro": "Prima consulenza",
    "check": "Check",
    "allenamento_1to1": "Allenamento 1to1",
}


class AppointmentBookingError(Exception):
    def __init__(self, message: str, *, code: str = "validation_error"):
        super().__init__(message)
        self.message = message
        self.code = code


def nutritionist_id_for_patient(patient: Patient) -> Optional[int]:
    nid = getattr(patient, "nutrizionista_id", None)
    return int(nid) if nid is not None else None


def list_availability_for_patient(
    patient: Patient, *, limite: int = 100
) -> dict[str, Any]:
    """Slot liberi del nutrizionista del paziente."""
    nid = nutritionist_id_for_patient(patient)
    if nid is None:
        return {
            "professionista": _professionista_name(patient),
            "slots": [],
            "tipi": [
                {"value": k, "label": v} for k, v in TIPI_PRENOTABILI.items()
            ],
            "error": "no_nutritionist",
        }

    raw = AgendaService.slot_liberi_per_select(limite=limite, utente_id=nid)
    slots = []
    for item in raw:
        data_str = item.get("data") or ""
        try:
            dt = datetime.strptime(data_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        slots.append(
            {
                "data_appuntamento": dt.isoformat(sep="T", timespec="seconds"),
                "data": dt.strftime("%Y-%m-%d"),
                "ora": dt.strftime("%H:%M"),
                "label": item.get("label") or "",
                "note": item.get("note") or "",
            }
        )

    return {
        "professionista": _professionista_name(patient),
        "slots": slots,
        "tipi": [{"value": k, "label": v} for k, v in TIPI_PRENOTABILI.items()],
    }


def book_for_patient(
    patient: Patient,
    *,
    data_appuntamento: datetime,
    tipo: str = "check",
    note: Optional[str] = None,
) -> Appuntamento:
    """Crea richiesta appuntamento (stato in_attesa) su uno slot libero."""
    nid = nutritionist_id_for_patient(patient)
    if nid is None:
        raise AppointmentBookingError(
            "Nessun nutrizionista collegato al tuo account",
            code="no_nutritionist",
        )

    if tipo not in TIPI_PRENOTABILI:
        raise AppointmentBookingError(
            "Tipo appuntamento non valido",
            code="invalid_tipo",
        )

    data_appuntamento = data_appuntamento.replace(second=0, microsecond=0)
    if data_appuntamento < datetime.now().replace(second=0, microsecond=0):
        raise AppointmentBookingError(
            "Non puoi prenotare uno slot passato",
            code="slot_past",
        )

    if not AgendaService.is_slot_disponibile(
        data_appuntamento, utente_id=nid
    ):
        raise AppointmentBookingError(
            "Questo orario non è più disponibile. Scegline un altro.",
            code="slot_unavailable",
        )

    appt = Appuntamento(
        patient_id=patient.id,
        utente_id=nid,
        created_by="user",
        data_appuntamento=data_appuntamento,
        tipo=tipo,
        stato="in_attesa",
        note=(note.strip() if note else None) or None,
    )
    db.session.add(appt)
    db.session.commit()
    return appt



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
