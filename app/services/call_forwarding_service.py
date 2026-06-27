"""
Deviazione chiamate verso il numero Vapi inbound.

Il server non può attivare la deviazione sulla SIM del nutrizionista da solo:
invia una richiesta a un'automazione sul telefono (webhook generico o Pushcut)
che compone i codici USSD dell'operatore.

Codici GSM standard:
- Attiva deviazione incondizionata: **21*<numero>#
- Disattiva: ##21#
"""

import logging

import requests

from app.config.config import Config
from app.services import vapi_service

logger = logging.getLogger(__name__)

TIMEOUT = 20


def ussd_activate_code(target_e164: str) -> str:
    """Codice USSD per attivare la deviazione incondizionata."""
    num = (target_e164 or "").replace(" ", "").replace("-", "")
    if num and not num.startswith("+"):
        num = f"+{num}"
    return f"**21*{num}#"


def ussd_deactivate_code() -> str:
    return "##21#"


def get_forward_target() -> str:
    """Numero E.164 di destinazione (Vapi inbound)."""
    override = (Config.CALL_FORWARDING_TARGET or "").strip()
    if override:
        return override
    info = vapi_service.get_phone_number()
    if info:
        return (info.get("number") or info.get("phoneNumber") or "").strip()
    return ""


def is_remote_control_configured() -> bool:
    mode = (Config.CALL_FORWARDING_MODE or "webhook").strip().lower()
    if mode == "pushcut":
        return bool(
            Config.PUSHCUT_API_KEY
            and Config.PUSHCUT_NOTIF_ON
            and Config.PUSHCUT_NOTIF_OFF
        )
    if mode == "webhook":
        return bool(Config.CALL_FORWARDING_ON_URL and Config.CALL_FORWARDING_OFF_URL)
    return False


def provider_label() -> str:
    mode = (Config.CALL_FORWARDING_MODE or "webhook").strip().lower()
    if mode == "pushcut":
        return "Pushcut"
    if mode == "webhook":
        return "Webhook telefono"
    return mode or "—"


def _request_url(url: str) -> tuple[bool, str]:
    url = (url or "").strip()
    if not url:
        return False, "URL non configurato."

    headers = {}
    secret = (Config.CALL_FORWARDING_SECRET or "").strip()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"

    try:
        resp = requests.post(url, headers=headers, json={"source": "mynutriapp"}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Deviazione chiamate: errore rete verso %s: %s", url, exc)
        return False, f"Errore di rete verso l'automazione telefono: {exc}"

    if resp.status_code >= 400:
        logger.error("Deviazione chiamate: %s → %s", resp.status_code, resp.text[:300])
        return False, f"Automazione telefono ha risposto {resp.status_code}."

    return True, "Comando inviato al telefono."


def _trigger_pushcut(notification_name: str) -> tuple[bool, str]:
    name = (notification_name or "").strip()
    if not name:
        return False, "Nome notifica Pushcut mancante."

    url = f"https://api.pushcut.io/v1/notifications/{name}"
    headers = {"API-Key": Config.PUSHCUT_API_KEY}
    try:
        resp = requests.post(url, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Pushcut deviazione: errore rete: %s", exc)
        return False, f"Errore di rete verso Pushcut: {exc}"

    if resp.status_code >= 400:
        logger.error("Pushcut deviazione %s: %s", resp.status_code, resp.text[:300])
        return False, f"Pushcut ha risposto {resp.status_code}."

    return True, "Comando inviato tramite Pushcut."


def _trigger_remote(active: bool, target: str) -> tuple[bool, str]:
    mode = (Config.CALL_FORWARDING_MODE or "webhook").strip().lower()

    if mode == "pushcut":
        notif = Config.PUSHCUT_NOTIF_ON if active else Config.PUSHCUT_NOTIF_OFF
        ok, msg = _trigger_pushcut(notif)
    elif mode == "webhook":
        url = Config.CALL_FORWARDING_ON_URL if active else Config.CALL_FORWARDING_OFF_URL
        ok, msg = _request_url(url)
    else:
        return False, f"Modalità deviazione non supportata: {mode}."

    if not ok:
        return ok, msg

    code = ussd_activate_code(target) if active else ussd_deactivate_code()
    action = "attivata" if active else "disattivata"
    return True, f"Deviazione {action}. Sul telefono verrà composto: {code} ({msg})"


def set_forwarding(active: bool, config=None) -> tuple[bool, str]:
    """Attiva/disattiva deviazione remota e sincronizza Vapi."""
    target = get_forward_target()
    if active and not target:
        return False, "Numero Vapi inbound non disponibile: verifica VAPI_PHONE_NUMBER_ID."

    if not is_remote_control_configured():
        code = ussd_activate_code(target) if active else ussd_deactivate_code()
        return (
            False,
            "Automazione telefono non configurata nel .env. "
            f"Componi manualmente sul cellulare: {code}",
        )

    if not active and vapi_service.is_configured() and Config.VAPI_PHONE_NUMBER_ID:
        ok_detach, msg_detach = vapi_service.detach_assistant_from_number()
        if not ok_detach:
            return False, msg_detach

    ok, msg = _trigger_remote(active, target)
    if not ok:
        if not active and vapi_service.is_configured() and config:
            vapi_service.attach_assistant_to_number()
            vapi_service.push_assistant_config(config)
        return False, msg

    if active and vapi_service.is_configured():
        if config:
            sync_ok, sync_msg = vapi_service.push_assistant_config(config)
            if not sync_ok:
                return False, f"Deviazione attivata ma sync Vapi fallita: {sync_msg}"
        else:
            attach_ok, attach_msg = vapi_service.attach_assistant_to_number()
            if not attach_ok:
                return False, f"Deviazione attivata ma Vapi non collegato: {attach_msg}"

    return True, msg


def status_info(deviazione_attiva: bool) -> dict:
    target = get_forward_target()
    return {
        "attiva": deviazione_attiva,
        "target": target,
        "configured": is_remote_control_configured(),
        "provider": provider_label(),
        "ussd_on": ussd_activate_code(target) if target else "",
        "ussd_off": ussd_deactivate_code(),
    }
