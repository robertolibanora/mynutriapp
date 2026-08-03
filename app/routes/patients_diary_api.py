"""API timeline / trends / creazione consultation per paziente."""

from __future__ import annotations

from functools import wraps

from flask import Blueprint, jsonify, request, session

from app.services.diario_audio_service import DiarioAudioError
from app.services.diario_consultation_service import create_consultation
from app.services.diario_timeline_service import (
    get_patient_diary_timeline,
    get_patient_diary_trends,
)

patients_diary_api_bp = Blueprint(
    "patients_diary_api",
    __name__,
    url_prefix="/api/patients",
)


def api_nutrizionista_required(func):
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


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in ("1", "true", "yes", "on")


@patients_diary_api_bp.route("/<int:patient_id>/consultations", methods=["POST"])
@api_nutrizionista_required
def create_patient_consultation(patient_id: int):
    """POST crea consultation BOZZA (poi upload audio sulla consultation)."""
    body = request.get_json(silent=True) or {}
    consenso_reg = body.get("consenso_registrazione")
    consenso_ai = body.get("consenso_ai")
    if consenso_reg is None:
        consenso_reg = _truthy(request.form.get("consenso_registrazione"))
    if consenso_ai is None:
        consenso_ai = _truthy(request.form.get("consenso_ai"))
    try:
        payload = create_consultation(
            patient_id=patient_id,
            utente_id=int(session["utente_id"]),
            data_colloquio=body.get("data_colloquio") or request.form.get("data_colloquio"),
            note_manuali=body.get("note_manuali") or request.form.get("note_manuali"),
            set_consenso_registrazione=bool(consenso_reg),
            set_consenso_ai=bool(consenso_ai),
        )
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code
    return jsonify(payload), 201


@patients_diary_api_bp.route("/<int:patient_id>/diary", methods=["GET"])
@api_nutrizionista_required
def patient_diary_timeline(patient_id: int):
    """GET timeline (CONFERMATE di default)."""
    try:
        payload = get_patient_diary_timeline(
            patient_id=patient_id,
            utente_id=int(session["utente_id"]),
            include_pending=_truthy(request.args.get("include_pending")),
            date_from=request.args.get("from") or request.args.get("date_from"),
            date_to=request.args.get("to") or request.args.get("date_to"),
            page=int(request.args.get("page", 1)),
            per_page=int(request.args.get("per_page", 20)),
        )
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code
    except ValueError:
        return jsonify({"error": "Parametri page/per_page non validi"}), 400
    return jsonify(payload), 200


@patients_diary_api_bp.route("/<int:patient_id>/diary/trends", methods=["GET"])
@api_nutrizionista_required
def patient_diary_trends(patient_id: int):
    """GET serie numeriche per grafici (solo confermate, skip null)."""
    try:
        payload = get_patient_diary_trends(
            patient_id=patient_id,
            utente_id=int(session["utente_id"]),
            date_from=request.args.get("from") or request.args.get("date_from"),
            date_to=request.args.get("to") or request.args.get("date_to"),
        )
    except DiarioAudioError as exc:
        return jsonify({"error": str(exc)}), exc.status_code
    return jsonify(payload), 200
