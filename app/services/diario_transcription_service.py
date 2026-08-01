"""Orchestrazione trascrizione consultation (decrypt → transcribe → persist)."""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Optional

from app.config.config import Config
from app.models.diario import AudioRecording, Consultation, Transcript
from app.models.enums import ConsultationStato
from app.models.models import db
from app.services.diario_audio_service import DiarioAudioError, assert_consultation_ownership
from app.services.job_locks import acquire_job, claim_job, is_job_running, release_job
from app.services.transcription import get_transcriber
from app.services.transcription.base import (
    TranscriptionError,
    TranscriptionResult,
    TransientTranscriptionError,
)
from app.utils.audio_crypto import decrypt_file_streaming, load_audio_key

logger = logging.getLogger(__name__)

_JOB_KIND = "transcribe"


def _mark_running(consultation_id: int) -> bool:
    """Registra un job in corso (lock file, cross-process)."""
    return acquire_job(_JOB_KIND, consultation_id)


def _unmark_running(consultation_id: int) -> None:
    release_job(_JOB_KIND, consultation_id)


def is_transcription_running(consultation_id: int) -> bool:
    return is_job_running(_JOB_KIND, consultation_id)


def _ext_for_mime(mime: Optional[str]) -> str:
    mapping = {
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
    }
    if not mime:
        return ".bin"
    return mapping.get(mime.lower(), ".bin")


def _transcribe_with_retry(
    audio_path: str,
    *,
    language: str,
    max_attempts: int,
) -> TranscriptionResult:
    delay = Config.TRANSCRIPTION_RETRY_BASE_SEC
    last_exc: Optional[Exception] = None
    transcriber = get_transcriber()

    for attempt in range(1, max_attempts + 1):
        try:
            return transcriber.transcribe(audio_path, language=language)
        except TransientTranscriptionError as exc:
            last_exc = exc
            logger.warning(
                "Trascrizione transitoria tentativo %s/%s: %s",
                attempt,
                max_attempts,
                exc,
            )
            if attempt >= max_attempts:
                break
            time.sleep(delay)
            delay *= 2
        except TranscriptionError:
            raise

    raise TransientTranscriptionError(
        f"Trascrizione fallita dopo {max_attempts} tentativi: {last_exc}"
    )


def enqueue_transcription(*, consultation_id: int, utente_id: int) -> dict:
    """Valida ownership/precondizioni e prepara il payload di accettazione job.

    Non esegue la trascrizione: il caller deve passare ``run_transcription_job``
    a :class:`BackgroundTasks`.
    """
    consultation = db.session.get(Consultation, consultation_id)
    if consultation is None:
        raise DiarioAudioError("Consultation non trovata", status_code=404)

    assert_consultation_ownership(consultation, utente_id)

    recording = AudioRecording.query.filter_by(consultation_id=consultation.id).first()
    if recording is None or recording.cancellato_il is not None:
        raise DiarioAudioError("Nessun audio attivo da trascrivere", status_code=400)

    if is_transcription_running(consultation.id):
        raise DiarioAudioError("Trascrizione già in corso", status_code=409)

    if consultation.stato == ConsultationStato.TRASCRITTO and consultation.transcript:
        raise DiarioAudioError(
            "Consultation già trascritta. Elimina/riesegui solo se necessario.",
            status_code=409,
        )

    if consultation.stato not in (
        ConsultationStato.CARICATO,
        ConsultationStato.ERRORE,
        ConsultationStato.TRASCRITTO,
    ):
        # TRASCRITTO senza transcript già gestito sopra; BOZZA non ha senso
        if consultation.stato == ConsultationStato.BOZZA:
            raise DiarioAudioError(
                "Carica prima l'audio (stato BOZZA)",
                status_code=400,
            )

    if not _mark_running(consultation.id):
        raise DiarioAudioError("Trascrizione già in corso", status_code=409)

    # Pulisce errore precedente all'accettazione del job
    consultation.errore_pipeline = None
    db.session.commit()

    return {
        "consultation_id": consultation.id,
        "stato": consultation.stato.value if hasattr(consultation.stato, "value") else consultation.stato,
        "job": "accepted",
        "in_progress": True,
    }


