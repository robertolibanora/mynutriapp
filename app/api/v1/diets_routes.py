"""API diete paziente autenticato."""

from __future__ import annotations

from flask import g

from app.api.v1.deps import require_patient_access_token
from app.api.v1.errors import api_error
from app.services.diet_service import (
    build_list_payload,
    get_active_for_patient,
    get_for_patient,
    serialize_diet,
)


def register_diets_routes(bp):
    @bp.get("/diets")
    @require_patient_access_token
    def diets_list():
        return build_list_payload(g.current_patient.id), 200

    @bp.get("/diets/active")
    @require_patient_access_token
    def diets_active():
        active = get_active_for_patient(g.current_patient.id)
        if active is None:
            return {"diet": None}, 200
        kind, obj = active
        return {"diet": serialize_diet(kind, obj, attiva=True)}, 200

    @bp.get("/diets/<int:diet_id>")
    @require_patient_access_token
    def diets_detail(diet_id: int):
        found = get_for_patient(diet_id, g.current_patient.id)
        if found is None:
            return api_error("Dieta non trovata", code="not_found", status=404)
        kind, obj = found
        active = get_active_for_patient(g.current_patient.id)
        attiva = bool(
            active is not None
            and active[0] == kind
            and active[1].id == obj.id
        )
        return serialize_diet(kind, obj, attiva=attiva), 200
