"""Primo accesso paziente: invito sicuro + attivazione password."""

from __future__ import annotations

import logging
import secrets
from typing import Optional

from flask import current_app, url_for
from werkzeug.security import generate_password_hash

from app.models.models import AuthSecureToken, Patient, db
from app.services.email_service import EmailServiceError, send_email
from app.services.licensing_service import assert_within_plan_limit
from app.services import secure_token_service as tokens

logger = logging.getLogger(__name__)

ACCOUNT_INVITED = "invited"
ACCOUNT_ACTIVE = "active"
ACCOUNT_DISABLED = "disabled"

VALID_ACCOUNT_STATUSES = frozenset(
    {ACCOUNT_INVITED, ACCOUNT_ACTIVE, ACCOUNT_DISABLED}
)


class PatientInviteError(Exception):
    def __init__(self, message: str, *, code: str = "invite_error"):
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


def activation_url(raw_token: str) -> str:
    """Link HTTPS fallback (apre app via deep link o form web)."""
    from urllib.parse import quote

    base = _public_base_url()
    path = f"/activate-account?token={quote(raw_token, safe='')}"
    return f"{base}{path}" if base else path


def activation_app_url(raw_token: str) -> str:
    """Custom scheme per aprire direttamente l'app Flutter."""
    from urllib.parse import quote

    return f"mynutriapp://activate-account?token={quote(raw_token, safe='')}"


def create_patient_with_invite(
    *,
    nome: str,
    cognome: str,
    telefono: str,
    email: str,
    sesso: str,
    data_nascita,
    altezza_cm,
    peso_iniziale,
    nutrizionista_id: int,
    consenso_privacy: bool = True,
    consenso_marketing: bool = False,
) -> Patient:
    """Crea paziente senza password definitiva: stato invited + email di invito."""
    from app.services.gdpr_service import apply_consents

    email_n = (email or "").strip().lower()
    if not email_n or "@" not in email_n:
        raise PatientInviteError("Email obbligatoria per l'invito", code="email_required")

    assert_within_plan_limit(int(nutrizionista_id))

    patient = Patient(
        nome=(nome or "").strip(),
        cognome=(cognome or "").strip(),
        telefono=(telefono or "").strip(),
        email=email_n,
        sesso=sesso or None,
        data_nascita=data_nascita,
        altezza_cm=altezza_cm,
        peso_iniziale=peso_iniziale,
        password_hash=generate_password_hash(secrets.token_urlsafe(32)),
        stato_cliente="attivo",
        account_status=ACCOUNT_INVITED,
        token_version=0,
        nutrizionista_id=int(nutrizionista_id),
    )
    apply_consents(
        patient,
        consenso_privacy=bool(consenso_privacy),
        consenso_marketing=bool(consenso_marketing),
    )
    db.session.add(patient)
    db.session.flush()
    send_invite_email(patient)
    return patient


def send_invite_email(patient: Patient) -> str:
    """Genera token invito e invia email. Ritorna il raw token (utile nei test)."""
    if not patient.email:
        raise PatientInviteError("Il paziente non ha un'email", code="email_required")

    patient.account_status = ACCOUNT_INVITED
    raw, _row = tokens.issue_token(
        AuthSecureToken.PURPOSE_PATIENT_INVITE, patient.id
    )
    link = activation_url(raw)
    app_link = activation_app_url(raw)
    studio = ""
    if patient.nutrizionista is not None:
        studio = (
            getattr(patient.nutrizionista, "studio_nome", None)
            or f"{patient.nutrizionista.nome} {patient.nutrizionista.cognome}".strip()
        )
    subject = "Attiva il tuo account MyNutriApp"
    body = (
        f"Ciao {patient.nome},\n\n"
        f"{('Il tuo nutrizionista presso ' + studio) if studio else 'Il tuo nutrizionista'} "
        f"ti ha invitato su MyNutriApp.\n\n"
        f"Crea la tua password aprendo questo link (scadenza inclusa):\n{link}\n\n"
        f"Se hai l'app installata puoi anche usare:\n{app_link}\n\n"
        f"Se non ti aspetti questa email, puoi ignorarla.\n"
    )
    try:
        send_email(to=patient.email, subject=subject, body_text=body)
    except EmailServiceError as exc:
        logger.warning("Invito creato ma email non inviata patient=%s: %s", patient.id, exc)
    db.session.flush()
    return raw


def resend_invite(patient: Patient) -> str:
    if getattr(patient, "account_status", None) == ACCOUNT_ACTIVE:
        raise PatientInviteError(
            "L'account è già attivo: usa il recupero password",
            code="already_active",
        )
    # invited o disabled → nuovo invito (disabilitati da prenotazione pubblica)
    return send_invite_email(patient)


def activate_account(raw_token: str, password: str, password_confirm: str) -> Patient:
    password = password or ""
    password_confirm = password_confirm or ""
    if len(password) < 8:
        raise PatientInviteError("Password minimo 8 caratteri", code="weak_password")
    if password != password_confirm:
        raise PatientInviteError("Le password non coincidono", code="password_mismatch")

    row = tokens.consume_token(AuthSecureToken.PURPOSE_PATIENT_INVITE, raw_token)
    if row is None:
        raise PatientInviteError(
            "Link non valido o scaduto", code="invalid_token"
        )

    patient = db.session.get(Patient, row.subject_id)
    if patient is None:
        raise PatientInviteError("Link non valido o scaduto", code="invalid_token")
    if getattr(patient, "account_status", None) == ACCOUNT_DISABLED:
        raise PatientInviteError("Account disabilitato", code="account_disabled")

    patient.password_hash = generate_password_hash(password)
    patient.account_status = ACCOUNT_ACTIVE
    patient.token_version = int(getattr(patient, "token_version", 0) or 0) + 1
    if getattr(patient, "stato_cliente", None) == "provvisorio":
        patient.stato_cliente = "attivo"
    db.session.flush()
    return patient


def patient_can_login(patient: Patient) -> bool:
    status = getattr(patient, "account_status", None) or ACCOUNT_ACTIVE
    if status == ACCOUNT_DISABLED:
        return False
    if status == ACCOUNT_INVITED:
        return False
    stato = getattr(patient, "stato_cliente", None) or "attivo"
    return stato == "attivo"
