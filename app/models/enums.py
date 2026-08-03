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


class UtenteRuolo(str, enum.Enum):
    """Ruolo operatore in tabella utente (multi-tenant)."""

    SUPER_ADMIN = "super_admin"
    NUTRIZIONISTA = "nutrizionista"
