"""UI HTML revisione e timeline diario colloquio."""

from __future__ import annotations

import json
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.models import Patient, db
from app.services.diario_audio_service import DiarioAudioError
from app.services.diario_consultation_service import get_consultation_for_pipeline
from app.services.diario_review_service import get_diary_for_review
from app.services.diario_timeline_service import (
    get_patient_diary_timeline,
    get_patient_diary_trends,
)

diario_ui_bp = Blueprint("diario_ui", __name__, url_prefix="/admin/diario")


def _admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for("auth.login"))
        if not session.get("utente_id"):
            try:
                from app.services.utente_service import ensure_session_utente_id

                if ensure_session_utente_id() is None:
                    raise RuntimeError("utente_id non disponibile")
            except Exception:  # noqa: BLE001
                flash(
                    "Sessione nutrizionista incompleta: effettua di nuovo il login.",
                    "warning",
                )
                return redirect(url_for("auth.login"))
        return func(*args, **kwargs)

    return wrapper


@diario_ui_bp.route("/pazienti/<int:patient_id>/nuovo")
@_admin_required
def nuovo_colloquio(patient_id: int):
    """UI: crea colloquio + carica audio + avvia pipeline."""
    paziente = db.session.get(Patient, patient_id)
    if paziente is None:
        flash("Paziente non trovato", "danger")
        return redirect(url_for("patients.lista_pazienti"))
    return render_template(
        "admin/diario_pipeline.html",
        paziente=paziente,
        consultation=None,
        consultation_id=None,
        mode="nuovo",
    )


@diario_ui_bp.route("/consultations/<int:consultation_id>/pipeline")
@_admin_required
def pipeline_colloquio(consultation_id: int):
    """UI: riprendi upload/trascrizione/estrazione di un colloquio esistente."""
    try:
        payload = get_consultation_for_pipeline(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
        )
    except DiarioAudioError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("patients.lista_pazienti"))

    paziente = db.session.get(Patient, payload["patient"]["id"])
    return render_template(
        "admin/diario_pipeline.html",
        paziente=paziente,
        consultation=payload,
        consultation_id=consultation_id,
        mode="pipeline",
    )


@diario_ui_bp.route("/consultations/<int:consultation_id>/review")
@_admin_required
def review_diary(consultation_id: int):
    """UI: trascrizione a sinistra, campi editabili a destra."""
    try:
        payload = get_diary_for_review(
            consultation_id=consultation_id,
            utente_id=int(session["utente_id"]),
        )
    except DiarioAudioError as exc:
        flash(str(exc), "danger")
        # Se non c'è ancora diario, manda alla pipeline
        if exc.status_code in (404, 400):
            return redirect(
                url_for("diario_ui.pipeline_colloquio", consultation_id=consultation_id)
            )
        return redirect(url_for("patients.lista_pazienti"))

    patient_id = payload["patient"]["id"]
    return render_template(
        "admin/diario_review.html",
        consultation_id=consultation_id,
        patient_id=patient_id,
        payload=payload,
        contenuto=payload["diary_entry"]["contenuto_json"] or {},
    )


@diario_ui_bp.route("/pazienti/<int:patient_id>")
@_admin_required
def lista_diari_paziente(patient_id: int):
    """Redirect alla scheda paziente, tab Diario."""
    paziente = db.session.get(Patient, patient_id)
    if paziente is None:
        flash("Paziente non trovato", "danger")
        return redirect(url_for("patients.lista_pazienti"))
    return redirect(
        url_for("patients.dettaglio_paziente", patient_id=patient_id, tab="diario")
    )


@diario_ui_bp.route("/pazienti/<int:patient_id>/timeline")
@_admin_required
def timeline_paziente(patient_id: int):
    """Timeline cronologica + grafico peso."""
    utente_id = int(session["utente_id"])
    include_pending = request.args.get("include_pending") in ("1", "true", "on", "yes")
    date_from = request.args.get("from") or None
    date_to = request.args.get("to") or None
    page = request.args.get("page", 1, type=int) or 1

    try:
        timeline = get_patient_diary_timeline(
            patient_id=patient_id,
            utente_id=utente_id,
            include_pending=include_pending,
            date_from=date_from,
            date_to=date_to,
            page=page,
            per_page=20,
        )
        trends = get_patient_diary_trends(
            patient_id=patient_id,
            utente_id=utente_id,
            date_from=date_from,
            date_to=date_to,
        )
    except DiarioAudioError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("patients.dettaglio_paziente", patient_id=patient_id))

    paziente = db.session.get(Patient, patient_id)
    return render_template(
        "admin/diario_timeline.html",
        paziente=paziente,
        items=timeline["items"],
        page=timeline["page"],
        pages=timeline["pages"],
        has_next=timeline["has_next"],
        has_prev=timeline["has_prev"],
        include_pending=include_pending,
        date_from=date_from or "",
        date_to=date_to or "",
        trends_json=json.dumps(trends),
    )
