"""Area super admin: creazione nutrizionisti (tenant)."""

from __future__ import annotations

from functools import wraps

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.billing.plans import VALID_PLANS
from app.services.utente_admin_service import (
    NutrizionistaCreate,
    UtenteAdminError,
    create_nutrizionista,
    list_nutrizionisti,
    set_nutrizionista_plan,
    toggle_nutrizionista,
)
from app.utils.tenant import require_super_admin

super_admin_bp = Blueprint("super_admin", __name__, url_prefix="/super")


def super_admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "super_admin":
            flash("Accesso riservato al super admin", "danger")
            return redirect(url_for("auth.login"))
        require_super_admin()
        return func(*args, **kwargs)

    return wrapper


@super_admin_bp.route("/utenti", methods=["GET", "POST"])
@super_admin_required
def lista_utenti():
    creator_id = require_super_admin()

    if request.method == "POST":
        try:
            create_nutrizionista(
                NutrizionistaCreate(
                    nome=request.form.get("nome") or "",
                    cognome=request.form.get("cognome") or "",
                    telefono=request.form.get("telefono") or "",
                    email=request.form.get("email") or "",
                    password=request.form.get("password") or "",
                    attivo=True,
                    plan=request.form.get("plan") or "starter",
                ),
                creato_da=creator_id,
            )
            flash("Nutrizionista creato", "success")
        except UtenteAdminError as exc:
            flash(str(exc), "danger")
        return redirect(url_for("super_admin.lista_utenti"))

    utenti = list_nutrizionisti()
    return render_template(
        "super/utenti.html",
        utenti=utenti,
        plans=sorted(VALID_PLANS),
        admin_name=session.get("name") or "Super Admin",
    )


@super_admin_bp.route("/utenti/<int:utente_id>/toggle", methods=["POST"])
@super_admin_required
def toggle_utente(utente_id: int):
    require_super_admin()
    try:
        row = toggle_nutrizionista(utente_id)
        stato = "attivato" if row.attivo else "disattivato"
        flash(f"Utente {stato}", "success")
    except UtenteAdminError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("super_admin.lista_utenti"))


@super_admin_bp.route("/utenti/<int:utente_id>/plan", methods=["POST"])
@super_admin_required
def set_utente_plan(utente_id: int):
    require_super_admin()
    try:
        row = set_nutrizionista_plan(utente_id, request.form.get("plan") or "")
        flash(f"Piano aggiornato: {row.plan}", "success")
    except UtenteAdminError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("super_admin.lista_utenti"))
