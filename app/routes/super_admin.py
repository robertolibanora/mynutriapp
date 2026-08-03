"""Area super admin: monitoraggio piattaforma (sola lettura + gestione stato)."""

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
    attention_subscribers,
    chart_payloads,
    list_subscribers,
    platform_kpis,
    signup_series,
    stripe_monitor_snapshot,
)
from app.services.utente_admin_service import (
    UtenteAdminError,
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
    subscribers = list_subscribers(limit=80)
    attention = attention_subscribers(subscribers)
    ctx = _nav_ctx()
    ctx["active_nav"] = "dashboard"
    return render_template(
        "super/dashboard.html",
        kpis=kpis,
        charts_json=json.dumps(charts),
        stripe=stripe,
        subscribers=subscribers,
        attention=attention,
        **ctx,
    )


@super_admin_bp.route("/utenti", methods=["GET"])
@super_admin_required
def lista_utenti():
    require_super_admin()
    utenti = list_nutrizionisti()
    subscribers = list_subscribers(limit=200)
    by_id = {s["id"]: s for s in subscribers}
    rows = []
    for u in utenti:
        extra = by_id.get(u.id) or {}
        rows.append(
            {
                "id": u.id,
                "nome": f"{u.nome} {u.cognome}".strip(),
                "telefono": u.telefono or "—",
                "email": u.email,
                "plan": u.plan,
                "attivo": bool(u.attivo),
                "subscription_status": extra.get("subscription_status")
                or u.subscription_status
                or "none",
                "pazienti_attivi": extra.get("pazienti_attivi", 0),
                "needs_password_setup": bool(u.needs_password_setup),
                "creato_il": u.creato_il,
            }
        )
    ctx = _nav_ctx()
    ctx["active_nav"] = "utenti"
    return render_template(
        "super/utenti.html",
        utenti=rows,
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
