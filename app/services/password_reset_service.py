"""Recupero password paziente (API) e nutrizionista (web)."""

from __future__ import annotations

import logging
from typing import Optional

from flask import current_app, url_for
from werkzeug.security import generate_password_hash

from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import AuthSecureToken, Patient, db
from app.services.email_service import EmailServiceError, send_email
from app.services import secure_token_service as tokens

logger = logging.getLogger(__name__)

GENERIC_OK_MESSAGE = (
    "Se l'indirizzo è registrato, riceverai a breve un'email con le istruzioni."
)


class PasswordResetError(Exception):
    def __init__(self, message: str, *, code: str = "reset_error"):
        super().__init__(message)
        self.message = message
        self.code = code


def _public_base_url() -> str:
    base = (current_app.config.get("APP_PUBLIC_URL") or "").rstrip("/")
    if base:
        return base
    try:
        return url_for("auth.login", _external=True).rsplit("/login", 1)[0]
    except Exception:  # noqa: BLE001
        return ""


def reset_url(raw_token: str, *, for_staff: bool = False) -> str:
    """Link reset: pazienti → query deep-link; staff → path token."""
    from urllib.parse import quote

    base = _public_base_url()
    if for_staff:
        path = f"/reset-password/{raw_token}"
    else:
        path = f"/reset-password?token={quote(raw_token, safe='')}"
    return f"{base}{path}" if base else path


def reset_app_url(raw_token: str) -> str:
    from urllib.parse import quote

    return f"mynutriapp://reset-password?token={quote(raw_token, safe='')}"


def find_patient_by_email(email: str) -> Optional[Patient]:
    email_n = (email or "").strip().lower()
    if not email_n:
        return None
    matches = [
        p
        for p in Patient.query.filter(Patient.email.isnot(None)).all()
        if (p.email or "").strip().lower() == email_n
    ]
    if len(matches) == 1:
        return matches[0]
    # Ambiguo multi-tenant: non rivelare; nessun invio
    return None if len(matches) != 1 else matches[0]


def find_utente_by_email(email: str) -> Optional[Utente]:
    email_n = (email or "").strip().lower()
    if not email_n:
        return None
    return Utente.query.filter(
        Utente.email == email_n,
        Utente.ruolo.in_(
            [UtenteRuolo.NUTRIZIONISTA.value, UtenteRuolo.SUPER_ADMIN.value]
        ),
        Utente.attivo.is_(True),
    ).first()


def request_patient_reset(email: str) -> str:
    """Avvia reset paziente. Sempre messaggio generico (non rivela esistenza)."""
    patient = find_patient_by_email(email)
    if patient is None:
        return GENERIC_OK_MESSAGE
    status = getattr(patient, "account_status", None) or "active"
    if status == "disabled":
        return GENERIC_OK_MESSAGE
    if status == "invited":
        # Meglio reinviare invito, ma non rivelare: invia comunque istruzioni invito
        try:
            from app.services.patient_invite_service import send_invite_email

            send_invite_email(patient)
            db.session.commit()
        except Exception:  # noqa: BLE001
            db.session.rollback()
        return GENERIC_OK_MESSAGE

    raw, _ = tokens.issue_token(AuthSecureToken.PURPOSE_PATIENT_RESET, patient.id)
    link = reset_url(raw, for_staff=False)
    app_link = reset_app_url(raw)
    body = (
        f"Ciao {patient.nome},\n\n"
        f"Abbiamo ricevuto una richiesta di reset password per MyNutriApp.\n\n"
        f"Imposta una nuova password da questo link (valido circa "
        f"{int(current_app.config.get('PASSWORD_RESET_TOKEN_EXPIRES_MINUTES') or 45)} minuti):\n"
        f"{link}\n\n"
        f"Se hai l'app installata puoi anche usare:\n{app_link}\n\n"
        f"Se non hai richiesto tu il reset, ignora questa email.\n"
    )
    try:
        send_email(
            to=patient.email,
            subject="Reset password MyNutriApp",
            body_text=body,
        )
    except EmailServiceError as exc:
        logger.warning("Reset token creato ma email fallita patient=%s: %s", patient.id, exc)
    db.session.commit()
    return GENERIC_OK_MESSAGE


def request_utente_reset(email: str) -> str:
    """Avvia reset nutrizionista/super_admin (web). Messaggio generico."""
    utente = find_utente_by_email(email)
    if utente is None or not utente.password_hash:
        return GENERIC_OK_MESSAGE
    if getattr(utente, "needs_password_setup", False):
        return GENERIC_OK_MESSAGE

    raw, _ = tokens.issue_token(AuthSecureToken.PURPOSE_UTENTE_RESET, utente.id)
    link = reset_url(raw, for_staff=True)
    body = (
        f"Ciao {utente.nome},\n\n"
        f"Reset password per l'area professionisti MyNutriApp.\n\n"
        f"Link (scadenza inclusa):\n{link}\n\n"
        f"Se non hai richiesto tu il reset, ignora questa email.\n"
    )
    try:
        send_email(
            to=utente.email,
            subject="Reset password MyNutriApp (professionisti)",
            body_text=body,
        )
    except EmailServiceError as exc:
        logger.warning("Reset token creato ma email fallita utente=%s: %s", utente.id, exc)
    db.session.commit()
    return GENERIC_OK_MESSAGE


def reset_patient_password(
    raw_token: str, password: str, password_confirm: str
) -> Patient:
    password = password or ""
    password_confirm = password_confirm or ""
    if len(password) < 8:
        raise PasswordResetError("Password minimo 8 caratteri", code="weak_password")
    if password != password_confirm:
        raise PasswordResetError("Le password non coincidono", code="password_mismatch")

    row = tokens.consume_token(AuthSecureToken.PURPOSE_PATIENT_RESET, raw_token)
    if row is None:
        raise PasswordResetError("Link non valido o scaduto", code="invalid_token")

    patient = db.session.get(Patient, row.subject_id)
    if patient is None:
        raise PasswordResetError("Link non valido o scaduto", code="invalid_token")

    patient.password_hash = generate_password_hash(password)
    patient.account_status = "active"
    patient.token_version = int(getattr(patient, "token_version", 0) or 0) + 1
    db.session.commit()
    return patient


def reset_utente_password(
    raw_token: str, password: str, password_confirm: str
) -> Utente:
    password = password or ""
    password_confirm = password_confirm or ""
    if len(password) < 8:
        raise PasswordResetError("Password minimo 8 caratteri", code="weak_password")
    if password != password_confirm:
        raise PasswordResetError("Le password non coincidono", code="password_mismatch")

    row = tokens.consume_token(AuthSecureToken.PURPOSE_UTENTE_RESET, raw_token)
    if row is None:
        raise PasswordResetError("Link non valido o scaduto", code="invalid_token")

    utente = db.session.get(Utente, row.subject_id)
    if utente is None:
        raise PasswordResetError("Link non valido o scaduto", code="invalid_token")

    utente.password_hash = generate_password_hash(password)
    utente.needs_password_setup = False
    db.session.commit()
    return utente
