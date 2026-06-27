# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""Policy outbound Vapi: niente conversazione se il cliente non risponde."""
from __future__ import annotations

import os
from typing import Any


def outbound_start_speaking_wait_seconds() -> float:
    raw = (os.getenv("VAPI_OUTBOUND_START_SPEAKING_WAIT_S") or "").strip()
    if raw:
        try:
            return max(0.0, min(10.0, float(raw)))
        except ValueError:
            pass
    return _DEFAULT_START_SPEAKING_WAIT_S

# Squillo massimo prima di no-answer (Twilio transport su Vapi; +5s buffer lato provider).
_DEFAULT_RING_TIMEOUT_S = 20
# Silenzio utente dopo che l'assistente ha parlato (Gloria: chiusura rapida).
_DEFAULT_SILENCE_TIMEOUT_S = 15
# Sara: attende risposta al firstMessage / domande — non riagganciare prima di 2,5 min.
_DEFAULT_SILENCE_TIMEOUT_SARA_S = 150
# Secondi di attesa dopo answer prima che l'assistente inizi a parlare (outbound).
_DEFAULT_START_SPEAKING_WAIT_S = 3.0
# Pausa finale pipeline prima che l'assistente parli dopo l'utente (max 2s).
_DEFAULT_RESPONSE_WAIT_S = 0.4
_MAX_RESPONSE_WAIT_S = 2.0


def response_wait_seconds() -> float:
    """Pausa massima (secondi) tra fine turno utente e inizio risposta assistente."""
    raw = (os.getenv("VAPI_RESPONSE_WAIT_SECONDS") or "").strip()
    if raw:
        try:
            return max(0.0, min(_MAX_RESPONSE_WAIT_S, float(raw)))
        except ValueError:
            pass
    return _DEFAULT_RESPONSE_WAIT_S


def build_start_speaking_plan(*, wait_seconds: float | None = None) -> dict[str, Any]:
    """Piano risposta Vapi: endpointing italiano + waitSeconds capped a 2s."""
    ws = response_wait_seconds() if wait_seconds is None else float(wait_seconds)
    ws = max(0.0, min(_MAX_RESPONSE_WAIT_S, ws))
    no_punct = min(0.8, ws)
    return {
        "waitSeconds": ws,
        "transcriptionEndpointingPlan": {
            "onPunctuationSeconds": 0.05,
            "onNoPunctuationSeconds": no_punct,
            "onNumberSeconds": min(0.35, ws),
        },
    }


def outbound_ring_timeout_seconds() -> int:
    raw = (os.getenv("VAPI_OUTBOUND_RING_TIMEOUT_SECONDS") or "").strip()
    if raw:
        try:
            return max(10, min(60, int(raw)))
        except ValueError:
            pass
    return _DEFAULT_RING_TIMEOUT_S


def outbound_silence_timeout_seconds(agent_key: str | None = None) -> int:
    ak = str(agent_key or "").strip().lower()
    if ak == "sara":
        raw = (
            os.getenv("VAPI_OUTBOUND_SILENCE_TIMEOUT_SECONDS_SARA")
            or os.getenv("VAPI_OUTBOUND_SILENCE_TIMEOUT_SECONDS")
            or ""
        ).strip()
        default = _DEFAULT_SILENCE_TIMEOUT_SARA_S
        cap = 600
    else:
        raw = (os.getenv("VAPI_OUTBOUND_SILENCE_TIMEOUT_SECONDS") or "").strip()
        default = _DEFAULT_SILENCE_TIMEOUT_S
        cap = 120
    if raw:
        try:
            return max(8, min(cap, int(raw)))
        except ValueError:
            pass
    return default


_SIP_UNREACHABLE_MARKERS = (
    "sip-480",
    "480-temporarily-unavailable",
    "temporarily-unavailable",
)


def is_unreachable_sip_ended_reason(ended_reason: str) -> bool:
    """True se la chiamata outbound è fallita perché il destinatario non era raggiungibile (SIP 480)."""
    key = (ended_reason or "").strip().lower()
    if not key:
        return False
    return any(marker in key for marker in _SIP_UNREACHABLE_MARKERS)


def is_voicemail_ended_reason(ended_reason: str) -> bool:
    """True se Vapi ha chiuso per segreteria / answering machine."""
    key = (ended_reason or "").strip().lower()
    if not key:
        return False
    if key == "voicemail" or "voicemail" in key:
        return True
    return key in {
        "machine-detected",
        "answering-machine",
        "answering-machine-detected",
        "machine-detected-beep",
    }


def voicemail_detection_config() -> dict[str, Any]:
    """Rileva segreteria il prima possibile; senza voicemailMessage Vapi riaggancia subito.

    startAtSeconds=0: controllo immediato appena la chiamata è risposta.
    frequencySeconds=2.5: minimo consentito da Vapi.
    maxRetries=8: copre ~20 secondi di tentativi (0s, 2.5s, 5s … 17.5s).
    beepMaxAwaitSeconds=0: nessun messaggio da lasciare → riaggancia senza parlare.
    """
    return {
        "provider": "vapi",
        "backoffPlan": {
            "startAtSeconds": 0,
            "frequencySeconds": 2.5,
            "maxRetries": 8,
        },
        "beepMaxAwaitSeconds": 0,
    }


# Sara: evita spezzature TTS su virgola/punto nel pitch finale (stall su "profilandolo… infatti").
SARA_VOICE_CHUNK_PLAN: dict[str, Any] = {
    "enabled": True,
    "minCharacters": 80,
    "punctuationBoundaries": ["?"],
}


def apply_outbound_call_policy(
    overrides: dict[str, Any] | None,
    *,
    agent_key: str | None = None,
) -> dict[str, Any]:
    """Imposta override per non tenere la linea aperta senza risposta umana."""
    out = dict(overrides or {})
    ring_s = outbound_ring_timeout_seconds()
    silence_s = outbound_silence_timeout_seconds(agent_key)

    # Pausa iniziale outbound: SSML nel firstMessage (client). Qui solo timing risposta.
    out.setdefault("firstMessageMode", "assistant-speaks-first")
    out["startSpeakingPlan"] = build_start_speaking_plan()
    out.setdefault("voicemailDetection", voicemail_detection_config())
    out["silenceTimeoutSeconds"] = silence_s
    # Nessun voicemailMessage → riaggancia alla segreteria senza messaggio.

    transport = out.get("transportConfigurations")
    ring_cfg = {"provider": "twilio", "timeout": ring_s}
    if isinstance(transport, list):
        merged = False
        for item in transport:
            if isinstance(item, dict) and str(item.get("provider") or "").lower() == "twilio":
                item.setdefault("timeout", ring_s)
                merged = True
                break
        if not merged:
            transport.append(ring_cfg)
        out["transportConfigurations"] = transport
    else:
        out["transportConfigurations"] = [ring_cfg]

    return out
