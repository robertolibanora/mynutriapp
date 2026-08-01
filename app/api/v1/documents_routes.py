"""API documenti paziente autenticato."""

from __future__ import annotations

import os

from flask import g, request, send_from_directory

from app.api.v1.deps import require_patient_access_token
from app.api.v1.errors import api_error
from app.services.document_service import (
    DocumentValidationError,
    build_list_payload,
    create_for_patient,
    delete_for_patient,
    get_for_patient,
    resolve_file_path,
    serialize_document,
)


def register_documents_routes(bp):
    @bp.get("/documents")
    @require_patient_access_token
    def documents_list():
        return build_list_payload(g.current_patient.id), 200

    @bp.get("/documents/<int:document_id>")
    @require_patient_access_token
    def documents_detail(document_id: int):
        row = get_for_patient(document_id, g.current_patient.id)
        if row is None:
            return api_error("Documento non trovato", code="not_found", status=404)
        return serialize_document(row), 200

    @bp.post("/documents")
    @require_patient_access_token
    def documents_create():
        tipo = request.form.get("tipo") or ""
        descrizione = request.form.get("descrizione")
        file = request.files.get("file")
        try:
            row = create_for_patient(
                g.current_patient.id,
                tipo=tipo,
                file=file,
                descrizione=descrizione,
            )
        except DocumentValidationError as exc:
            msg = str(exc)
            code = "validation_error"
            status = 400
            if "troppo grande" in msg.lower():
                code = "payload_too_large"
                status = 413
            return api_error(msg, code=code, status=status)
        return serialize_document(row), 201

    @bp.get("/documents/<int:document_id>/download")
    @require_patient_access_token
    def documents_download(document_id: int):
        row = get_for_patient(document_id, g.current_patient.id)
        if row is None:
            return api_error("Documento non trovato", code="not_found", status=404)
        path = resolve_file_path(row)
        if path is None:
            return api_error("File non disponibile", code="not_found", status=404)
        meta = serialize_document(row)
        directory = os.path.dirname(path)
        filename = os.path.basename(path)
        return send_from_directory(
            directory,
            filename,
            mimetype=meta["content_type"],
            as_attachment=True,
            download_name=meta["filename"],
        )

    @bp.delete("/documents/<int:document_id>")
    @require_patient_access_token
    def documents_delete(document_id: int):
        ok = delete_for_patient(document_id, g.current_patient.id)
        if not ok:
            return api_error("Documento non trovato", code="not_found", status=404)
        return {"ok": True}, 200
