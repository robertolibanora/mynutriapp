"""Auth JSON: login + refresh token."""

from __future__ import annotations

from flask import request

from app.api.v1.errors import api_error
from app.models.models import Patient, db
from app.services.auth_service import (
    AuthStatus,
    authenticate,
    patient_login_user_dict,
)
from app.services.jwt_service import (
    JwtError,
    access_expires_seconds,
    decode_token,
    issue_token_pair,
    patient_id_from_payload,
)
from app.utils.audit import log_audit_event


def register_auth_routes(bp):
    @bp.post("/auth/login")
    def login():
        data = request.get_json(silent=True) or {}
        telefono = data.get("telefono") or ""
        password = data.get("password") or ""

        if not str(telefono).strip() or not str(password):
            return api_error(
                "Credenziali non valide",
                code="invalid_credentials",
                status=401,
            )

        result = authenticate(str(telefono), str(password))

        if result.status == AuthStatus.OK_ADMIN:
            return api_error(
                "Accesso riservato all'area web",
                code="admin_web_only",
                status=403,
            )

        if result.status == AuthStatus.INACTIVE:
            return api_error(
                "Account non ancora attivo. Attendi la conferma del nutrizionista.",
                code="account_inactive",
                status=403,
            )

        if result.status != AuthStatus.OK_USER or result.patient is None:
            telefono_n = result.telefono_normalized or ""
            log_audit_event(
                "LOGIN_FAILED",
                "system",
                details={
                    "user_type": "api",
                    "telefono": (telefono_n[:3] + "***") if telefono_n else "***",
                },
            )
            db.session.commit()
            return api_error(
                "Credenziali non valide",
                code="invalid_credentials",
                status=401,
            )

        patient = result.patient
        name = f"{patient.nome} {patient.cognome}".strip()
        tokens = issue_token_pair(patient_id=patient.id, name=name)

        log_audit_event(
            "LOGIN",
            "system",
            details={"user_type": "user", "user_id": patient.id, "via": "api"},
        )
        db.session.commit()

        return {
            **tokens,
            "user": patient_login_user_dict(patient),
        }, 200

    @bp.post("/auth/refresh")
    def refresh():
        data = request.get_json(silent=True) or {}
        refresh_token = data.get("refresh_token") or ""
        if not refresh_token:
            return api_error("Refresh token mancante", code="invalid_token", status=401)

        try:
            payload = decode_token(refresh_token, expected_typ="refresh")
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

        name = f"{patient.nome} {patient.cognome}".strip()
        tokens = issue_token_pair(patient_id=patient.id, name=name)
        return {
            **tokens,
            "expires_in": access_expires_seconds(),
        }, 200
