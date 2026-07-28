"""Factory trascrittori: scelta solo da env/Config."""

from __future__ import annotations

from functools import lru_cache

from app.config.config import Config
from app.services.transcription.base import Transcriber, TranscriptionError
from app.services.transcription.local_whisper import LocalWhisperTranscriber
from app.services.transcription.openai_whisper import OpenAIWhisperTranscriber


@lru_cache(maxsize=1)
def get_transcriber() -> Transcriber:
    """Restituisce l'implementazione configurata con ``TRANSCRIPTION_PROVIDER``."""
    provider = (Config.TRANSCRIPTION_PROVIDER or "local_whisper").strip().lower()
    if provider in ("local_whisper", "local", "faster_whisper"):
        return LocalWhisperTranscriber(
            model_size=Config.WHISPER_MODEL_SIZE,
            device=Config.WHISPER_DEVICE,
            compute_type=Config.WHISPER_COMPUTE_TYPE,
            download_root=Config.WHISPER_DOWNLOAD_ROOT or None,
        )
    if provider in ("openai_whisper", "openai"):
        return OpenAIWhisperTranscriber(
            api_key=Config.OPENAI_API_KEY,
            model=Config.OPENAI_WHISPER_MODEL,
            timeout_sec=Config.OPENAI_WHISPER_TIMEOUT_SEC,
            base_url=Config.OPENAI_BASE_URL or None,
        )
    raise TranscriptionError(
        f"TRANSCRIPTION_PROVIDER sconosciuto: {provider!r} "
        "(ammessi: local_whisper, openai_whisper)"
    )


def reset_transcriber_cache() -> None:
    """Utile nei test per forzare la ri-creazione del provider."""
    get_transcriber.cache_clear()
