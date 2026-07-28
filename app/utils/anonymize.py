"""Anonimizzazione identificativi paziente prima dell'invio a LLM esterni."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.models.models import Patient

PLACEHOLDER = "[PAZIENTE]"


@dataclass
class AnonymizationMap:
    """Mappa locale placeholder → valore originale (mai inviata all'API)."""

    originals: list[str] = field(default_factory=list)
    display_name: str = ""

    def restore_text(self, text: str) -> str:
        if not text or PLACEHOLDER not in text:
            return text
        replacement = self.display_name or (self.originals[0] if self.originals else PLACEHOLDER)
        return text.replace(PLACEHOLDER, replacement)


def _norm(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def build_identifier_list(patient: Patient) -> list[str]:
    """Raccoglie identificativi diretti da sostituire (più lunghi prima)."""
    nome = _norm(patient.nome)
    cognome = _norm(patient.cognome)
    email = _norm(getattr(patient, "email", None))
    telefono = _norm(patient.telefono)

    candidates: list[str] = []
    if nome and cognome:
        candidates.append(f"{nome} {cognome}")
        candidates.append(f"{cognome} {nome}")
    if cognome:
        candidates.append(cognome)
    if nome:
        candidates.append(nome)
    if email:
        candidates.append(email)
    if telefono:
        candidates.append(telefono)
        digits = re.sub(r"\D+", "", telefono)
        if len(digits) >= 8:
            candidates.append(digits)

    # dedup preservando ordine, casefold per confronto
    seen: set[str] = set()
    ordered: list[str] = []
    for item in candidates:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    # più lunghi prima per evitare sostituzioni parziali
    ordered.sort(key=len, reverse=True)
    return ordered


def anonymize_text(text: str, patient: Patient) -> tuple[str, AnonymizationMap]:
    """Sostituisce nome/cognome/telefono/email con ``[PAZIENTE]``."""
    mapping = AnonymizationMap(
        display_name=" ".join(
            p for p in (_norm(patient.nome), _norm(patient.cognome)) if p
        ).strip()
    )
    if not text:
        return text, mapping

    result = text
    for ident in build_identifier_list(patient):
        mapping.originals.append(ident)
        pattern = re.compile(re.escape(ident), re.IGNORECASE)
        result = pattern.sub(PLACEHOLDER, result)
    # collassa placeholder ripetuti adiacenti
    result = re.sub(
        rf"(?:{re.escape(PLACEHOLDER)}\s*){{2,}}",
        PLACEHOLDER + " ",
        result,
    ).strip()
    return result, mapping


def deanonymize_structure(data: Any, mapping: AnonymizationMap) -> Any:
    """Ripristina i placeholder nel JSON validato (solo lato server)."""
    if isinstance(data, str):
        return mapping.restore_text(data)
    if isinstance(data, list):
        return [deanonymize_structure(x, mapping) for x in data]
    if isinstance(data, dict):
        return {k: deanonymize_structure(v, mapping) for k, v in data.items()}
    return data
