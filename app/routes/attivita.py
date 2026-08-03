"""Sezione Attività — inbox operativa multi-tenant."""

from datetime import datetime

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.models.models import Patient, db
from app.services.activity_service import (
    build_inbox,
    complete_activity,
    create_manual_activity,
    delete_activity,
    reopen_activity,
)
from app.utils.db_schema import ensure_activity_notes_schema
from app.utils.tenant import patients_query_for_tenant, tenant_filter_enabled

attivita_bp = Blueprint("attivita", __name__, url_prefix="/admin/attivita")


def admin_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") not in ("admin", "nutrizionista"):
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)

    return wrapper


@attivita_bp.before_request
def _ensure_schema():
    ensure_activity_notes_schema()


@attivita_bp.route("/")
@admin_required
def lista_attivita():
    bucket = (request.args.get("bucket") or "oggi").strip()
    if bucket not in ("oggi", "ritardo", "prossime", "completate"):
        bucket = "oggi"
    inbox = build_inbox(bucket=bucket)
    pazienti = (
        patients_query_for_tenant() if tenant_filter_enabled() else Patient.query
    ).order_by(Patient.cognome.asc(), Patient.nome.asc()).limit(200).all()
    return render_template(
        "admin/attivita.html",
        items=inbox["items"],
        counts=inbox["counts"],
        bucket=bucket,
        pazienti=pazienti,
    )


@attivita_bp.route("/nuova", methods=["POST"])
@admin_required
def nuova_attivita():
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Inserisci un titolo per l'attività", "warning")
        return redirect(url_for("attivita.lista_attivita"))

    patient_id = request.form.get("patient_id") or None
    if patient_id:
        try:
            patient_id = int(patient_id)
        except ValueError:
            patient_id = None

    due_raw = (request.form.get("due_at") or "").strip()
    due_at = None
    if due_raw:
        try:
            due_at = datetime.strptime(due_raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            try:
                due_at = datetime.strptime(due_raw, "%Y-%m-%d")
            except ValueError:
                due_at = None

    priority = request.form.get("priority") or "medium"
    notes = (request.form.get("notes") or "").strip() or None

    try:
        create_manual_activity(
            title=title,
            patient_id=patient_id,
            due_at=due_at,
            priority=priority,
            notes=notes,
        )
        db.session.commit()
        flash("Attività creata", "success")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        flash(f"Errore: {exc}", "danger")

    return redirect(url_for("attivita.lista_attivita", bucket="prossime"))


@attivita_bp.route("/<int:activity_id>/completa", methods=["POST"])
@admin_required
def completa(activity_id):
    try:
        complete_activity(activity_id)
        db.session.commit()
        flash("Attività completata", "success")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        flash(f"Errore: {exc}", "danger")
    return redirect(request.referrer or url_for("attivita.lista_attivita"))


@attivita_bp.route("/<int:activity_id>/riapri", methods=["POST"])
@admin_required
def riapri(activity_id):
    try:
        reopen_activity(activity_id)
        db.session.commit()
        flash("Attività riaperta", "success")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        flash(f"Errore: {exc}", "danger")
    return redirect(request.referrer or url_for("attivita.lista_attivita", bucket="completate"))


@attivita_bp.route("/<int:activity_id>/elimina", methods=["POST"])
@admin_required
def elimina(activity_id):
    try:
        delete_activity(activity_id)
        db.session.commit()
        flash("Attività eliminata", "success")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        flash(f"Errore: {exc}", "danger")
    return redirect(request.referrer or url_for("attivita.lista_attivita"))
