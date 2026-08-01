"""Route paziente residue (profilo) — blueprint name `patients` per url_for esistenti."""

from functools import wraps

from flask import Blueprint, flash, redirect, render_template, session, url_for

from app.models.models import Patient

patients_bp = Blueprint("patients", __name__)


def user_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "user":
            flash("Effettua il login come paziente", "warning")
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)

    return wrapper


@patients_bp.route("/user/profilo")
@user_required
def profilo_user():
    user_id = session.get("user_id")
    if not user_id:
        flash("Sessione non valida", "danger")
        return redirect(url_for("auth.login"))

    paziente = Patient.query.get_or_404(user_id)
    paziente.patologie = paziente.patologie_decrypted
    paziente.intolleranze = paziente.intolleranze_decrypted
    paziente.esami_biochimici = paziente.esami_biochimici_decrypted

    return render_template("user/profilo.html", paziente=paziente)
