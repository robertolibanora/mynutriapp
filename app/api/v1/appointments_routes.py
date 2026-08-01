"""API appuntamenti paziente autenticato."""

from __future__ import annotations

from flask import g

from app.api.v1.deps import require_patient_access_token
from app.api.v1.errors import api_error
from app.services.appointment_service import (
    get_for_patient,
    list_for_patient,
    serialize_appointment,
)


def register_appointments_routes(bp):
    @bp.get("/appointments")
    @require_patient_access_token
    def appointments_list():
        patient = g.current_patient
        items = list_for_patient(patient.id)
        return {
            "appointments": [
                serialize_appointment(a, patient=patient) for a in items
            ]
        }, 200

    @bp.get("/appointments/<int:appointment_id>")
    @require_patient_access_token
    def appointments_detail(appointment_id: int):
        patient = g.current_patient
        appt = get_for_patient(appointment_id, patient.id)
        if appt is None:
            return api_error(
                "Appuntamento non trovato",
                code="not_found",
                status=404,
            )
        return serialize_appointment(appt, patient=patient), 200
