"""Invio email transazionali (SMTP). Fail-soft: logga e non solleva in produzione tipica."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

from flask import current_app

logger = logging.getLogger(__name__)


class EmailServiceError(Exception):
    """Errore invio email."""


def _cfg(key: str, default: str = "") -> str:
    return str(current_app.config.get(key, default) or "").strip()


def is_email_configured() -> bool:
    return bool(_cfg("MAIL_SERVER") and _cfg("MAIL_FROM"))


def send_email(
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> bool:
    """Invia un'email. Ritorna True se inviata, False se SMTP non configurato.

    In TESTING non invia realmente (log only) e ritorna True.
    """
    to = (to or "").strip()
    if not to:
        raise EmailServiceError("Destinatario email mancante")

    if current_app.config.get("TESTING"):
        logger.info("EMAIL[test] to=%s subject=%s", to, subject)
        current_app.config.setdefault("_TEST_EMAILS", []).append(
            {"to": to, "subject": subject, "body": body_text}
        )
        return True

    if not is_email_configured():
        logger.warning(
            "SMTP non configurato: email non inviata to=%s subject=%s", to, subject
        )
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _cfg("MAIL_FROM")
    msg["To"] = to
    reply_to = _cfg("MAIL_REPLY_TO")
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    host = _cfg("MAIL_SERVER")
    port = int(current_app.config.get("MAIL_PORT") or 587)
    use_tls = bool(current_app.config.get("MAIL_USE_TLS", True))
    use_ssl = bool(current_app.config.get("MAIL_USE_SSL", False))
    username = _cfg("MAIL_USERNAME")
    password = _cfg("MAIL_PASSWORD")
    timeout = float(current_app.config.get("MAIL_TIMEOUT_SEC") or 20)

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=timeout) as smtp:
                if username:
                    smtp.login(username, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as smtp:
                if use_tls:
                    smtp.starttls()
                if username:
                    smtp.login(username, password)
                smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Invio email fallito to=%s: %s", to, exc)
        raise EmailServiceError("Invio email non riuscito") from exc

    logger.info("Email inviata to=%s subject=%s", to, subject)
    return True
