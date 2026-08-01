"""Orchestrazione: transcript → OpenAI → diary_entry (stato ELABORATO)."""

from __future__ import annotations

import logging
from typing import Optional

from app.config.config import Config
from app.models.diario import Consultation, DiaryEntry, Transcript
from app.models.enums import ConsultationStato
from app.models.models import Patient, db
from app.services.diario_audio_service import DiarioAudioError, assert_consultation_ownership
from app.services.diary_extraction_openai import OpenAIDiaryExtractor, DiaryExtractionError, redact_secrets
from app.services.job_locks import acquire_job, claim_job, is_job_running, release_job
from app.utils.anonymize import anonymize_text, deanonymize_structure

logger = logging.getLogger(__name__)

_JOB_KIND = "extract"


def _mark_running(consultation_id: int) -> bool:
    return acquire_job(_JOB_KIND, consultation_id)


def _unmark_running(consultation_id: int) -> None:
    release_job(_JOB_KIND, consultation_id)


def is_extraction_running(consultation_id: int) -> bool:
    return is_job_running(_JOB_KIND, consultation_id)


def enqueue_diary_extraction(*, consultation_id: int, utente_id: int) -> dict:
    """Valida precondizioni e accetta il job (esecuzione via BackgroundTasks)."""
    consultation = db.session.get(Consultation, consultation_id)
    if consultation is None:
        raise DiarioAudioError("Consultation non trovata", status_code=404)

    assert_consultation_ownership(consultation, utente_id)

    transcript = Transcript.query.filter_by(consultation_id=consultation.id).first()
    if transcript is None or not (transcript.testo or "").strip():
        raise DiarioAudioError(
            "Trascrizione assente: esegui prima POST .../transcribe",
            status_code=400,
        )

    if is_extraction_running(consultation.id):
        raise DiarioAudioError("Estrazione diario già in corso", status_code=409)

    if consultation.stato == ConsultationStato.ELABORATO and consultation.diary_entry:
        raise DiarioAudioError(
            "Diario già elaborato per questa consultation",
            status_code=409,
        )

    if consultation.stato not in (
        ConsultationStato.TRASCRITTO,
        ConsultationStato.ERRORE,
        ConsultationStato.ELABORATO,
    ):
        raise DiarioAudioError(
            f"Stato non idoneo all'estrazione: {consultation.stato}",
            status_code=400,
        )

    if not _mark_running(consultation.id):
        raise DiarioAudioError("Estrazione diario già in corso", status_code=409)

    consultation.errore_pipeline = None
    db.session.commit()

    return {
        "consultation_id": consultation.id,
        "stato": consultation.stato.value
        if hasattr(consultation.stato, "value")
        else consultation.stato,
        "job": "accepted",
        "in_progress": True,
    }


def run_diary_extraction_job(consultation_id: int) -> None:
    """Job isolato (thread / futuro Celery): anonimizza → OpenAI → valida → salva."""
    claim_job(_JOB_KIND, consultation_id)
    try:
        consultation = db.session.get(Consultation, consultation_id)
        if consultation is None:
            logger.error("Job estrazione: consultation %s assente", consultation_id)
            return

        patient = db.session.get(Patient, consultation.patient_id)
        transcript = Transcript.query.filter_by(consultation_id=consultation.id).first()
        if patient is None or transcript is None or not (transcript.testo or "").strip():
            consultation.stato = ConsultationStato.ERRORE
            consultation.errore_pipeline = "Paziente o trascrizione assenti"
            db.session.commit()
            return

        anonymized, mapping = anonymize_text(transcript.testo, patient)
        # Sicurezza: non loggare testo (né chiaro né anonimizzato completo)
        logger.info(
            "Estrazione diario avviata consultation=%s chars=%s model=%s",
            consultation_id,
            len(anonymized),
            Config.OPENAI_DIARY_MODEL,
        )

        extractor = OpenAIDiaryExtractor()
        try:
            schema = extractor.extract(anonymized)
        except DiaryExtractionError as exc:
            consultation.stato = ConsultationStato.ERRORE
            consultation.errore_pipeline = redact_secrets(str(exc))[:2000]
            db.session.commit()
            logger.error(
                "Estrazione ERRORE consultation=%s: %s",
                consultation_id,
                consultation.errore_pipeline,
            )
            return

        payload = deanonymize_structure(schema.model_dump(mode="json"), mapping)
        # Ri-valida dopo deanonymize (struttura invariata)
        from app.schemas.diary_extraction import DiaryExtractionSchema

        validated = DiaryExtractionSchema.model_validate(payload)

        entry = DiaryEntry.query.filter_by(consultation_id=consultation.id).first()
        if entry is None:
            entry = DiaryEntry(
                consultation_id=consultation.id,
                patient_id=consultation.patient_id,
                contenuto_json={},
                modello_usato=extractor.model,
            )
            db.session.add(entry)

        entry.patient_id = consultation.patient_id
        entry.contenuto_json = validated.model_dump(mode="json")
        entry.riassunto_testo = validated.riassunto
        entry.modello_usato = extractor.model
        entry.modificato_manualmente = False

        consultation.stato = ConsultationStato.ELABORATO
        consultation.errore_pipeline = None
        db.session.commit()
        logger.info(
            "Estrazione OK consultation=%s model=%s",
            consultation_id,
            extractor.model,
        )
    except Exception as exc:  # noqa: BLE001
        safe = redact_secrets(str(exc))
        logger.exception(
            "Estrazione crash consultation=%s: %s", consultation_id, safe
        )
        try:
            consultation = db.session.get(Consultation, consultation_id)
            if consultation is not None:
                consultation.stato = ConsultationStato.ERRORE
                consultation.errore_pipeline = safe[:2000]
                db.session.commit()
        except Exception:  # noqa: BLE001
            db.session.rollback()
            logger.exception("Impossibile salvare ERRORE estrazione %s", consultation_id)
    finally:
        _unmark_running(consultation_id)
