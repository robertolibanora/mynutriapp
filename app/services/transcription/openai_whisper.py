"""Trascrizione via OpenAI Whisper API (fallback: i dati escono dal server)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from app.services.transcription.base import (
    Transcriber,
    TranscriptionError,
    TranscriptionResult,
    TransientTranscriptionError,
)

logger = logging.getLogger(__name__)


class OpenAIWhisperTranscriber(Transcriber):
    """Client Whisper API (``openai`` SDK)."""

    provider_name = "openai_whisper"

    def __init__(
        self,
        *,
        api_key: Optional[str],
        model: str = "whisper-1",
        timeout_sec: float = 120.0,
        base_url: Optional[str] = None,
    ) -> None:
        if not api_key:
            raise TranscriptionError("OPENAI_API_KEY non configurata per openai_whisper")
        self.api_key = api_key
        self.model = model
        self.timeout_sec = timeout_sec
        self.base_url = base_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise TranscriptionError(
                    "Pacchetto openai non installato. pip install openai"
                ) from exc
            kwargs = {"api_key": self.api_key, "timeout": self.timeout_sec}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def transcribe(self, audio_path: str, *, language: str) -> TranscriptionResult:
        started = time.perf_counter()
        path = Path(audio_path)
        if not path.is_file():
            raise TranscriptionError(f"File audio assente: {audio_path}")

        try:
            client = self._get_client()
            with path.open("rb") as fh:
                result = client.audio.transcriptions.create(
                    model=self.model,
                    file=fh,
                    language=language or None,
                )
            text = (getattr(result, "text", None) or "").strip()
        except TranscriptionError:
            raise
        except Exception as exc:  # noqa: BLE001
            status = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            msg = str(exc)
            if status in (408, 429, 500, 502, 503, 504) or "timeout" in msg.lower():
                raise TransientTranscriptionError(msg) from exc
            raise TranscriptionError(f"Whisper API fallita: {exc}") from exc

        elapsed = time.perf_counter() - started
        if not text:
            raise TranscriptionError("Trascrizione API vuota")

        return TranscriptionResult(
            text=text,
            language=language,
            provider=self.provider_name,
            model=self.model,
            duration_sec=round(elapsed, 3),
        )
