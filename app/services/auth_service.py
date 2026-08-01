"""Autenticazione condivisa tra login web e API /api/v1."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from werkzeug.security import check_password_hash

from app.models.models import Patient
from app.utils.helpers import normalize_phone


class AuthStatus(str, Enum):
    OK_ADMIN = "ok_admin"
    OK_USER = "ok_user"
    INACTIVE = "inactive"
    INVALID = "invalid"


@dataclass(frozen=True)
class AuthResult:
    status: AuthStatus
    patient: Optional[Patient] = None
    admin_name: Optional[str] = None
    telefono_normalized: str = ""


def _admin_phone() -> str:
    return normalize_phone(os.getenv("ADMIN_PHONE", "") or "")


def _admin_password_hash() -> Optional[str]:
    return os.getenv("ADMIN_PASSWORD_HASH") or None


def _admin_name() -> str:
    return (os.getenv("ADMIN_NAME") or "MyNutriApp").strip()


def find_patient_by_phone(telefono: str) -> Optional[Patient]:
    """Lookup paziente con match esatto e fallback normalize_phone."""
    telefono = normalize_phone(telefono)
    user = Patient.query.filter_by(telefono=telefono).first()
    if user:
        return user
    for candidate in Patient.query.filter(Patient.telefono.isnot(None)).all():
        if normalize_phone(candidate.telefono) == telefono:
            return candidate
    return None


def authenticate(telefono: str, password: str) -> AuthResult:
    """
    Verifica credenziali (stessa logica del login web).

    Non tocca sessioni né emette token: responsabilità del caller.
    """
    telefono_n = normalize_phone(telefono or "")
    password = password or ""

    admin_phone = _admin_phone()
    admin_hash = _admin_password_hash()
    if admin_phone and admin_hash:
        if telefono_n == admin_phone and check_password_hash(admin_hash, password):
            return AuthResult(
                status=AuthStatus.OK_ADMIN,
                admin_name=_admin_name(),
                telefono_normalized=telefono_n,
            )

    user = find_patient_by_phone(telefono_n)
    if user and check_password_hash(user.password_hash, password):
        stato = getattr(user, "stato_cliente", None) or "attivo"
        if stato != "attivo":
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
    }
