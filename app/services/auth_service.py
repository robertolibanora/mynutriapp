"""Autenticazione condivisa tra login web e API /api/v1."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional

from werkzeug.security import check_password_hash

from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import Patient
from app.services.utente_service import find_utente_by_phone
from app.utils.helpers import normalize_phone


class AuthStatus(str, Enum):
    OK_SUPER_ADMIN = "ok_super_admin"
    OK_NUTRIZIONISTA = "ok_nutrizionista"
    OK_ADMIN = "ok_admin"  # compat → trattato come super_admin
    OK_USER = "ok_user"
    INACTIVE = "inactive"
    INVALID = "invalid"
    AMBIGUOUS = "ambiguous"  # stesso telefono su più tenant, serve email


@dataclass(frozen=True)
class AuthResult:
    status: AuthStatus
    patient: Optional[Patient] = None
    utente: Optional[Utente] = None
    admin_name: Optional[str] = None
    telefono_normalized: str = ""


def _patients_matching_phone(telefono: str) -> List[Patient]:
    """Tutti i pazienti con lo stesso telefono (normalizzato)."""
    telefono = normalize_phone(telefono)
    matches: List[Patient] = []
    seen: set[int] = set()
    for candidate in Patient.query.filter(Patient.telefono.isnot(None)).all():
        if normalize_phone(candidate.telefono) != telefono:
            continue
        if candidate.id in seen:
            continue
        seen.add(candidate.id)
        matches.append(candidate)
    return matches


def find_patient_by_phone(
    telefono: str,
    email: Optional[str] = None,
) -> Optional[Patient]:
    """Lookup paziente per telefono; con multi-match richiede email (fail-closed)."""
    matches = _patients_matching_phone(telefono)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    email_n = (email or "").strip().lower()
    if not email_n:
        return None  # ambiguo senza email → fail-closed

    email_matches = [
        p for p in matches
        if p.email and p.email.strip().lower() == email_n
    ]
    if len(email_matches) == 1:
        return email_matches[0]
    return None


def phone_login_is_ambiguous(telefono: str) -> bool:
    """True se esistono più pazienti con lo stesso telefono."""
    return len(_patients_matching_phone(telefono)) > 1


def authenticate(
    telefono: str,
    password: str,
    email: Optional[str] = None,
) -> AuthResult:
    """
    Verifica credenziali (login da DB).

    1) utente attivo (super_admin / nutrizionista)
    2) paziente attivo (email obbligatoria se telefono ambiguo)
    """
    telefono_n = normalize_phone(telefono or "")
    password = password or ""

    utente = find_utente_by_phone(telefono_n)
    if utente and utente.password_hash and check_password_hash(utente.password_hash, password):
        if not utente.attivo:
            return AuthResult(
                status=AuthStatus.INACTIVE,
                utente=utente,
                telefono_normalized=telefono_n,
            )
        name = f"{utente.nome} {utente.cognome}".strip()
        if utente.ruolo == UtenteRuolo.SUPER_ADMIN.value:
            return AuthResult(
                status=AuthStatus.OK_SUPER_ADMIN,
                utente=utente,
                admin_name=name,
                telefono_normalized=telefono_n,
            )
        if utente.ruolo == UtenteRuolo.NUTRIZIONISTA.value:
            return AuthResult(
                status=AuthStatus.OK_NUTRIZIONISTA,
                utente=utente,
                admin_name=name,
                telefono_normalized=telefono_n,
            )

    matches = _patients_matching_phone(telefono_n)
    if len(matches) > 1 and not (email or "").strip():
        # Verifica se almeno una password matcherebbe (non rivelare dettagli)
        any_pwd = any(
            check_password_hash(p.password_hash, password) for p in matches
        )
        if any_pwd:
            return AuthResult(
                status=AuthStatus.AMBIGUOUS,
                telefono_normalized=telefono_n,
            )

    user = find_patient_by_phone(telefono_n, email=email)
    if user and check_password_hash(user.password_hash, password):
        from app.services.patient_invite_service import patient_can_login

        if not patient_can_login(user):
            return AuthResult(
                status=AuthStatus.INACTIVE,
                patient=user,
                telefono_normalized=telefono_n,
            )
        return AuthResult(
            status=AuthStatus.OK_USER,
            patient=user,
            telefono_normalized=telefono_n,
        )

    return AuthResult(status=AuthStatus.INVALID, telefono_normalized=telefono_n)


def patient_login_user_dict(patient: Patient) -> dict[str, Any]:
    """Subset user per risposta login."""
    return {
        "id": patient.id,
        "role": "user",
        "name": f"{patient.nome} {patient.cognome}".strip(),
        "nome": patient.nome,
        "cognome": patient.cognome,
        "telefono": patient.telefono,
        "nutrizionista_id": patient.nutrizionista_id,
    }


def patient_public_dict(patient: Patient) -> dict[str, Any]:
    """Profilo pubblico per GET /api/v1/me (mai password_hash)."""
    peso = patient.peso_iniziale
    if peso is not None:
        try:
            peso = float(peso)
        except (TypeError, ValueError):
            peso = None

    data_nascita = None
    if patient.data_nascita is not None:
        data_nascita = patient.data_nascita.isoformat()

    return {
        "id": patient.id,
        "role": "user",
        "name": f"{patient.nome} {patient.cognome}".strip(),
        "nome": patient.nome,
        "cognome": patient.cognome,
        "telefono": patient.telefono,
        "email": patient.email,
        "sesso": patient.sesso,
        "data_nascita": data_nascita,
        "altezza_cm": patient.altezza_cm,
        "peso_iniziale": peso,
        "intolleranze": getattr(patient, "intolleranze_decrypted", None) or patient.intolleranze,
        "cibi_da_evitare": patient.cibi_da_ev,
        "patologie": getattr(patient, "patologie_decrypted", None) or patient.patologie,
        "esami_biochimici": getattr(patient, "esami_biochimici_decrypted", None)
        or patient.esami_biochimici,
        "allenamenti_descr": patient.allenamenti_descr,
        "stato_cliente": getattr(patient, "stato_cliente", None) or "attivo",
        "account_status": getattr(patient, "account_status", None) or "active",
        "nutrizionista_id": patient.nutrizionista_id,
        "consenso_privacy": bool(getattr(patient, "consenso_privacy", False)),
        "consenso_marketing": bool(getattr(patient, "consenso_marketing", False)),
        "privacy_policy_version": getattr(patient, "privacy_policy_version", None),
        "erasure_requested_at": (
            patient.erasure_requested_at.isoformat()
            if getattr(patient, "erasure_requested_at", None)
            else None
        ),
    }
