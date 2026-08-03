"""API upload/cancellazione audio e trascrizione per consultation."""

from __future__ import annotations

from functools import wraps

from flask import Blueprint, jsonify, request, session

from app.schemas.diario import AudioRecordingResponse
from app.services.diario_audio_service import (
    DiarioAudioError,
    soft_delete_consultation_audio,
    upload_consultation_audio,
)
from app.services.diario_transcription_service import (
    enqueue_transcription,
    get_consultation_status,
    run_transcription_job,
)
from app.services.diario_extraction_service import (
    enqueue_diary_extraction,
    run_diary_extraction_job,
)
from app.services.diario_review_service import (
    amend_confirmed_diary,
    confirm_diary,
    get_diary_for_review,
    patch_diary,
    reject_and_regenerate,
)
from app.services.jobs import BackgroundTasks, dispatch_background_tasks

consultations_audio_bp = Blueprint(
    "consultations_audio",
    __name__,
    url_prefix="/api/consultations",
)


def api_nutrizionista_required(func):
    """Richiede sessione admin con ``utente_id`` (nutrizionista)."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") not in ('admin', 'nutrizionista'):
            return jsonify({"error": "Accesso non autorizzato"}), 403
        if not session.get("utente_id"):
            try:
                from app.services.utente_service import ensure_session_utente_id

                if ensure_session_utente_id() is None:
                    raise RuntimeError("utente_id non disponibile")
            except Exception:  # noqa: BLE001
                return jsonify(
                    {
                        "error": "Sessione nutrizionista incompleta: manca utente_id. "
                        "Effettua di nuovo il login."
                    }
                ), 401
        return func(*args, **kwargs)

    return wrapper


@consultations_audio_bp.route("/<int:consultation_id>/audio", methods=["POST"])
@api_nutrizionista_required
def upload_audio(consultation_id: int):
    """POST /api/consultations/{id}/audio — multipart field ``audio``."""
    file_storage = request.files.get("audio")
    if file_storage is None:
        # Diagnostica: spesso Content-Type errato o body tagliato dal proxy
        import logging

        logging.getLogger(__name__).warning(
            "Upload audio senza campo file: consultation=%s content_type=%s "
            "content_length=%s files=%s form_keys=%s",
            consultation_id,
            request.content_type,
            request.content_length,
            list(request.files.keys()),
            list(request.form.keys()),
        )
    try:
        recording = upload_consultation_audio(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
            file_storage=file_storage,
        )
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code

    payload = AudioRecordingResponse.model_validate(recording).model_dump(mode="json")
    return jsonify(payload), 201


@consultations_audio_bp.route("/<int:consultation_id>/audio", methods=["DELETE"])
@api_nutrizionista_required
def delete_audio(consultation_id: int):
    """DELETE /api/consultations/{id}/audio — soft delete file + cancellato_il."""
    try:
        recording = soft_delete_consultation_audio(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
        )
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code

    payload = AudioRecordingResponse.model_validate(recording).model_dump(mode="json")
    return jsonify(payload), 200


@consultations_audio_bp.route("/<int:consultation_id>/transcribe", methods=["POST"])
@api_nutrizionista_required
def start_transcription(consultation_id: int):
    """POST /api/consultations/{id}/transcribe — avvia job in background."""
    background = BackgroundTasks()
    try:
        payload = enqueue_transcription(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
        )
        background.add_task(run_transcription_job, consultation_id)
        dispatch_background_tasks(background)
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code

    return jsonify(payload), 202


@consultations_audio_bp.route("/<int:consultation_id>/extract", methods=["POST"])
@api_nutrizionista_required
def start_diary_extraction(consultation_id: int):
    """POST /api/consultations/{id}/extract — genera diary_entry da transcript."""
    background = BackgroundTasks()
    try:
        payload = enqueue_diary_extraction(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
        )
        background.add_task(run_diary_extraction_job, consultation_id)
        dispatch_background_tasks(background)
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code

    return jsonify(payload), 202


@consultations_audio_bp.route("/<int:consultation_id>/status", methods=["GET"])
@api_nutrizionista_required
def consultation_status(consultation_id: int):
    """GET /api/consultations/{id}/status — stato pipeline + eventuale errore."""
    try:
        payload = get_consultation_status(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
        )
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code

    return jsonify(payload), 200


@consultations_audio_bp.route("/<int:consultation_id>/diary", methods=["GET"])
@api_nutrizionista_required
def get_diary(consultation_id: int):
    """GET diary_entry + trascrizione (flag da_revisionare / confermato)."""
    try:
        payload = get_diary_for_review(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
        )
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code
    return jsonify(payload), 200


@consultations_audio_bp.route("/<int:consultation_id>/diary", methods=["PATCH"])
@api_nutrizionista_required
def update_diary(consultation_id: int):
    """PATCH bozza pre-conferma (blocca se già CONFERMATO)."""
    body = request.get_json(silent=True) or {}
    try:
        payload = patch_diary(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
            contenuto_json=body.get("contenuto_json"),
            riassunto_testo=body.get("riassunto_testo"),
        )
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code
    return jsonify(payload), 200


@consultations_audio_bp.route("/<int:consultation_id>/diary/confirm", methods=["POST"])
@api_nutrizionista_required
def diary_confirm(consultation_id: int):
    """Conferma definitiva → CONFERMATO."""
    try:
        payload = confirm_diary(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
        )
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code
    return jsonify(payload), 200


@consultations_audio_bp.route("/<int:consultation_id>/diary/reject", methods=["POST"])
@api_nutrizionista_required
def diary_reject(consultation_id: int):
    """Scarta bozza e riavvia estrazione in background."""
    background = BackgroundTasks()
    try:
        reject_and_regenerate(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
        )
        payload = enqueue_diary_extraction(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
        )
        background.add_task(run_diary_extraction_job, consultation_id)
        dispatch_background_tasks(background)
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code
    payload["message"] = "Bozza scartata, rigenerazione avviata"
    return jsonify(payload), 202


@consultations_audio_bp.route("/<int:consultation_id>/diary/post-confirm", methods=["PATCH"])
@api_nutrizionista_required
def diary_post_confirm_amend(consultation_id: int):
    """Correzione esplicita di un diario già CONFERMATO."""
    body = request.get_json(silent=True) or {}
    try:
        payload = amend_confirmed_diary(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
            contenuto_json=body.get("contenuto_json"),
            riassunto_testo=body.get("riassunto_testo"),
            motivo=body.get("motivo"),
        )
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code
    return jsonify(payload), 200
