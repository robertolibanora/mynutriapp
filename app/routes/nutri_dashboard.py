"""Dashboard minimale nutrizionista (tenant)."""

from __future__ import annotations

from functools import wraps

from flask import Blueprint, flash, redirect, render_template, session, url_for

from app.models.models import Patient
from app.services.licensing_service import get_subscription_usage
from app.utils.tenant import current_utente_id, require_nutrizionista

nutri_dashboard_bp = Blueprint("nutri_dashboard", __name__, url_prefix="/nutri")


def nutrizionista_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "nutrizionista":
            flash("Effettua il login come nutrizionista", "warning")
            return redirect(url_for("auth.login"))
        require_nutrizionista()
        return func(*args, **kwargs)

    return wrapper


@nutri_dashboard_bp.route("/")
@nutrizionista_required
def home():
    uid = current_utente_id()
    n_pazienti = Patient.query.filter_by(nutrizionista_id=uid).count()
    usage = get_subscription_usage(int(uid))
    return render_template(
        "super/nutri_home.html",
        n_pazienti=n_pazienti,
        usage=usage,
        admin_name=session.get("name") or "Nutrizionista",
    )


@nutri_dashboard_bp.route("/account")
@nutrizionista_required
def account():
    uid = current_utente_id()
    usage = get_subscription_usage(int(uid))
    return render_template(
        "super/nutri_account.html",
        usage=usage,
        admin_name=session.get("name") or "Nutrizionista",
    )
