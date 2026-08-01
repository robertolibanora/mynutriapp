"""Dipendenze auth JWT per route /api/v1."""

from __future__ import annotations

from functools import wraps
from typing import Callable

from flask import g, request

from app.api.v1.errors import api_error
from app.models.models import Patient, db
from app.services.jwt_service import JwtError, decode_token, patient_id_from_payload


def _bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[7:].strip()
    return token or None


def require_patient_access_token(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        token = _bearer_token()
        if not token:
            return api_error("Autenticazione richiesta", code="unauthorized", status=401)
        try:
            payload = decode_token(token, expected_typ="access")
            patient_id = patient_id_from_payload(payload)
        except JwtError:
            return api_error("Token non valido o scaduto", code="invalid_token", status=401)

        patient = db.session.get(Patient, patient_id)
        if patient is None:
            return api_error("Token non valido o scaduto", code="invalid_token", status=401)

        stato = getattr(patient, "stato_cliente", None) or "attivo"
        if stato != "attivo":
            return api_error(
                "Account non attivo",
                code="account_inactive",
                status=403,
            )

        g.current_patient = patient
        g.jwt_payload = payload
        return view(*args, **kwargs)

    return wrapped
