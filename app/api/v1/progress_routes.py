"""API progressi paziente autenticato."""

from __future__ import annotations

import mimetypes
import os

from flask import g, request, send_from_directory

from app.api.v1.deps import require_patient_access_token
from app.api.v1.errors import api_error
from app.services.progress_service import (
    ProgressValidationError,
    create_for_patient,
    get_for_patient,
    get_latest_for_patient,
    list_for_patient,
    resolve_photo_path,
    serialize_detail,
    serialize_summary,
)


def register_progress_routes(bp):
    @bp.get("/progress")
    @require_patient_access_token
    def progress_list():
        rows = list_for_patient(g.current_patient.id)
        return {"progress": [serialize_summary(p) for p in rows]}, 200

    @bp.get("/progress/latest")
    @require_patient_access_token
    def progress_latest():
        row = get_latest_for_patient(g.current_patient.id)
        if row is None:
            return {"progress": None}, 200
        return {"progress": serialize_summary(row)}, 200

    @bp.get("/progress/<int:progress_id>")
    @require_patient_access_token
    def progress_detail(progress_id: int):
        row = get_for_patient(progress_id, g.current_patient.id)
        if row is None:
            return api_error("Progresso non trovato", code="not_found", status=404)
        return serialize_detail(row), 200

    @bp.post("/progress")
    @require_patient_access_token
    def progress_create():
        data = request.get_json(silent=True) or {}
        try:
            row = create_for_patient(
                g.current_patient.id,
                peso_settimanale=data.get("peso_settimanale"),
                frequenza_allenamenti=data.get("frequenza_allenamenti"),
                aderenza=data.get("aderenza"),
            )
        except ProgressValidationError as exc:
            return api_error(str(exc), code="validation_error", status=400)
        return serialize_detail(row), 201

    @bp.get("/progress/<int:progress_id>/photo")
    @require_patient_access_token
    def progress_photo(progress_id: int):
        row = get_for_patient(progress_id, g.current_patient.id)
        if row is None:
            return api_error("Progresso non trovato", code="not_found", status=404)
        path = resolve_photo_path(row)
        if path is None:
            return api_error("Foto non disponibile", code="not_found", status=404)
        directory = os.path.dirname(path)
        filename = os.path.basename(path)
        mime, _ = mimetypes.guess_type(filename)
        return send_from_directory(
            directory,
            filename,
            mimetype=mime or "application/octet-stream",
        )
