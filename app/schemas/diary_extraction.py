"""Schema Pydantic del diario strutturato (output Claude)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


AderenzaPiano = Literal["alta", "media", "bassa", "non_rilevata"]


class MisureDiario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vita_cm: Optional[float] = None
    fianchi_cm: Optional[float] = None
    massa_grassa_pct: Optional[float] = None


class DiaryExtractionSchema(BaseModel):
    """JSON strutturato estratto dalla trascrizione del colloquio."""

    model_config = ConfigDict(extra="forbid")

    peso_kg: Optional[float] = None
    misure: MisureDiario = Field(default_factory=MisureDiario)
    aderenza_piano: AderenzaPiano = "non_rilevata"
    sintomi_riportati: list[str] = Field(default_factory=list)
    difficolta_segnalate: list[str] = Field(default_factory=list)
    abitudini_alimentari: list[str] = Field(default_factory=list)
    attivita_fisica: Optional[str] = None
    obiettivi_concordati: list[str] = Field(default_factory=list)
    modifiche_al_piano: list[str] = Field(default_factory=list)
    note_cliniche: Optional[str] = None
    prossimo_controllo: Optional[str] = None
    riassunto: str = Field(..., min_length=1)
