"""Revisione umana del diario: get / patch / confirm / reject / post-confirm amend."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.models.diario import Consultation, DiaryEntry, Transcript
from app.models.enums import ConsultationStato
from app.models.models import Patient, db
from app.schemas.diary_extraction import DiaryExtractionSchema
from app.services.diario_audio_service import DiarioAudioError, assert_consultation_ownership
from app.utils.audit import log_audit_event


def _stato_val(consultation: Consultation) -> str:
    return (
        consultation.stato.value
        if hasattr(consultation.stato, "value")
        else str(consultation.stato)
    )


def _is_confermato(consultation: Consultation) -> bool:
    return consultation.stato == ConsultationStato.CONFERMATO


def _serialize_entry(entry: DiaryEntry, *, confermato: bool) -> dict[str, Any]:
    return {
        "id": entry.id,
        "consultation_id": entry.consultation_id,
        "patient_id": entry.patient_id,
        "contenuto_json": entry.contenuto_json or {},
        "riassunto_testo": entry.riassunto_testo,
        "modello_usato": entry.modello_usato,
        "revisionato_da": entry.revisionato_da,
        "revisionato_il": entry.revisionato_il.isoformat() if entry.revisionato_il else None,
        "modificato_manualmente": bool(entry.modificato_manualmente),
        "creato_il": entry.creato_il.isoformat() if entry.creato_il else None,
        "aggiornato_il": entry.aggiornato_il.isoformat() if entry.aggiornato_il else None,
        # Flag espliciti per il frontend (non mischiare con storico validato)
        "confermato": confermato,
        "da_revisionare": not confermato,
        "valido_storico": confermato,
    }


def _load_owned_consultation(consultation_id: int, utente_id: int) -> Consultation:
    consultation = db.session.get(Consultation, consultation_id)
    if consultation is None:
        raise DiarioAudioError("Consultation non trovata", status_code=404)
    assert_consultation_ownership(consultation, utente_id)
    return consultation


def get_diary_for_review(*, consultation_id: int, utente_id: int) -> dict[str, Any]:
    """GET diary + trascrizione affiancata."""
    consultation = _load_owned_consultation(consultation_id, utente_id)
    entry = DiaryEntry.query.filter_by(consultation_id=consultation.id).first()
    if entry is None:
        raise DiarioAudioError("Diary entry non presente: esegui prima l'estrazione", status_code=404)

    transcript = Transcript.query.filter_by(consultation_id=consultation.id).first()
    patient = db.session.get(Patient, consultation.patient_id)
    confermato = _is_confermato(consultation)

    return {
        "consultation_id": consultation.id,
        "stato": _stato_val(consultation),
        "confermato": confermato,
        "da_revisionare": not confermato,
        "valido_storico": confermato,
        "modificabile": not confermato,
        "patient": {
            "id": patient.id if patient else consultation.patient_id,
            "nome": patient.nome if patient else None,
            "cognome": patient.cognome if patient else None,
        },
        "transcript": (
            {
                "id": transcript.id,
                "testo": transcript.testo,
                "lingua": transcript.lingua,
                "provider": transcript.provider,
                "modello": transcript.modello,
            }
            if transcript
            else None
        ),
        "diary_entry": _serialize_entry(entry, confermato=confermato),
    }


def patch_diary(
    *,
    consultation_id: int,
    utente_id: int,
    contenuto_json: Optional[dict[str, Any]] = None,
    riassunto_testo: Optional[str] = None,
) -> dict[str, Any]:
    """PATCH pre-conferma: modifica bozza. Bloccato se già CONFERMATO."""
    consultation = _load_owned_consultation(consultation_id, utente_id)
    if _is_confermato(consultation):
        raise DiarioAudioError(
            "Diario già confermato: usa PATCH .../diary/post-confirm per correzioni",
            status_code=409,
        )
    if consultation.stato not in (ConsultationStato.ELABORATO, ConsultationStato.ERRORE):
        # Consentiamo ELABORATO; ERRORE solo se esiste comunque una entry
        pass

    entry = DiaryEntry.query.filter_by(consultation_id=consultation.id).first()
    if entry is None:
        raise DiarioAudioError("Diary entry non presente", status_code=404)

    if contenuto_json is None and riassunto_testo is None:
        raise DiarioAudioError("Nessun campo da aggiornare", status_code=400)

    if contenuto_json is not None:
        try:
            validated = DiaryExtractionSchema.model_validate(contenuto_json)
        except Exception as exc:  # noqa: BLE001
            raise DiarioAudioError(f"contenuto_json non valido: {exc}", status_code=400) from exc
        entry.contenuto_json = validated.model_dump(mode="json")
        if riassunto_testo is None:
            entry.riassunto_testo = validated.riassunto

    if riassunto_testo is not None:
        text = riassunto_testo.strip()
        if not text:
            raise DiarioAudioError("riassunto_testo non può essere vuoto", status_code=400)
        entry.riassunto_testo = text
        # allinea anche il campo nello schema se presente
        payload = dict(entry.contenuto_json or {})
        payload["riassunto"] = text
        try:
            entry.contenuto_json = DiaryExtractionSchema.model_validate(payload).model_dump(
                mode="json"
            )
        except Exception:  # noqa: BLE001
            entry.contenuto_json = payload

    entry.modificato_manualmente = True
    if consultation.stato != ConsultationStato.ELABORATO:
        consultation.stato = ConsultationStato.ELABORATO
        consultation.errore_pipeline = None

    log_audit_event(
        "UPDATE",
        "diary_entry",
        entry.id,
        details={"consultation_id": consultation.id, "fase": "pre_conferma"},
    )
    db.session.commit()
    return get_diary_for_review(consultation_id=consultation_id, utente_id=utente_id)


def confirm_diary(*, consultation_id: int, utente_id: int) -> dict[str, Any]:
    """Conferma definitiva → CONFERMATO."""
    consultation = _load_owned_consultation(consultation_id, utente_id)
    entry = DiaryEntry.query.filter_by(consultation_id=consultation.id).first()
    if entry is None:
        raise DiarioAudioError("Diary entry non presente", status_code=404)
    if _is_confermato(consultation):
        raise DiarioAudioError("Diario già confermato", status_code=409)
    if consultation.stato != ConsultationStato.ELABORATO:
        raise DiarioAudioError(
            f"Puoi confermare solo un diario ELABORATO (stato={_stato_val(consultation)})",
            status_code=400,
        )

    entry.revisionato_da = utente_id
    entry.revisionato_il = datetime.utcnow()
    consultation.stato = ConsultationStato.CONFERMATO
    consultation.errore_pipeline = None

    log_audit_event(
        "DIARIO_CONFIRM",
        "diary_entry",
        entry.id,
        details={"consultation_id": consultation.id},
    )
    db.session.commit()
    return get_diary_for_review(consultation_id=consultation_id, utente_id=utente_id)


def reject_and_regenerate(*, consultation_id: int, utente_id: int) -> dict[str, Any]:
    """Scarta la bozza e prepara la rigenerazione (caller enqueue extract)."""
    consultation = _load_owned_consultation(consultation_id, utente_id)
    if _is_confermato(consultation):
        raise DiarioAudioError(
            "Diario confermato: non si può scartare. Usa post-confirm per correzioni.",
            status_code=409,
        )

    entry = DiaryEntry.query.filter_by(consultation_id=consultation.id).first()
    if entry is not None:
        log_audit_event(
            "DIARIO_REJECT",
            "diary_entry",
            entry.id,
            details={"consultation_id": consultation.id},
        )
        db.session.delete(entry)

    consultation.stato = ConsultationStato.TRASCRITTO
    consultation.errore_pipeline = None
    db.session.commit()

    return {
        "consultation_id": consultation.id,
        "stato": _stato_val(consultation),
        "job": "regenerate_requested",
        "da_revisionare": False,
        "confermato": False,
        "valido_storico": False,
        "message": "Bozza scartata: avviare estrazione",
    }


def amend_confirmed_diary(
    *,
    consultation_id: int,
    utente_id: int,
    contenuto_json: Optional[dict[str, Any]] = None,
    riassunto_testo: Optional[str] = None,
    motivo: Optional[str] = None,
) -> dict[str, Any]:
    """Correzione esplicita post-conferma (endpoint dedicato)."""
    consultation = _load_owned_consultation(consultation_id, utente_id)
    if not _is_confermato(consultation):
        raise DiarioAudioError(
            "Usa PATCH /diary per bozze non confermate",
            status_code=400,
        )

    entry = DiaryEntry.query.filter_by(consultation_id=consultation.id).first()
    if entry is None:
        raise DiarioAudioError("Diary entry non presente", status_code=404)

    if contenuto_json is None and riassunto_testo is None:
        raise DiarioAudioError("Nessun campo da aggiornare", status_code=400)

    if contenuto_json is not None:
        try:
            validated = DiaryExtractionSchema.model_validate(contenuto_json)
        except Exception as exc:  # noqa: BLE001
            raise DiarioAudioError(f"contenuto_json non valido: {exc}", status_code=400) from exc
        entry.contenuto_json = validated.model_dump(mode="json")
        if riassunto_testo is None:
            entry.riassunto_testo = validated.riassunto

    if riassunto_testo is not None:
        text = riassunto_testo.strip()
        if not text:
            raise DiarioAudioError("riassunto_testo non può essere vuoto", status_code=400)
        entry.riassunto_testo = text
        payload = dict(entry.contenuto_json or {})
        payload["riassunto"] = text
        entry.contenuto_json = DiaryExtractionSchema.model_validate(payload).model_dump(
            mode="json"
        )

    entry.modificato_manualmente = True
    entry.revisionato_da = utente_id
    entry.revisionato_il = datetime.utcnow()

    log_audit_event(
        "DIARIO_AMEND_POST_CONFIRM",
        "diary_entry",
        entry.id,
        details={
            "consultation_id": consultation.id,
            "motivo": (motivo or "")[:500],
        },
    )
    db.session.commit()
    return get_diary_for_review(consultation_id=consultation_id, utente_id=utente_id)


def list_patient_diaries(*, patient_id: int, utente_id: int) -> list[dict[str, Any]]:
    """Elenco consultation/diary del paziente (con flag revisione)."""
    rows = (
        Consultation.query.filter_by(patient_id=patient_id, nutrizionista_id=utente_id)
        .order_by(Consultation.data_colloquio.desc())
        .all()
    )
    out: list[dict[str, Any]] = []
    for c in rows:
        confermato = _is_confermato(c)
        entry = c.diary_entry
        out.append(
            {
                "consultation_id": c.id,
                "data_colloquio": c.data_colloquio.isoformat() if c.data_colloquio else None,
                "stato": _stato_val(c),
                "confermato": confermato,
                "da_revisionare": bool(entry) and not confermato,
                "valido_storico": confermato,
                "has_diary_entry": entry is not None,
                "riassunto": entry.riassunto_testo if entry else None,
            }
        )
    return out