def run_transcription_job(consultation_id: int) -> None:
    """Job isolato: adatto a thread BackgroundTasks o a un task Celery futuro."""
    claim_job(_JOB_KIND, consultation_id)
    tmp_path: Optional[Path] = None
    try:
        consultation = db.session.get(Consultation, consultation_id)
        if consultation is None:
            logger.error("Job trascrizione: consultation %s assente", consultation_id)
            return

        recording = AudioRecording.query.filter_by(consultation_id=consultation.id).first()
        if recording is None or recording.cancellato_il is not None:
            consultation.stato = ConsultationStato.ERRORE
            consultation.errore_pipeline = "Audio assente o cancellato"
            db.session.commit()
            return

        enc_path = Path(recording.path_file)
        if not enc_path.is_file():
            consultation.stato = ConsultationStato.ERRORE
            consultation.errore_pipeline = f"File audio non trovato: {enc_path}"
            db.session.commit()
            return

        suffix = _ext_for_mime(recording.mime_type)
        tmp = tempfile.NamedTemporaryFile(prefix="diario_tx_", suffix=suffix, delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()

        key = load_audio_key(Config.AUDIO_ENCRYPTION_KEY)
        decrypt_file_streaming(
            enc_path,
            tmp_path,
            key,
            chunk_size=Config.AUDIO_CHUNK_SIZE,
        )

        language = Config.TRANSCRIPTION_LANGUAGE
        result = _transcribe_with_retry(
            str(tmp_path),
            language=language,
            max_attempts=Config.TRANSCRIPTION_MAX_ATTEMPTS,
        )

        existing = Transcript.query.filter_by(consultation_id=consultation.id).first()
        if existing is None:
            existing = Transcript(consultation_id=consultation.id)
            db.session.add(existing)

        existing.testo = result.text
        existing.lingua = result.language or language
        existing.provider = result.provider
        existing.modello = result.model
        existing.durata_elaborazione_sec = result.duration_sec

        consultation.stato = ConsultationStato.TRASCRITTO
        consultation.errore_pipeline = None
        db.session.commit()
        logger.info(
            "Trascrizione OK consultation=%s provider=%s model=%s chars=%s",
            consultation_id,
            result.provider,
            result.model,
            len(result.text),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Trascrizione ERRORE consultation=%s: %s", consultation_id, exc)
        try:
            consultation = db.session.get(Consultation, consultation_id)
            if consultation is not None:
                consultation.stato = ConsultationStato.ERRORE
                consultation.errore_pipeline = str(exc)[:2000]
                db.session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Impossibile salvare stato ERRORE per %s", consultation_id)
            db.session.rollback()
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Cleanup temp trascrizione fallito %s: %s", tmp_path, exc)
        _unmark_running(consultation_id)


def get_consultation_status(*, consultation_id: int, utente_id: int) -> dict:
    """Stato corrente + eventuale errore (e flag in_progress)."""
    from app.services.diario_extraction_service import is_extraction_running

    consultation = db.session.get(Consultation, consultation_id)
    if consultation is None:
        raise DiarioAudioError("Consultation non trovata", status_code=404)

    assert_consultation_ownership(consultation, utente_id)

    stato = consultation.stato.value if hasattr(consultation.stato, "value") else consultation.stato
    has_audio = (
        consultation.audio_recording is not None
        and consultation.audio_recording.cancellato_il is None
    )
    has_transcript = consultation.transcript is not None
    has_diary = consultation.diary_entry is not None
    tx_running = is_transcription_running(consultation.id)
    ex_running = is_extraction_running(consultation.id)

    return {
        "consultation_id": consultation.id,
        "stato": stato,
        "in_progress": tx_running or ex_running,
        "transcription_in_progress": tx_running,
        "extraction_in_progress": ex_running,
        "errore": consultation.errore_pipeline,
        "has_audio": has_audio,
        "has_transcript": has_transcript,
        "has_diary_entry": has_diary,
        "transcript_preview": (
            (consultation.transcript.testo[:240] + "…")
            if has_transcript
            and consultation.transcript.testo
            and len(consultation.transcript.testo) > 240
            else (consultation.transcript.testo if has_transcript else None)
        ),
        "riassunto": (
            consultation.diary_entry.riassunto_testo if has_diary else None
        ),
    }
