"""Creazione e serializzazione consultation (colloquio diario)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.config.config import Config
from app.models.diario import Consultation
from app.models.enums import ConsultationStato
from app.models.models import Patient, db
from app.services.diario_audio_service import DiarioAudioError
from app.services.diario_timeline_service import _assert_patient_access


def _parse_data_colloquio(raw: Optional[str]) -> datetime:
    if not raw or not str(raw).strip():
        return datetime.now().replace(microsecond=0)
    text = str(raw).strip().replace("Z", "")
    try:
        if len(text) == 10:
            return datetime.fromisoformat(text)
        if "T" in text:
            return datetime.fromisoformat(text)
        # datetime-local: 2026-07-29T14:30 or 2026-07-29 14:30
        return datetime.fromisoformat(text.replace(" ", "T"))
    except ValueError as exc:
        raise DiarioAudioError(f"Data colloquio non valida: {raw}", status_code=400) from exc


def create_consultation(
    *,
    patient_id: int,
    utente_id: int,
    data_colloquio: Optional[str] = None,
    note_manuali: Optional[str] = None,
    set_consenso_registrazione: bool = False,
    set_consenso_ai: bool = False,
) -> dict[str, Any]:
    """Crea una consultation in stato BOZZA e restituisce il payload JSON."""
    if not utente_id:
        raise DiarioAudioError("Autenticazione nutrizionista richiesta", status_code=401)

    patient = _assert_patient_access(patient_id, utente_id)

    if set_consenso_registrazione and not patient.consenso_registrazione:
        patient.consenso_registrazione = True
        patient.consenso_aggiornato_il = datetime.utcnow()
    if set_consenso_ai and not patient.consenso_ai:
        patient.consenso_ai = True
        patient.consenso_aggiornato_il = datetime.utcnow()

    if not Config.SINGLE_TENANT and patient.nutrizionista_id is None:
        patient.nutrizionista_id = utente_id

    consultation = Consultation(
        patient_id=patient.id,
        nutrizionista_id=utente_id,
        data_colloquio=_parse_data_colloquio(data_colloquio),
        stato=ConsultationStato.BOZZA,
        note_manuali=(note_manuali or "").strip() or None,
    )
    db.session.add(consultation)
    db.session.commit()

    return serialize_consultation(consultation)


def serialize_consultation(consultation: Consultation) -> dict[str, Any]:
    stato = (
        consultation.stato.value
        if hasattr(consultation.stato, "value")
        else consultation.stato
    )
    return {
        "id": consultation.id,
        "patient_id": consultation.patient_id,
        "nutrizionista_id": consultation.nutrizionista_id,
        "data_colloquio": (
            consultation.data_colloquio.isoformat() if consultation.data_colloquio else None
        ),
        "stato": stato,
        "note_manuali": consultation.note_manuali,
        "errore_pipeline": consultation.errore_pipeline,
        "creato_il": consultation.creato_il.isoformat() if consultation.creato_il else None,
        "pipeline_url": f"/admin/diario/consultations/{consultation.id}/pipeline",
        "review_url": f"/admin/diario/consultations/{consultation.id}/review",
    }


def get_consultation_for_pipeline(*, consultation_id: int, utente_id: int) -> dict[str, Any]:
    """Dati minimi per la pagina pipeline (upload + stati)."""
    from app.services.diario_audio_service import assert_consultation_ownership

    consultation = db.session.get(Consultation, consultation_id)
    if consultation is None:
        raise DiarioAudioError("Consultation non trovata", status_code=404)
    assert_consultation_ownership(consultation, utente_id)

    patient = db.session.get(Patient, consultation.patient_id)
    if patient is None:
        raise DiarioAudioError("Paziente non trovato", status_code=404)

    payload = serialize_consultation(consultation)
    payload["patient"] = {
        "id": patient.id,
        "nome": patient.nome,
        "cognome": patient.cognome,
        "consenso_registrazione": bool(patient.consenso_registrazione),
        "consenso_ai": bool(patient.consenso_ai),
    }
    return payload
