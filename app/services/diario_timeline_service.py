"""Timeline e trend del diario paziente (solo storico validato di default)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from app.models.diario import Consultation, DiaryEntry
from app.models.enums import ConsultationStato
from app.models.models import Patient, db
from app.services.diario_audio_service import DiarioAudioError


def _parse_date(value: Optional[str], *, end_of_day: bool = False) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip()
    try:
        if len(text) == 10:
            d = date.fromisoformat(text)
            if end_of_day:
                return datetime(d.year, d.month, d.day, 23, 59, 59)
            return datetime(d.year, d.month, d.day, 0, 0, 0)
        return datetime.fromisoformat(text.replace("Z", ""))
    except ValueError as exc:
        raise DiarioAudioError(f"Data non valida: {value}", status_code=400) from exc


def _assert_patient_access(patient_id: int, utente_id: int) -> Patient:
    patient = db.session.get(Patient, patient_id)
    if patient is None:
        raise DiarioAudioError("Paziente non trovato", status_code=404)
    # Accesso: nutrizionista assegnato oppure proprietario di almeno una consultation
    if patient.nutrizionista_id == utente_id:
        return patient
    owned = (
        Consultation.query.filter_by(patient_id=patient_id, nutrizionista_id=utente_id)
        .limit(1)
        .first()
    )
    if owned is None:
        raise DiarioAudioError(
            "Non sei il nutrizionista proprietario di questo paziente",
            status_code=403,
        )
    return patient


def _key_fields(contenuto: Optional[dict]) -> dict[str, Any]:
    data = contenuto or {}
    misure = data.get("misure") or {}
    return {
        "peso_kg": data.get("peso_kg"),
        "aderenza_piano": data.get("aderenza_piano"),
        "vita_cm": misure.get("vita_cm"),
        "fianchi_cm": misure.get("fianchi_cm"),
        "massa_grassa_pct": misure.get("massa_grassa_pct"),
    }


def get_patient_diary_timeline(
    *,
    patient_id: int,
    utente_id: int,
    include_pending: bool = False,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    """Timeline paginata: CONFERMATE di default, data_colloquio DESC."""
    patient = _assert_patient_access(patient_id, utente_id)

    page = max(1, int(page or 1))
    per_page = min(100, max(1, int(per_page or 20)))
    dt_from = _parse_date(date_from, end_of_day=False)
    dt_to = _parse_date(date_to, end_of_day=True)

    q = (
        db.session.query(Consultation, DiaryEntry)
        .join(DiaryEntry, DiaryEntry.consultation_id == Consultation.id)
        .filter(
            Consultation.patient_id == patient_id,
            Consultation.nutrizionista_id == utente_id,
        )
    )
    if include_pending:
        q = q.filter(
            Consultation.stato.in_(
                [
                    ConsultationStato.CONFERMATO,
                    ConsultationStato.ELABORATO,
                ]
            )
        )
    else:
        q = q.filter(Consultation.stato == ConsultationStato.CONFERMATO)

    if dt_from is not None:
        q = q.filter(Consultation.data_colloquio >= dt_from)
    if dt_to is not None:
        q = q.filter(Consultation.data_colloquio <= dt_to)

    total = q.count()
    rows = (
        q.order_by(Consultation.data_colloquio.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    items: list[dict[str, Any]] = []
    for consultation, entry in rows:
        confermato = consultation.stato == ConsultationStato.CONFERMATO
        keys = _key_fields(entry.contenuto_json)
        items.append(
            {
                "diary_entry_id": entry.id,
                "consultation_id": consultation.id,
                "data_colloquio": (
                    consultation.data_colloquio.isoformat()
                    if consultation.data_colloquio
                    else None
                ),
                "riassunto": entry.riassunto_testo,
                "peso_kg": keys["peso_kg"],
                "aderenza_piano": keys["aderenza_piano"],
                "misure": {
                    "vita_cm": keys["vita_cm"],
                    "fianchi_cm": keys["fianchi_cm"],
                    "massa_grassa_pct": keys["massa_grassa_pct"],
                },
                "contenuto_json": entry.contenuto_json or {},
                "stato": (
                    consultation.stato.value
                    if hasattr(consultation.stato, "value")
                    else str(consultation.stato)
                ),
                "confermato": confermato,
                "da_revisionare": not confermato,
                "valido_storico": confermato,
                "consultation_url": f"/admin/diario/consultations/{consultation.id}/review",
                "api_diary_url": f"/api/consultations/{consultation.id}/diary",
            }
        )

    pages = (total + per_page - 1) // per_page if per_page else 0
    return {
        "patient_id": patient.id,
        "patient": {"id": patient.id, "nome": patient.nome, "cognome": patient.cognome},
        "include_pending": bool(include_pending),
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
        "items": items,
    }


def get_patient_diary_trends(
    *,
    patient_id: int,
    utente_id: int,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict[str, Any]:
    """Serie temporali numeriche (solo CONFERMATE). I null vengono saltati."""
    patient = _assert_patient_access(patient_id, utente_id)
    dt_from = _parse_date(date_from, end_of_day=False)
    dt_to = _parse_date(date_to, end_of_day=True)

    q = (
        db.session.query(Consultation, DiaryEntry)
        .join(DiaryEntry, DiaryEntry.consultation_id == Consultation.id)
        .filter(
            Consultation.patient_id == patient_id,
            Consultation.nutrizionista_id == utente_id,
            Consultation.stato == ConsultationStato.CONFERMATO,
        )
    )
    if dt_from is not None:
        q = q.filter(Consultation.data_colloquio >= dt_from)
    if dt_to is not None:
        q = q.filter(Consultation.data_colloquio <= dt_to)

    rows = q.order_by(Consultation.data_colloquio.asc()).all()

    series: dict[str, list[dict[str, Any]]] = {
        "peso_kg": [],
        "vita_cm": [],
        "fianchi_cm": [],
        "massa_grassa_pct": [],
    }

    for consultation, entry in rows:
        data_iso = (
            consultation.data_colloquio.isoformat() if consultation.data_colloquio else None
        )
        keys = _key_fields(entry.contenuto_json)
        mapping = {
            "peso_kg": keys["peso_kg"],
            "vita_cm": keys["vita_cm"],
            "fianchi_cm": keys["fianchi_cm"],
            "massa_grassa_pct": keys["massa_grassa_pct"],
        }
        for name, value in mapping.items():
            if value is None:
                continue
            try:
                num = float(value)
            except (TypeError, ValueError):
                continue
            series[name].append(
                {
                    "date": data_iso,
                    "value": num,
                    "consultation_id": consultation.id,
                }
            )

    return {
        "patient_id": patient.id,
        "series": series,
    }
