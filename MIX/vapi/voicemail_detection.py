# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""Detector deterministico di segreterie telefoniche italiane (offline, no LLM).

Riconosce i messaggi automatici degli operatori IT (TIM/Vodafone/WindTre/Iliad)
e i menu della casella vocale che, trascritti da Vapi come turni "cliente",
venivano scambiati per conversazioni reali → falso `callback_requested`.

Puro: nessuna dipendenza esterna, nessuna API, nessuno stato globale.
Deterministico: stesso input → stesso output. Pensato per essere testabile.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class VoicemailSignal:
    """Esito della rilevazione su un testo o su un transcript."""

    is_voicemail: bool
    matched_patterns: list[str] = field(default_factory=list)
    confidence: str = "low"  # low | medium | high
    reason: str = ""


# Frasi/menu inequivocabilmente automatici (casella vocale / operatore).
# Una sola occorrenza → segreteria ad alta confidenza.
_HIGH_PATTERNS: tuple[tuple[str, str], ...] = (
    ("segnale_acustico", r"(?:dopo|al)\s+il?\s*(?:segnale|bip)\s*(?:acustico)?"),
    ("segnale", r"\bsegnale acustico\b"),
    ("registra_messaggio", r"\bregistr\w+\s+(?:il|un|pure|adesso|ora|nuovamente)?\s*(?:tuo\s+|vostro\s+)?messaggio"),
    ("segreteria_telefonica", r"\bsegreteria telefonica\b"),
    ("servizio_segreteria", r"\bservizio di segreteria\b"),
    ("trasferimento_segreteria", r"\btrasfer\w+\s+alla segreteria\b"),
    ("casella_vocale", r"\bcasella vocale\b"),
    # "il cliente/numero/abbonato/utente/persona da lei chiamato/selezionato"
    ("numero_chiamato", r"\b(?:il|l['’\s]?|la)\s*(?:utente|abbonato|cliente|numero|persona)\s+(?:da lei\s+)?(?:chiamat\w+|selezionat\w+)"),
    ("non_raggiungibile", r"\bnon (?:e|è)\s+(?:al momento\s+)?raggiungibile\b"),
    ("momentaneamente_non_raggiungibile", r"\bmomentaneamente non raggiungibile\b"),
    # menu: "per inviare/ascoltare/riascoltare/cancellare/registrare ... il messaggio"
    ("menu_messaggio", r"\bper (?:inviare|ascoltare|riascoltare|cancellare|registrare)\b.*\bmessaggio\b"),
    ("menu_inviare", r"\bper inviare il messaggio\b"),
    ("menu_ascoltarlo", r"\bper (?:ri)?ascoltarl[oa]\b"),
    ("menu_registrare_nuovamente", r"\bper registrare nuovamente\b"),
    ("messaggio_registrato", r"\bmessaggio e stato (?:registrato|inviato|salvato)\b"),
    # Vapi a volte trascrive "il tuo messaggio (ha) raggiunto la lunghezza massima"
    ("lunghezza_massima", r"\braggiunto la lunghezza massima\b"),
    ("grazie_per_aver_chiamato", r"\bgrazie per aver\w*\s+chiamato\b"),
    ("lasciate_un_messaggio", r"\blasci(?:a|ate|are)\b\s+un messaggio\s+dopo\b"),
    ("momentaneamente_assente", r"\b(?:sono\s+)?momentaneamente assente\b"),
    ("benvenuto_segreteria", r"\bbenvenut\w+\s+(?:nella|alla)\s+segreteria\b"),
    ("non_posso_rispondere", r"\b(?:al momento\s+|in questo momento\s+)?non posso rispondere\b"),
    ("non_disponibile_rispondere", r"\bnon (?:sono|e|è)\s+disponibile\s+a rispondere\b"),
)

