"""Estrazione diario strutturato via OpenAI Chat Completions API."""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.config.config import Config
from app.schemas.diary_extraction import DiaryExtractionSchema

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Sei un assistente che estrae informazioni da trascrizioni di colloqui
tra nutrizionista e paziente. Il tuo unico output deve essere un oggetto JSON valido
che rispetta ESATTAMENTE questo schema (nessun altro campo):

{
  "peso_kg": number | null,
  "misure": {
    "vita_cm": number | null,
    "fianchi_cm": number | null,
    "massa_grassa_pct": number | null
  },
  "aderenza_piano": "alta" | "media" | "bassa" | "non_rilevata",
  "sintomi_riportati": [string],
  "difficolta_segnalate": [string],
  "abitudini_alimentari": [string],
  "attivita_fisica": string | null,
  "obiettivi_concordati": [string],
  "modifiche_al_piano": [string],
  "note_cliniche": string | null,
  "prossimo_controllo": string | null,
  "punti_colloquio": [
    {"tema": string, "dettaglio": string}
  ],
  "riassunto": string
}

REGOLE OBBLIGATORIE:
1. Rispondi SOLO con JSON valido. Nessun preambolo, nessuna spiegazione, nessun markdown,
   nessun code fence (niente ```).
2. NON inventare valori. Se un dato non è esplicitamente presente nella trascrizione,
   usa null per gli scalari e [] per le liste. "aderenza_piano" = "non_rilevata" se non detta.
3. NON formulare diagnosi, prognosi o prescrizioni. Registra solo ciò che è stato detto
   nel colloquio, senza giudizi clinici aggiuntivi.
4. "riassunto" deve essere un breve riassunto fattuale di ciò che emerge dalla trascrizione
   (obbligatorio, non vuoto).
5. Il paziente è indicato come [PAZIENTE] nel testo: non inventare il nome reale.
6. Scansiona TUTTA la trascrizione: i colloqui toccano più temi in punti diversi.
   Compila i campi tematici (misure, alimentazione, attività, sintomi, piano, follow-up)
   e in "punti_colloquio" elenca i temi distinti emersi, in ordine cronologico di
   comparsa. Ogni punto ha "tema" (etichetta breve, es. "Attività fisica", "Dolori",
   "Istruzioni diario") e "dettaglio" (1-3 frasi fattuali su ciò che è stato detto).
   Se non emergono temi chiari, usa [].
"""

CORRECTION_PROMPT = """La risposta precedente NON era JSON valido rispetto allo schema richiesto.
Rispondi di nuovo con UN SOLO oggetto JSON valido, senza markdown e senza testo extra.
Errori di validazione: {errors}
"""


class DiaryExtractionError(Exception):
    """Errore permanente di estrazione (non salvare JSON parziale)."""


def redact_secrets(message: str) -> str:
    """Rimuove eventuali segreti da messaggi di errore / log."""
    if not message:
        return message
    redacted = message
    key = (Config.OPENAI_API_KEY or "").strip()
    if key:
        redacted = redacted.replace(key, "[REDACTED]")
    redacted = re.sub(r"sk-[A-Za-z0-9\-_]{20,}", "[REDACTED]", redacted)
    return redacted


def _strip_code_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_diary_json(raw: str) -> DiaryExtractionSchema:
    """Parse + validazione Pydantic; solleva DiaryExtractionError se invalido."""
    cleaned = _strip_code_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise DiaryExtractionError(f"JSON non valido: {exc}") from exc
    try:
        return DiaryExtractionSchema.model_validate(data)
    except Exception as exc:  # noqa: BLE001 — ValidationError
        raise DiaryExtractionError(f"Schema non valido: {exc}") from exc


class OpenAIDiaryExtractor:
    """Client OpenAI per estrazione diario."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else Config.OPENAI_API_KEY) or ""
        self.model = model or Config.OPENAI_DIARY_MODEL
        self.max_tokens = max_tokens if max_tokens is not None else Config.OPENAI_DIARY_MAX_TOKENS
        self.temperature = (
            temperature if temperature is not None else Config.OPENAI_DIARY_TEMPERATURE
        )
        self.base_url = (
            base_url if base_url is not None else (Config.OPENAI_BASE_URL or None)
        )
        self._client = None

    def _get_client(self):
        if not self.api_key:
            raise DiaryExtractionError("OPENAI_API_KEY non configurata")
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise DiaryExtractionError(
                    "Pacchetto openai non installato. pip install openai"
                ) from exc
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def _call(self, user_content: str) -> str:
        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
        except Exception as exc:  # noqa: BLE001
            raise DiaryExtractionError(
                redact_secrets(f"Chiamata OpenAI fallita: {exc}")
            ) from exc

        choice = (getattr(response, "choices", None) or [None])[0]
        message = getattr(choice, "message", None) if choice is not None else None
        raw = (getattr(message, "content", None) or "").strip()
        if not raw:
            raise DiaryExtractionError("Risposta OpenAI vuota")
        return raw

    def extract(self, anonymized_transcript: str) -> DiaryExtractionSchema:
        """Estrae e valida; un solo ritento di correzione se il parsing fallisce."""
        user_msg = (
            "Trascrizione del colloquio (identificativi già anonimizzati):\n\n"
            f"{anonymized_transcript}"
        )
        raw = self._call(user_msg)
        try:
            return parse_diary_json(raw)
        except DiaryExtractionError as first_err:
            logger.warning(
                "Parse diario fallito, ritento correzione: %s",
                redact_secrets(str(first_err)),
            )
            correction = CORRECTION_PROMPT.format(errors=str(first_err)[:800])
            raw2 = self._call(
                f"{user_msg}\n\n{correction}\n\nRisposta precedente da correggere:\n{raw[:4000]}"
            )
            try:
                return parse_diary_json(raw2)
            except DiaryExtractionError as second_err:
                raise DiaryExtractionError(
                    redact_secrets(
                        f"Estrazione fallita dopo correzione: {second_err}"
                    )
                ) from second_err
