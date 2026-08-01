"""Documenti paziente: metadati, upload, download, delete."""

from __future__ import annotations

import logging
import mimetypes
import os
import uuid
from datetime import date, datetime
from typing import Any, Optional

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.config.config import (
    Config,
    get_allowed_extensions,
    get_full_path,
    get_upload_folder,
)
from app.models.models import Documento, db

ALLOWED_TIPI = frozenset({"analisi", "referto", "excel", "pdf_altro"})
ALLOWED_MIMES = {
    "application/pdf": ["pdf"],
    "image/jpeg": ["jpg", "jpeg"],
    "image/png": ["png"],
}


class DocumentValidationError(ValueError):
    pass


def list_for_patient(patient_id: int) -> list[Documento]:
    return (
        Documento.query.filter_by(patient_id=patient_id)
        .order_by(Documento.data_upload.desc())
        .all()
    )


def get_for_patient(document_id: int, patient_id: int) -> Optional[Documento]:
    doc = Documento.query.filter_by(id=document_id).first()
    if doc is None or doc.patient_id != patient_id:
        return None
    return doc


def resolve_file_path(documento: Documento) -> Optional[str]:
    if not documento.file_path:
        return None
    path = get_full_path(documento.file_path)
    if os.path.isfile(path):
        return path
    if os.path.isfile(documento.file_path):
        return documento.file_path
    return None


def _basename_safe(documento: Documento) -> str:
    raw = os.path.basename(documento.file_path or "")
    return raw or f"documento_{documento.id}"


def _guess_content_type(path: Optional[str], filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    if path:
        guessed, _ = mimetypes.guess_type(path)
        if guessed:
            return guessed
    return "application/octet-stream"


def _iso_dt(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep="T", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def serialize_document(documento: Documento) -> dict[str, Any]:
    filename = _basename_safe(documento)
    path = resolve_file_path(documento)
    return {
        "id": documento.id,
        "tipo": documento.tipo,
        "descrizione": documento.descrizione,
        "data_upload": _iso_dt(documento.data_upload),
        "filename": filename,
        "content_type": _guess_content_type(path, filename),
    }


def _allowed_file(filename: str) -> bool:
    allowed = get_allowed_extensions("documenti")
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def create_for_patient(
    patient_id: int,
    *,
    tipo: str,
    file: Optional[FileStorage],
    descrizione: Optional[str] = None,
) -> Documento:
    if tipo not in ALLOWED_TIPI:
        raise DocumentValidationError("tipo documento non valido")
    if not file or not file.filename:
        raise DocumentValidationError("file obbligatorio")
    if not _allowed_file(file.filename):
        raise DocumentValidationError("Formato file non valido. Usa PDF, JPG o PNG")

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    if file_size > Config.MAX_FILE_SIZE:
        max_mb = Config.MAX_FILE_SIZE // (1024 * 1024)
        raise DocumentValidationError(f"File troppo grande. Massimo {max_mb}MB")

    try:
        import magic

        file_content = file.read(1024)
        file.seek(0)
        mime_type = magic.from_buffer(file_content, mime=True)
        if mime_type not in ALLOWED_MIMES:
            raise DocumentValidationError("Tipo file non valido (validazione MIME)")
    except ImportError:
        pass
    except DocumentValidationError:
        raise
    except Exception as exc:
        logging.warning("MIME validation failed: %s", exc)

    upload_folder = get_upload_folder("documenti")
    os.makedirs(upload_folder, exist_ok=True)
    original = secure_filename(file.filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    filename = f"{patient_id}_{timestamp}_{unique_id}_{original}"
    save_path = os.path.join(upload_folder, filename)
    file.save(save_path)

    desc = (descrizione or "").strip() or None
    nuovo = Documento(
        patient_id=patient_id,
        tipo=tipo,
        file_path=save_path,
        descrizione=desc,
    )
    db.session.add(nuovo)
    db.session.commit()
    return nuovo


def delete_for_patient(document_id: int, patient_id: int) -> bool:
    """True se eliminato; False se non trovato / non ownership."""
    documento = get_for_patient(document_id, patient_id)
    if documento is None:
        return False

    path = resolve_file_path(documento)
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            logging.warning("Impossibile eliminare file documento %s", path)

    db.session.delete(documento)
    db.session.commit()
    return True


def build_list_payload(patient_id: int) -> dict[str, Any]:
    return {
        "documents": [serialize_document(d) for d in list_for_patient(patient_id)]
    }