# Indizi più deboli (menu DTMF, "lascia un messaggio" generico).
# Da soli non bastano: servono ≥2 indizi medium nello stesso transcript.
_MEDIUM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("dtmf_digita", r"\b(?:digit[ai]|digiti|prema|premi|premere)\s+(?:il tasto\s+)?(?:uno|due|tre|quattro|cinque|sei|sette|otto|nove|zero|[0-9])\b"),
    ("premere_tasto", r"\bpremere il tasto\b"),
    ("lascia_messaggio", r"\blasci(?:a|ate|are)\b\s+un messaggio\b"),
)

# Se il turno cita un canale "umano" (WhatsApp/email/SMS), NON è una segreteria:
# è una persona che chiede di essere ricontattata altrove.
_HUMAN_CHANNEL_HINT = re.compile(
    r"\b(whats?app|wapp|email|e-?mail|posta elettronica|sms|telegram|messaggino)\b",
    re.IGNORECASE,
)

_HIGH_RE = tuple((name, re.compile(p, re.IGNORECASE)) for name, p in _HIGH_PATTERNS)
_MEDIUM_RE = tuple((name, re.compile(p, re.IGNORECASE)) for name, p in _MEDIUM_PATTERNS)


def _normalize(text: str) -> str:
    """Lowercase, accenti rimossi, punteggiatura→spazio, spazi compattati.

    Mantiene apostrofi-spazio per i pattern; rende il match robusto a varianti.
    """
    s = str(text or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w'’\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def detect_voicemail(text: str) -> VoicemailSignal:
    """Rileva segreteria su un singolo turno/testo.

    high  = almeno una frase inequivocabile da operatore/casella vocale.
    medium= un solo indizio debole (menu DTMF / "lascia un messaggio").
    low   = nessun segnale (is_voicemail=False).
    """
    raw = str(text or "")
    norm = _normalize(raw)
    if not norm:
        return VoicemailSignal(False, [], "low", "empty")

    high_hits = [name for name, rx in _HIGH_RE if rx.search(norm)]
    if high_hits:
        return VoicemailSignal(True, high_hits, "high", "high_confidence_phrase")

    human_channel = bool(_HUMAN_CHANNEL_HINT.search(raw))
    medium_hits = [name for name, rx in _MEDIUM_RE if rx.search(norm)]
    if medium_hits and not human_channel:
        # Un singolo indizio debole: segnalato come medium ma is_voicemail=True
        # solo se non c'è un riferimento a canale umano (WhatsApp/email/SMS).
        return VoicemailSignal(True, medium_hits, "medium", "weak_signal")
    if medium_hits and human_channel:
        return VoicemailSignal(False, [], "low", "human_channel_override")

    return VoicemailSignal(False, [], "low", "no_signal")


def is_voicemail_text(text: str) -> bool:
    """Comodo bool per il singolo turno (high o medium)."""
    return detect_voicemail(text).is_voicemail


def transcript_is_voicemail(texts: Iterable[str]) -> VoicemailSignal:
    """Decisione a livello di chiamata sui turni (tipicamente del cliente).

    is_voicemail = almeno un turno high, OPPURE ≥2 turni medium distinti.
    Più conservativo del singolo turno per evitare falsi positivi su persone reali.
    """
    high_all: list[str] = []
    medium_turns = 0
    medium_all: list[str] = []
    for t in texts or []:
        sig = detect_voicemail(t)
        if sig.confidence == "high":
            high_all.extend(sig.matched_patterns)
        elif sig.confidence == "medium":
            medium_turns += 1
            medium_all.extend(sig.matched_patterns)
    if high_all:
        return VoicemailSignal(True, sorted(set(high_all)), "high", "high_confidence_phrase")
    if medium_turns >= 2:
        return VoicemailSignal(True, sorted(set(medium_all)), "medium", "multiple_weak_signals")
    if medium_turns == 1:
        return VoicemailSignal(False, sorted(set(medium_all)), "low", "single_weak_signal")
    return VoicemailSignal(False, [], "low", "no_signal")


__all__ = [
    "VoicemailSignal",
    "detect_voicemail",
    "is_voicemail_text",
    "transcript_is_voicemail",
]
