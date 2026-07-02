"""
Servizio Vapi — Segretario AI inbound.

Gestisce la comunicazione con l'API Vapi (https://api.vapi.ai):
- lettura/aggiornamento dell'assistente (system prompt, primo messaggio, tools, webhook)
- lettura del numero di telefono inbound
- costruzione del payload dell'assistente a partire dalla SegretarioConfig
- verifica della firma dei webhook in arrivo

Usa `requests` (già presente fra le dipendenze del progetto).
"""

import hashlib
import hmac
import json
import logging

import requests

from app.config.config import Config

logger = logging.getLogger(__name__)

TIMEOUT = 30


# ============================================================
# 🔧 HELPER DI BASE
# ============================================================

def is_configured() -> bool:
    """True se le credenziali minime per usare Vapi sono presenti."""
    return bool(Config.VAPI_API_KEY and Config.VAPI_ASSISTANT_ID)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {Config.VAPI_API_KEY}",
        "Content-Type": "application/json",
    }


def webhook_url() -> str:
    """URL pubblico a cui Vapi invierà gli eventi (tool-calls, fine chiamata...)."""
    base = (Config.VAPI_PUBLIC_URL or "").rstrip("/")
    if not base:
        return ""
    return f"{base}/admin/segretario/webhook"


# ============================================================
# 📞 LETTURA RISORSE VAPI
# ============================================================

