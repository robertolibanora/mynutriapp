"""Interfaccia astratta e tipi per i trascrittori audio."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptionResult:
    """Esito normalizzato di una trascrizione."""

    text: str
    language: str
    provider: str
    model: str
    duration_sec: float


class TranscriptionError(Exception):
    """Errore permanente (non ritentare)."""


class TransientTranscriptionError(TranscriptionError):
    """Errore transitorio (rate limit, timeout, 5xx): soggetto a retry."""


class Transcriber(ABC):
    """Contratto comune: LocalWhisper / OpenAIWhisper / fake test."""

    provider_name: str

    @abstractmethod
    def transcribe(self, audio_path: str, *, language: str) -> TranscriptionResult:
        """Trascrive un file audio in chiaro su disco."""
