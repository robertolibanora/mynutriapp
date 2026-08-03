"""API GDPR per paziente autenticato (mobile / JWT)."""

from __future__ import annotations

from flask import Response, g, request

from app.api.v1.deps import require_patient_access_token
from app.api.v1.errors import api_error
from app.config.config import Config
from app.models.models import db
from app.services.auth_service import patient_public_dict
from app.services.gdpr_service import (
    GdprError,
    apply_consents,
    export_as_json_bytes,
    request_erasure,
)
from app.utils.audit import log_audit_event


def _privacy_dict(patient) -> dict:
    return {
        "consenso_privacy": bool(getattr(patient, "consenso_privacy", False)),
        "consenso_marketing": bool(getattr(patient, "consenso_marketing", False)),
        "privacy_policy_version": getattr(patient, "privacy_policy_version", None)
        or Config.PRIVACY_POLICY_VERSION,
        "consenso_privacy_il": (
            patient.consenso_privacy_il.isoformat() + "Z"
            if getattr(patient, "consenso_privacy_il", None)
            else None
        ),
        "consenso_marketing_il": (
            patient.consenso_marketing_il.isoformat() + "Z"
            if getattr(patient, "consenso_marketing_il", None)
            else None
        ),
        "erasure_requested_at": (
            patient.erasure_requested_at.isoformat() + "Z"
            if getattr(patient, "erasure_requested_at", None)
            else None
        ),
        "erasure_completed_at": (
            patient.erasure_completed_at.isoformat() + "Z"
            if getattr(patient, "erasure_completed_at", None)
            else None
        ),
    }


def register_gdpr_routes(bp):
    @bp.get("/me/privacy")
    @require_patient_access_token
    def me_privacy_get():
        """Stato consensi e richieste GDPR del paziente autenticato."""
        return _privacy_dict(g.current_patient), 200

    @bp.patch("/me/privacy")
    @require_patient_access_token
    def me_privacy_patch():
        """Aggiorna consensi (marketing liberamente; privacy solo verso true)."""
        data = request.get_json(silent=True) or {}
        patient = g.current_patient

        if "consenso_privacy" in data:
            if data.get("consenso_privacy") is False or data.get("consenso_privacy") in (
                0,
                "0",
                "false",
                "False",
            ):
                return api_error(
                    "Per revocare il consenso privacy richiedi la cancellazione dei dati.",
                    code="privacy_revoke_via_erasure",
                    status=400,
                )
            apply_consents(patient, consenso_privacy=True)

        if "consenso_marketing" in data:
            apply_consents(
                patient,
                consenso_marketing=bool(data.get("consenso_marketing")),
            )

        log_audit_event(
            "UPDATE",
            "patient",
            patient.id,
            details={"via": "api_v1", "action": "privacy_consents"},
        )
        db.session.commit()
        return {
            "privacy": _privacy_dict(patient),
            "user": patient_public_dict(patient),
        }, 200

    @bp.get("/me/export")
    @require_patient_access_token
    def me_export():
        """Portabilità dati (Art. 20) — download JSON."""
        patient = g.current_patient
        payload = export_as_json_bytes(patient)
        log_audit_event(
            "EXPORT",
            "patient",
            patient.id,
            details={"via": "api_v1"},
        )
        db.session.commit()
        filename = f"miei_dati_{patient.id}.json"
        return Response(
            payload,
            mimetype="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @bp.post("/me/erasure")
    @require_patient_access_token
    def me_erasure():
        """Richiesta di oblio (Art. 17) — elaborata dallo staff."""
        patient = g.current_patient
        try:
            request_erasure(patient)
            db.session.commit()
        except GdprError as exc:
            return api_error(str(exc), code="erasure_error", status=400)

        return {
            "ok": True,
            "message": "Richiesta di cancellazione registrata.",
            "privacy": _privacy_dict(patient),
        }, 200