def get_assistant() -> dict | None:
    """GET /assistant/:id — ritorna la configurazione attuale dell'assistente."""
    if not is_configured():
        return None
    try:
        resp = requests.get(
            f"{Config.VAPI_BASE_URL}/assistant/{Config.VAPI_ASSISTANT_ID}",
            headers=_headers(),
            timeout=TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.error("Vapi GET assistant %s: %s", resp.status_code, resp.text[:300])
            return None
        return resp.json()
    except requests.RequestException as exc:
        logger.error("Vapi GET assistant errore rete: %s", exc)
        return None


def get_phone_number() -> dict | None:
    """GET /phone-number/:id — info sul numero inbound (numero E.164, provider...)."""
    if not (Config.VAPI_API_KEY and Config.VAPI_PHONE_NUMBER_ID):
        return None
    try:
        resp = requests.get(
            f"{Config.VAPI_BASE_URL}/phone-number/{Config.VAPI_PHONE_NUMBER_ID}",
            headers=_headers(),
            timeout=TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.error("Vapi GET phone-number %s: %s", resp.status_code, resp.text[:300])
            return None
        return resp.json()
    except requests.RequestException as exc:
        logger.error("Vapi GET phone-number errore rete: %s", exc)
        return None


# ============================================================
# 🛠️ DEFINIZIONE DEI TOOL (function calling)
# ============================================================

def build_tools() -> list[dict]:
    """Tool che l'AI può invocare durante la chiamata (gestiti dal nostro webhook)."""
    return [
        {
            "type": "function",
            "function": {
                "name": "verifica_disponibilita",
                "description": (
                    "Restituisce gli slot liberi e futuri per fissare un appuntamento "
                    "in studio. Usalo prima di proporre date al paziente."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "giorni": {
                            "type": "integer",
                            "description": "Quanti giorni in avanti cercare (default 30).",
                        }
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "prenota_appuntamento",
                "description": (
                    "Prenota un appuntamento in uno slot disponibile. Chiama prima "
                    "verifica_disponibilita e usa esattamente una delle date proposte."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data_ora": {
                            "type": "string",
                            "description": "Data e ora scelte nel formato 'YYYY-MM-DD HH:MM'.",
                        },
                        "nome": {
                            "type": "string",
                            "description": "Nome e cognome del paziente.",
                        },
                        "tipo": {
                            "type": "string",
                            "description": "Tipo appuntamento: check, rinnovo_dieta, rinnovo_allenamento, allenamento_1to1, altro.",
                        },
                        "note": {
                            "type": "string",
                            "description": "Motivo della chiamata o note utili al nutrizionista.",
                        },
                    },
                    "required": ["data_ora"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "lascia_messaggio",
                "description": (
                    "Registra una richiesta di richiamata o un messaggio per il "
                    "nutrizionista quando non è possibile risolvere durante la chiamata."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nome": {"type": "string", "description": "Nome del paziente."},
                        "messaggio": {
                            "type": "string",
                            "description": "Contenuto del messaggio o motivo della richiamata.",
                        },
                    },
                    "required": ["messaggio"],
                },
            },
        },
    ]


# ============================================================
# 🧠 SYSTEM PROMPT E PRIMO MESSAGGIO
# ============================================================

def default_first_message(config) -> str:
    nome = (getattr(config, "nome_assistente", None) or "Sara").strip()
    studio = (getattr(config, "nome_studio", None) or "lo studio").strip()
    if config and config.messaggio_benvenuto:
        return config.messaggio_benvenuto.strip()
    return (
        f"Studio {studio}, sono {nome}, l'assistente virtuale. "
        f"Il nutrizionista al momento non è disponibile: posso aiutarti io a "
        f"fissare un appuntamento o a lasciare un messaggio. Come posso aiutarti?"
    )


def build_system_prompt(config) -> str:
    nome = (getattr(config, "nome_assistente", None) or "Sara").strip()
    studio = (getattr(config, "nome_studio", None) or "lo studio nutrizionale").strip()
    extra = (config.istruzioni_ai or "").strip() if config else ""

    base = f"""Sei {nome}, la segretaria virtuale dello studio {studio}.
Rispondi alle telefonate dei pazienti quando il nutrizionista non è disponibile.

OBIETTIVI:
1. Fare customer care: rispondere con gentilezza a domande su orari, sede, servizi e percorsi.
2. Fissare appuntamenti usando SOLO gli slot realmente liberi.
3. Quando non puoi risolvere, raccogliere un messaggio per il nutrizionista.

REGOLE:
- Parla sempre in italiano, con tono cortese, caldo e professionale. Frasi brevi.
- Per fissare un appuntamento: chiama prima `verifica_disponibilita`, proponi al massimo
  2-3 date, poi conferma con `prenota_appuntamento` usando una data fra quelle proposte.
- Non inventare MAI orari o disponibilità: usa solo i risultati dei tool.
- Chiedi e ripeti nome e cognome per essere sicura dei dati.
- Non dare consigli medici o nutrizionali specifici: per quelli rimanda al nutrizionista.
- Se il paziente vuole parlare con una persona o ha un'urgenza, usa `lascia_messaggio`.
- Alla fine riepiloga brevemente cosa hai fatto (es. appuntamento fissato per...) e saluta.
"""
    if extra:
        base += f"\nISTRUZIONI AGGIUNTIVE DELLO STUDIO:\n{extra}\n"
    return base.strip()


# ============================================================
# 🚀 PUSH CONFIGURAZIONE SU VAPI
# ============================================================

def push_assistant_config(config) -> tuple[bool, str]:
    """Aggiorna l'assistente Vapi a partire dalla SegretarioConfig.

    Fa GET dell'assistente e MERGE per non sovrascrivere voce/model scelti in
    dashboard: aggiorna solo system prompt, primo messaggio, tools e webhook.
    Ritorna (ok, messaggio).
    """
    if not is_configured():
        return False, "Credenziali Vapi mancanti (VAPI_API_KEY / VAPI_ASSISTANT_ID)."

    current = get_assistant()
    if current is None:
        return False, "Impossibile leggere l'assistente da Vapi (verifica API key e Assistant ID)."

    # Conserva il model esistente, aggiornando solo messaggi di sistema e tools.
    model = dict(current.get("model") or {})
    if not model.get("provider"):
        model["provider"] = "openai"
    if not model.get("model"):
        model["model"] = "gpt-4o"

    messages = [m for m in (model.get("messages") or []) if m.get("role") != "system"]
    messages.insert(0, {"role": "system", "content": build_system_prompt(config)})
    model["messages"] = messages
    model["tools"] = build_tools()

    payload: dict = {
        "firstMessage": default_first_message(config),
        "model": model,
    }

    hook = webhook_url()
    if hook:
        server: dict = {"url": hook}
        if Config.VAPI_WEBHOOK_SECRET:
            server["secret"] = Config.VAPI_WEBHOOK_SECRET
        payload["server"] = server

    try:
        resp = requests.patch(
            f"{Config.VAPI_BASE_URL}/assistant/{Config.VAPI_ASSISTANT_ID}",
            headers=_headers(),
            data=json.dumps(payload),
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.error("Vapi PATCH assistant errore rete: %s", exc)
        return False, f"Errore di rete verso Vapi: {exc}"

    if resp.status_code >= 400:
        logger.error("Vapi PATCH assistant %s: %s", resp.status_code, resp.text[:400])
        return False, f"Vapi ha risposto {resp.status_code}: {resp.text[:200]}"

    # Assegna l'assistente + webhook anche al numero inbound, se configurato.
    if Config.VAPI_PHONE_NUMBER_ID:
        attach_assistant_to_number()

    return True, "Configurazione sincronizzata con Vapi."


def attach_assistant_to_number() -> tuple[bool, str]:
    """Collega l'assistente (e il webhook) al numero inbound su Vapi."""
    if not Config.VAPI_PHONE_NUMBER_ID:
        return False, "VAPI_PHONE_NUMBER_ID non configurato."

    payload: dict = {"assistantId": Config.VAPI_ASSISTANT_ID}
    hook = webhook_url()
    if hook:
        server = {"url": hook}
        if Config.VAPI_WEBHOOK_SECRET:
            server["secret"] = Config.VAPI_WEBHOOK_SECRET
        payload["server"] = server
    try:
        resp = requests.patch(
            f"{Config.VAPI_BASE_URL}/phone-number/{Config.VAPI_PHONE_NUMBER_ID}",
            headers=_headers(),
            data=json.dumps(payload),
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Vapi PATCH phone-number errore rete: %s", exc)
        return False, f"Errore di rete verso Vapi: {exc}"

    if resp.status_code >= 400:
        logger.warning("Vapi PATCH phone-number %s: %s", resp.status_code, resp.text[:300])
        return False, f"Vapi ha risposto {resp.status_code}."

    return True, "Assistente collegato al numero inbound."


def detach_assistant_from_number() -> tuple[bool, str]:
    """Scollega l'assistente dal numero inbound su Vapi."""
    if not Config.VAPI_PHONE_NUMBER_ID:
        return False, "VAPI_PHONE_NUMBER_ID non configurato."

    payload: dict = {"assistantId": None}
    try:
        resp = requests.patch(
            f"{Config.VAPI_BASE_URL}/phone-number/{Config.VAPI_PHONE_NUMBER_ID}",
            headers=_headers(),
            data=json.dumps(payload),
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Vapi PATCH phone-number (detach) errore rete: %s", exc)
        return False, f"Errore di rete verso Vapi: {exc}"

    if resp.status_code >= 400:
        logger.warning("Vapi PATCH phone-number detach %s: %s", resp.status_code, resp.text[:300])
        return False, f"Vapi ha risposto {resp.status_code}."

    return True, "Assistente scollegato dal numero inbound."


# ============================================================
# 🔐 VERIFICA FIRMA WEBHOOK
# ============================================================

def verify_webhook(headers, body: bytes) -> bool:
    """Verifica l'autenticità del webhook Vapi.

    Supporta sia il secret in chiaro (header `x-vapi-secret`) sia la firma
    HMAC-SHA256 (`x-vapi-signature`). Se nessun secret è configurato, accetta.
    """
    secret = Config.VAPI_WEBHOOK_SECRET
    if not secret:
        return True
    if not body:
        return False

    secret_header = ""
    signature_header = ""
    for k, v in headers.items():
        lk = k.lower()
        if lk == "x-vapi-secret":
            secret_header = (v or "").strip()
        elif lk == "x-vapi-signature":
            signature_header = (v or "").strip()
            if signature_header.lower().startswith("sha256="):
                signature_header = signature_header.split("=", 1)[1].strip()

    if secret_header and hmac.compare_digest(secret_header, secret):
        return True

    if signature_header:
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(digest, signature_header):
            return True
        if len(digest) == len(signature_header):
            return hmac.compare_digest(digest.lower(), signature_header.lower())

    return False
