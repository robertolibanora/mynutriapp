"""Staging: le credenziali ADMIN_*.env diventano un paziente attivo (niente UI admin)."""

from __future__ import annotations

import os

from app.models.models import Patient, db
from app.services.auth_service import find_patient_by_phone
from app.utils.helpers import normalize_phone


def ensure_patient_for_admin_credentials() -> Patient:
    """Crea/aggiorna un paziente attivo con telefono e hash password admin."""
    phone = normalize_phone(os.getenv("ADMIN_PHONE", "") or "")
    password_hash = os.getenv("ADMIN_PASSWORD_HASH") or ""
    name = (os.getenv("ADMIN_NAME") or "Demo Store").strip() or "Demo Store"

    if not phone or not password_hash:
        raise RuntimeError("ADMIN_PHONE / ADMIN_PASSWORD_HASH mancanti")

    parts = name.split(None, 1)
    nome = parts[0]
    cognome = parts[1] if len(parts) > 1 else "Store"

    patient = find_patient_by_phone(phone)
    if patient is None:
        patient = Patient(
            nome=nome,
            cognome=cognome,
            telefono=phone,
            password_hash=password_hash,
            stato_cliente="attivo",
            consenso_registrazione=False,
            consenso_ai=False,
        )
        db.session.add(patient)
    else:
        patient.password_hash = password_hash
        patient.stato_cliente = "attivo"
        if not patient.nome:
            patient.nome = nome
        if not patient.cognome:
            patient.cognome = cognome

    db.session.commit()
    return patient
