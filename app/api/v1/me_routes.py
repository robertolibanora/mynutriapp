"""Profilo paziente autenticato."""

from __future__ import annotations

from flask import g

from app.api.v1.deps import require_patient_access_token
from app.services.auth_service import patient_public_dict


def register_me_routes(bp):
    @bp.get("/me")
    @require_patient_access_token
    def me():
        return patient_public_dict(g.current_patient), 200
