"""Schemi Pydantic (request/response) per il dominio Diario del paziente."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import ConsultationStato


# ---------------------------------------------------------------------------
# Utente
# ---------------------------------------------------------------------------


class UtenteBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=100)
    cognome: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    telefono: Optional[str] = Field(None, max_length=20)
    attivo: bool = True


class UtenteCreate(UtenteBase):
    pass


class UtenteUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=1, max_length=100)
    cognome: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    telefono: Optional[str] = Field(None, max_length=20)
    attivo: Optional[bool] = None


class UtenteResponse(UtenteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creato_il: datetime
    aggiornato_il: datetime


# ---------------------------------------------------------------------------
# Patient (tabella patients)
# ---------------------------------------------------------------------------


class PatientBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=100)
    cognome: str = Field(..., min_length=1, max_length=100)
    data_nascita: Optional[date] = None
    email: Optional[EmailStr] = None
    telefono: str = Field(..., min_length=5, max_length=20)
    nutrizionista_id: Optional[int] = None
    consenso_registrazione: bool = False
    consenso_ai: bool = False


class PatientCreate(PatientBase):
    password: str = Field(..., min_length=8)


class PatientUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=1, max_length=100)
    cognome: Optional[str] = Field(None, min_length=1, max_length=100)
    data_nascita: Optional[date] = None
    email: Optional[EmailStr] = None
    telefono: Optional[str] = Field(None, min_length=5, max_length=20)
    nutrizionista_id: Optional[int] = None
    consenso_registrazione: Optional[bool] = None
    consenso_ai: Optional[bool] = None


class PatientResponse(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    consenso_aggiornato_il: Optional[datetime] = None
    creato_il: Optional[datetime] = None
    aggiornato_il: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Consultation
# ---------------------------------------------------------------------------


class ConsultationBase(BaseModel):
    patient_id: int
    nutrizionista_id: int
    data_colloquio: datetime
    stato: ConsultationStato = ConsultationStato.BOZZA
    note_manuali: Optional[str] = None


class ConsultationCreate(ConsultationBase):
    pass


class ConsultationUpdate(BaseModel):
    data_colloquio: Optional[datetime] = None
    stato: Optional[ConsultationStato] = None
    note_manuali: Optional[str] = None
    nutrizionista_id: Optional[int] = None


class ConsultationResponse(ConsultationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    errore_pipeline: Optional[str] = None
    creato_il: datetime
    aggiornato_il: datetime


# ---------------------------------------------------------------------------
# AudioRecording
# ---------------------------------------------------------------------------


class AudioRecordingBase(BaseModel):
    consultation_id: int
    path_file: str = Field(..., max_length=512)
    nome_originale: str = Field(..., max_length=255)
    mime_type: str = Field(..., max_length=100)
    dimensione_byte: int = Field(..., ge=0)
    durata_sec: Optional[float] = Field(None, ge=0)
    checksum_sha256: str = Field(..., min_length=64, max_length=64)
    cifrato: bool = False


class AudioRecordingCreate(AudioRecordingBase):
    pass


class AudioRecordingUpdate(BaseModel):
    path_file: Optional[str] = Field(None, max_length=512)
    durata_sec: Optional[float] = Field(None, ge=0)
    cifrato: Optional[bool] = None
    cancellato_il: Optional[datetime] = None


class AudioRecordingResponse(AudioRecordingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cancellato_il: Optional[datetime] = None
    creato_il: datetime


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------


class TranscriptBase(BaseModel):
    consultation_id: int
    testo: str
    lingua: str = Field(default="it", max_length=16)
    provider: str = Field(..., max_length=64)
    modello: str = Field(..., max_length=128)
    durata_elaborazione_sec: Optional[float] = Field(None, ge=0)


class TranscriptCreate(TranscriptBase):
    pass


class TranscriptUpdate(BaseModel):
    testo: Optional[str] = None
    lingua: Optional[str] = Field(None, max_length=16)
    provider: Optional[str] = Field(None, max_length=64)
    modello: Optional[str] = Field(None, max_length=128)
    durata_elaborazione_sec: Optional[float] = Field(None, ge=0)


class TranscriptResponse(TranscriptBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creato_il: datetime


# ---------------------------------------------------------------------------
# DiaryEntry
# ---------------------------------------------------------------------------


class DiaryEntryBase(BaseModel):
    consultation_id: int
    patient_id: int
    contenuto_json: dict[str, Any]
    riassunto_testo: Optional[str] = None
    modello_usato: str = Field(..., max_length=128)
    revisionato_da: Optional[int] = None
    revisionato_il: Optional[datetime] = None
    modificato_manualmente: bool = False


class DiaryEntryCreate(DiaryEntryBase):
    pass


class DiaryEntryUpdate(BaseModel):
    contenuto_json: Optional[dict[str, Any]] = None
    riassunto_testo: Optional[str] = None
    modello_usato: Optional[str] = Field(None, max_length=128)
    revisionato_da: Optional[int] = None
    revisionato_il: Optional[datetime] = None
    modificato_manualmente: Optional[bool] = None


class DiaryEntryResponse(DiaryEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creato_il: datetime
    aggiornato_il: datetime
    # Flag frontend: bozza vs storico validato
    confermato: bool = False
    da_revisionare: bool = True
    valido_storico: bool = False
