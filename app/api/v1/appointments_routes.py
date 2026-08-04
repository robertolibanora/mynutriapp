"""API appuntamenti paziente autenticato."""

from __future__ import annotations

from datetime import datetime

from flask import g, request

from app.api.v1.deps import require_patient_access_token
from app.api.v1.errors import api_error
from app.services.appointment_service import (
    AppointmentBookingError,
    book_for_patient,
    get_for_patient,
    list_availability_for_patient,
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

    @bp.get("/appointments/availability")
    @require_patient_access_token
    def appointments_availability():
        """Slot liberi del nutrizionista collegato al paziente."""
        patient = g.current_patient
        try:
            limite = int(request.args.get("limit") or 100)
        except (TypeError, ValueError):
            limite = 100
        limite = max(1, min(limite, 200))
        return list_availability_for_patient(patient, limite=limite), 200

    @bp.post("/appointments")
    @require_patient_access_token
    def appointments_create():
        """Prenota uno slot libero (richiesta in_attesa)."""
        patient = g.current_patient
        data = request.get_json(silent=True) or {}
        raw_dt = data.get("data_appuntamento")
        if not raw_dt or not isinstance(raw_dt, str):
            return api_error(
                "Campo data_appuntamento obbligatorio",
                code="validation_error",
                status=400,
            )

        parsed = None
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M",
        ):
            try:
                parsed = datetime.strptime(raw_dt.strip(), fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            # ISO con timezone / microsecondi
            try:
                parsed = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    parsed = parsed.replace(tzinfo=None)
            except ValueError:
                return api_error(
                    "Formato data_appuntamento non valido",
                    code="validation_error",
                    status=400,
                )

        tipo = (data.get("tipo") or "check").strip()
        note = data.get("note")
        if note is not None and not isinstance(note, str):
            note = str(note)

        try:
            appt = book_for_patient(
                patient,
                data_appuntamento=parsed,
                tipo=tipo,
                note=note,
            )
        except AppointmentBookingError as exc:
            status = 409 if exc.code == "slot_unavailable" else 400
            return api_error(exc.message, code=exc.code, status=status)

        return serialize_appointment(appt, patient=patient), 201

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
