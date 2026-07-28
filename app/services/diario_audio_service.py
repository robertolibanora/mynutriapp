"""Servizio upload/cancellazione audio colloquio (diario paziente)."""

from __future__ import annotations

import logging
import mimetypes
import os
import uuid
import wave
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Optional

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.config.config import Config
from app.models.diario import AudioRecording, Consultation
from app.models.enums import ConsultationStato
from app.models.models import Patient, db
from app.utils.audio_crypto import (
    AudioCryptoError,
    encrypt_file_streaming,
    load_audio_key,
    stream_to_file_with_hash,
)

logger = logging.getLogger(__name__)

MIME_TO_EXT = {
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}


class DiarioAudioError(Exception):
    """Errore di dominio con ``status_code`` HTTP suggerito."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _safe_unlink(path: Optional[Path]) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Impossibile rimuovere %s: %s", path, exc)


def _normalize_mime(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    mime = raw.split(";", 1)[0].strip().lower()
    if mime == "audio/x-wav":
        return "audio/wav"
    return mime


def detect_mime(file_storage: FileStorage, plaintext_path: Path) -> str:
    """Determina il MIME da content-type, magic bytes e/o estensione."""
    candidates: list[str] = []
    declared = _normalize_mime(file_storage.mimetype or file_storage.content_type)
    if declared:
        candidates.append(declared)

    try:
        import magic  # type: ignore

        sniffed = _normalize_mime(magic.from_file(str(plaintext_path), mime=True))
        if sniffed:
            candidates.insert(0, sniffed)
    except Exception:  # noqa: BLE001
        # python-magic opzionale
        pass

    # Header WAV RIFF
    try:
        with plaintext_path.open("rb") as fh:
            header = fh.read(12)
        if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
            candidates.insert(0, "audio/wav")
        elif header[:3] == b"ID3" or header[:2] == b"\xff\xfb":
            candidates.insert(0, "audio/mpeg")
        elif header[:4] == b"fLaC":
            pass
        elif header[:4] == b"OggS":
            candidates.insert(0, "audio/ogg")
    except OSError:
        pass

    name = file_storage.filename or ""
    guess, _ = mimetypes.guess_type(name)
    guess_n = _normalize_mime(guess)
    if guess_n:
        candidates.append(guess_n)

    allowed = Config.AUDIO_ALLOWED_MIME
    for mime in candidates:
        if mime in allowed or (mime == "audio/x-wav" and "audio/wav" in allowed):
            return "audio/wav" if mime == "audio/x-wav" else mime

    raise DiarioAudioError(
        f"MIME type non consentito. Ammessi: {', '.join(sorted(allowed))}",
        status_code=415,
    )


def probe_duration_sec(plaintext_path: Path, mime: str) -> float:
    """Restituisce la durata reale in secondi."""
    if mime == "audio/wav":
        try:
            with wave.open(str(plaintext_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate <= 0:
                    raise DiarioAudioError("WAV non valido: sample rate assente")
                return frames / float(rate)
        except wave.Error as exc:
            raise DiarioAudioError(f"WAV non valido: {exc}") from exc

    try:
        from mutagen import File as MutagenFile  # type: ignore

        audio = MutagenFile(str(plaintext_path))
        if audio is not None and getattr(audio, "info", None) is not None:
            length = getattr(audio.info, "length", None)
            if length is not None and length >= 0:
                return float(length)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mutagen non ha potuto leggere la durata: %s", exc)

    raise DiarioAudioError(
        "Impossibile determinare la durata dell'audio",
        status_code=400,
    )


def assert_consultation_ownership(consultation: Consultation, utente_id: Optional[int]) -> None:
    if not utente_id:
        raise DiarioAudioError("Autenticazione nutrizionista richiesta", status_code=401)
    # Single-tenant: l'unico admin autenticato ha accesso a tutte le consultation
    if Config.SINGLE_TENANT:
        return
    if consultation.nutrizionista_id != utente_id:
        raise DiarioAudioError(
            "Non sei il nutrizionista proprietario di questa consultation",
            status_code=403,
        )


def assert_patient_recording_consent(patient: Patient) -> None:
    if not bool(getattr(patient, "consenso_registrazione", False)):
        raise DiarioAudioError(
            "Il paziente non ha dato il consenso alla registrazione audio "
            "(consenso_registrazione=False)",
            status_code=403,
        )


def _storage_dir(patient_id: int, consultation_id: int) -> Path:
    base = Path(Config.AUDIO_STORAGE_PATH)
    return base / str(patient_id) / str(consultation_id)


def upload_consultation_audio(
    *,
    consultation_id: int,
    utente_id: int,
    file_storage: FileStorage,
) -> AudioRecording:
    """Streaming upload → validate → encrypt → persist. Cleanup su errore."""
    if file_storage is None or not getattr(file_storage, "filename", None):
        raise DiarioAudioError("File audio mancante (campo 'audio')", status_code=400)

    consultation = db.session.get(Consultation, consultation_id)
    if consultation is None:
        raise DiarioAudioError("Consultation non trovata", status_code=404)

    assert_consultation_ownership(consultation, utente_id)

    patient = db.session.get(Patient, consultation.patient_id)
    if patient is None:
        raise DiarioAudioError("Paziente non trovato", status_code=404)
    assert_patient_recording_consent(patient)

    existing = AudioRecording.query.filter_by(consultation_id=consultation.id).first()
    if existing is not None and existing.cancellato_il is None:
        raise DiarioAudioError(
            "Esiste già un audio attivo per questa consultation",
            status_code=409,
        )

    original_name = secure_filename(file_storage.filename) or "audio.bin"
    plain_tmp: Optional[Path] = None
    enc_path: Optional[Path] = None
    previous_path: Optional[Path] = None

    try:
        dest_dir = _storage_dir(consultation.patient_id, consultation.id)
        dest_dir.mkdir(parents=True, exist_ok=True)

        plain_tmp = dest_dir / f".upload-{uuid.uuid4().hex}.part"
        stream: BinaryIO = file_storage.stream
        size, checksum = stream_to_file_with_hash(
            stream,
            plain_tmp,
            max_bytes=Config.AUDIO_MAX_BYTES,
            chunk_size=Config.AUDIO_CHUNK_SIZE,
        )
        if size <= 0:
            raise DiarioAudioError("File audio vuoto", status_code=400)

        mime = detect_mime(file_storage, plain_tmp)
        duration = probe_duration_sec(plain_tmp, mime)
        if duration > Config.AUDIO_MAX_DURATION_SEC:
            raise DiarioAudioError(
                f"Durata audio eccessiva: massimo {Config.AUDIO_MAX_DURATION_SEC:.0f}s",
                status_code=400,
            )

        ext = MIME_TO_EXT.get(mime, Path(original_name).suffix.lower() or ".bin")
        enc_name = f"{uuid.uuid4().hex}{ext}.enc"
        enc_path = dest_dir / enc_name

        key = load_audio_key(Config.AUDIO_ENCRYPTION_KEY)
        encrypt_file_streaming(
            plain_tmp, enc_path, key, chunk_size=Config.AUDIO_CHUNK_SIZE
        )
        _safe_unlink(plain_tmp)
        plain_tmp = None

        relative_path = str(enc_path)

        if existing is not None:
            # Sostituisce un audio soft-deleted
            if existing.path_file:
                previous_path = Path(existing.path_file)
            existing.path_file = relative_path
            existing.nome_originale = original_name
            existing.mime_type = mime
            existing.dimensione_byte = size
            existing.durata_sec = duration
            existing.checksum_sha256 = checksum
            existing.cifrato = True
            existing.cancellato_il = None
            recording = existing
        else:
            recording = AudioRecording(
                consultation_id=consultation.id,
                path_file=relative_path,
                nome_originale=original_name,
                mime_type=mime,
                dimensione_byte=size,
                durata_sec=duration,
                checksum_sha256=checksum,
                cifrato=True,
            )
            db.session.add(recording)

        consultation.stato = ConsultationStato.CARICATO
        db.session.commit()

        if previous_path and previous_path.exists() and previous_path != enc_path:
            _safe_unlink(previous_path)

        return recording

    except AudioCryptoError as exc:
        db.session.rollback()
        _safe_unlink(plain_tmp)
        _safe_unlink(enc_path)
        msg = str(exc)
        status = 413 if "troppo grande" in msg.lower() else 400
        raise DiarioAudioError(msg, status_code=status) from exc
    except DiarioAudioError:
        db.session.rollback()
        _safe_unlink(plain_tmp)
        _safe_unlink(enc_path)
        raise
    except Exception:
        db.session.rollback()
        _safe_unlink(plain_tmp)
        _safe_unlink(enc_path)
        logger.exception("Upload audio fallito")
        raise


def soft_delete_consultation_audio(
    *,
    consultation_id: int,
    utente_id: int,
) -> AudioRecording:
    """Cancella il file fisico e valorizza ``cancellato_il`` (soft delete)."""
    consultation = db.session.get(Consultation, consultation_id)
    if consultation is None:
        raise DiarioAudioError("Consultation non trovata", status_code=404)

    assert_consultation_ownership(consultation, utente_id)

    recording = AudioRecording.query.filter_by(consultation_id=consultation.id).first()
    if recording is None or recording.cancellato_il is not None:
        raise DiarioAudioError("Nessun audio attivo da cancellare", status_code=404)

    path = Path(recording.path_file) if recording.path_file else None
    recording.cancellato_il = datetime.utcnow()
    db.session.commit()

    _safe_unlink(path)
    return recording
