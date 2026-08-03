"""Area super admin: monitoraggio piattaforma + gestione nutrizionisti."""

from __future__ import annotations

import json
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
from app.config.config import Config
from app.services.monitor_service import (
    chart_payloads,
    list_subscribers,
    platform_kpis,
    signup_series,
    stripe_monitor_snapshot,
)
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


def _nav_ctx() -> dict:
    return {
        "admin_name": session.get("name") or "Super Admin",
        "mail_url": Config.MONITOR_MAIL_URL,
        "stripe_dashboard_url": Config.MONITOR_STRIPE_DASHBOARD_URL,
        "active_nav": "",
    }


@super_admin_bp.route("/", methods=["GET"])
@super_admin_bp.route("/dashboard", methods=["GET"])
@super_admin_required
def dashboard():
    require_super_admin()
    kpis = platform_kpis()
    series = signup_series(weeks=8)
    charts = chart_payloads(kpis, series)
    stripe = stripe_monitor_snapshot(payment_limit=12)
    subscribers = list_subscribers(limit=50)
    ctx = _nav_ctx()
    ctx["active_nav"] = "dashboard"
    return render_template(
        "super/dashboard.html",
        kpis=kpis,
        charts_json=json.dumps(charts),
        stripe=stripe,
        subscribers=subscribers,
        **ctx,
    )


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
    ctx = _nav_ctx()
    ctx["active_nav"] = "utenti"
    return render_template(
        "super/utenti.html",
        utenti=utenti,
        plans=sorted(VALID_PLANS),
        **ctx,
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
