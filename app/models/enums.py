"""Enum di dominio condivisi tra modelli ORM e schemi Pydantic."""

from __future__ import annotations

import enum


class ConsultationStato(str, enum.Enum):
    """Stato della pipeline di un colloquio / voce di diario."""

    BOZZA = "BOZZA"
    CARICATO = "CARICATO"
    TRASCRITTO = "TRASCRITTO"
    ELABORATO = "ELABORATO"
    CONFERMATO = "CONFERMATO"
    ERRORE = "ERRORE"
