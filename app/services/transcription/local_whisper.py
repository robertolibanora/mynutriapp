"""Trascrizione locale con faster-whisper (dati sanitari restano sul server)."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.services.transcription.base import (
    Transcriber,
    TranscriptionError,
    TranscriptionResult,
    TransientTranscriptionError,
)

logger = logging.getLogger(__name__)


class LocalWhisperTranscriber(Transcriber):
    """Self-hosted Whisper via ``faster-whisper``."""

    provider_name = "local_whisper"

    def __init__(
        self,
        *,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        download_root: Optional[str] = None,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.download_root = download_root
        self._model: Any = None

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise TranscriptionError(
                    "faster-whisper non installato. Vedi docs/transcription_vps.md"
                ) from exc
            logger.info(
                "Caricamento modello faster-whisper size=%s device=%s compute=%s",
                self.model_size,
                self.device,
                self.compute_type,
            )
            kwargs: dict[str, Any] = {
                "device": self.device,
                "compute_type": self.compute_type,
            }
            if self.download_root:
                kwargs["download_root"] = self.download_root
            self._model = WhisperModel(self.model_size, **kwargs)
        return self._model

    def transcribe(self, audio_path: str, *, language: str) -> TranscriptionResult:
        started = time.perf_counter()
        try:
            model = self._get_model()
            segments, info = model.transcribe(
                audio_path,
                language=language or None,
                vad_filter=True,
            )
            parts = [seg.text.strip() for seg in segments if getattr(seg, "text", None)]
            text = " ".join(p for p in parts if p).strip()
            detected = getattr(info, "language", None) or language
        except TransientTranscriptionError:
            raise
        except TranscriptionError:
            raise
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if any(tok in msg for tok in ("timeout", "temporarily", "busy", "resource")):
                raise TransientTranscriptionError(str(exc)) from exc
            raise TranscriptionError(f"Trascrizione locale fallita: {exc}") from exc

        elapsed = time.perf_counter() - started
        if not text:
            raise TranscriptionError("Trascrizione vuota: audio senza parlato riconoscibile")

        return TranscriptionResult(
            text=text,
            language=detected,
            provider=self.provider_name,
            model=self.model_size,
            duration_sec=round(elapsed, 3),
        )
