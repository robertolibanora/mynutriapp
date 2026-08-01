"""API allenamenti paziente autenticato."""

from __future__ import annotations

import os

from flask import g, send_from_directory

from app.api.v1.deps import require_patient_access_token
from app.api.v1.errors import api_error
from app.services.workout_service import (
    build_list_payload,
    get_active_for_patient,
    get_for_patient,
    resolve_pdf_path,
    serialize_workout,
)


def register_workouts_routes(bp):
    @bp.get("/workouts")
    @require_patient_access_token
    def workouts_list():
        return build_list_payload(g.current_patient.id), 200

    @bp.get("/workouts/active")
    @require_patient_access_token
    def workouts_active():
        active = get_active_for_patient(g.current_patient.id)
        if active is None:
            return {"workout": None}, 200
        return {"workout": serialize_workout(active, attiva=True)}, 200

    @bp.get("/workouts/<int:workout_id>")
    @require_patient_access_token
    def workouts_detail(workout_id: int):
        row = get_for_patient(workout_id, g.current_patient.id)
        if row is None:
            return api_error("Allenamento non trovato", code="not_found", status=404)
        active = get_active_for_patient(g.current_patient.id)
        attiva = bool(active is not None and active.id == row.id)
        return serialize_workout(row, attiva=attiva), 200

    @bp.get("/workouts/<int:workout_id>/pdf")
    @require_patient_access_token
    def workouts_pdf(workout_id: int):
        row = get_for_patient(workout_id, g.current_patient.id)
        if row is None:
            return api_error("Allenamento non trovato", code="not_found", status=404)
        path = resolve_pdf_path(row)
        if path is None:
            return api_error("PDF non disponibile", code="not_found", status=404)
        directory = os.path.dirname(path)
        filename = os.path.basename(path)
        return send_from_directory(
            directory,
            filename,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )
