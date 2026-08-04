"""Auth JSON: login + refresh + forgot/reset password + attivazione account."""

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
    assert_token_version,
    decode_token,
    issue_token_pair,
    patient_id_from_payload,
)
from app.services.password_reset_service import (
    GENERIC_OK_MESSAGE,
    PasswordResetError,
    request_patient_reset,
    reset_patient_password,
)
from app.services.patient_invite_service import (
    PatientInviteError,
    activate_account,
    patient_can_login,
)
from app.utils.audit import log_audit_event


def register_auth_routes(bp):
    @bp.post("/auth/login")
    def login():
        data = request.get_json(silent=True) or {}
        telefono = data.get("telefono") or ""
        password = data.get("password") or ""
        email = data.get("email") or ""

        if not str(telefono).strip() or not str(password):
            return api_error(
                "Credenziali non valide",
                code="invalid_credentials",
                status=401,
            )

        result = authenticate(str(telefono), str(password), email=email or None)

        if result.status in (
            AuthStatus.OK_SUPER_ADMIN,
            AuthStatus.OK_NUTRIZIONISTA,
            AuthStatus.OK_ADMIN,
        ):
            return api_error(
                "Accesso riservato all'area web",
                code="staff_web_only",
                status=403,
            )

        if result.status == AuthStatus.INACTIVE:
            return api_error(
                "Account non ancora attivo. Controlla l'email di invito o attendi la conferma.",
                code="account_inactive",
                status=403,
            )

        if result.status == AuthStatus.AMBIGUOUS:
            return api_error(
                "Telefono associato a più professionisti: invia anche l'email.",
                code="phone_ambiguous",
                status=409,
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
        tokens = issue_token_pair(
            patient_id=patient.id,
            name=name,
            token_version=int(getattr(patient, "token_version", 0) or 0),
        )

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

        try:
            assert_token_version(payload, patient)
        except JwtError:
            return api_error("Token non valido o scaduto", code="invalid_token", status=401)

        if not patient_can_login(patient):
            return api_error(
                "Account non attivo",
                code="account_inactive",
                status=403,
            )

        name = f"{patient.nome} {patient.cognome}".strip()
        tokens = issue_token_pair(
            patient_id=patient.id,
            name=name,
            token_version=int(getattr(patient, "token_version", 0) or 0),
        )
        return {
            **tokens,
            "expires_in": access_expires_seconds(),
        }, 200

    @bp.post("/auth/forgot-password")
    def forgot_password():
        data = request.get_json(silent=True) or {}
        email = data.get("email") or ""
        # Risposta sempre generica (anche email assente/malformata)
        if str(email).strip():
            try:
                msg = request_patient_reset(str(email))
            except Exception:  # noqa: BLE001
                db.session.rollback()
                msg = GENERIC_OK_MESSAGE
        else:
            msg = GENERIC_OK_MESSAGE
        return {"ok": True, "message": msg}, 200

    @bp.post("/auth/reset-password")
    def reset_password():
        data = request.get_json(silent=True) or {}
        token = data.get("token") or ""
        password = data.get("password") or ""
        password_confirm = data.get("password_confirm") or data.get("password_confirmation") or ""
        try:
            patient = reset_patient_password(str(token), str(password), str(password_confirm))
            log_audit_event(
                "PASSWORD_RESET",
                "system",
                details={"user_type": "user", "user_id": patient.id, "via": "api"},
            )
            db.session.commit()
        except PasswordResetError as exc:
            db.session.rollback()
            return api_error(exc.message, code=exc.code, status=400)
        except Exception:  # noqa: BLE001
            db.session.rollback()
            return api_error("Reset non riuscito", code="reset_error", status=400)
        return {
            "ok": True,
            "message": "Password aggiornata. Accedi con la nuova password.",
        }, 200

    def _activate_handler():
        """Attivazione account da token di invito (primo accesso)."""
        data = request.get_json(silent=True) or {}
        token = data.get("token") or ""
        password = data.get("password") or ""
        password_confirm = (
            data.get("password_confirm") or data.get("password_confirmation") or ""
        )
        try:
            patient = activate_account(str(token), str(password), str(password_confirm))
            log_audit_event(
                "ACCOUNT_ACTIVATED",
                "system",
                details={"user_type": "user", "user_id": patient.id, "via": "api"},
            )
            db.session.commit()
        except PatientInviteError as exc:
            db.session.rollback()
            return api_error(exc.message, code=exc.code, status=400)
        except Exception:  # noqa: BLE001
            db.session.rollback()
            return api_error("Attivazione non riuscita", code="activate_error", status=400)
        return {
            "ok": True,
            "message": "Account attivato. Puoi accedere dall'app.",
        }, 200

    # Canonico (mobile) + alias legacy
    bp.post("/auth/activate-account")(_activate_handler)
    bp.post("/auth/activate")(_activate_handler)
