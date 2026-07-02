"""Pagine HTML per i piani alimentari strutturati (nuovo flusso dieta).

Queste view renderizzano solo le pagine: tutte le mutazioni (creazione
piano/pasto/item, ricerca e import alimenti) passano dalle API JSON già
esistenti sotto ``/api/admin/...``. Il calcolo dei totali per il rendering
iniziale usa :class:`NutritionCalculatorService`.

Il vecchio flusso dieta-PDF (blueprint ``diete``) resta intatto.
"""

from __future__ import annotations

from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    session,
    url_for,
)

from app.models.models import DietPlan, Patient
from app.services.nutrition import NutritionCalculatorService
from app.utils.db_schema import ensure_nutrition_schema

diete_plans_bp = Blueprint("diete_plans", __name__)


# ========================
# DECORATORI DI PROTEZIONE
# ========================

def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)

    return wrapper


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") not in ("admin", "user"):
            flash("Effettua il login", "warning")
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)

    return wrapper


@diete_plans_bp.before_request
def _ensure_schema():
    ensure_nutrition_schema()


# ========================
# VIEW MODEL TOTALI
# ========================

def _build_totals(plan: DietPlan) -> dict:
    """Prepara i totali (dieta, per pasto, per item) per il template."""
    meal_totals = {}
    item_totals = {}
    for meal in plan.meals:
        meal_totals[meal.id] = NutritionCalculatorService.compute_meal(meal.items)
        for item in meal.items:
            item_totals[item.id] = NutritionCalculatorService.compute_item(
                item.food, item.quantity_g
            )
    plan_totals = NutritionCalculatorService.compute_plan(plan.meals)
    # NB: niente chiave "items"/"meals" per non collidere con dict.items()/.meals in Jinja.
    return {
        "plan": plan_totals,
        "meal": meal_totals,
        "item": item_totals,
    }


# ========================
# ADMIN: CREA DIETA (pagina)
# ========================

@diete_plans_bp.route("/admin/pazienti/<int:patient_id>/diet-plans/new")
@admin_required
def new_diet_plan(patient_id):
    """Pagina di creazione di un nuovo piano alimentare per il paziente."""
    paziente = Patient.query.get_or_404(patient_id)
    return render_template("admin/diet_plan_new.html", paziente=paziente)


# ========================
# ADMIN: DETTAGLIO/BUILDER DIETA
# ========================

@diete_plans_bp.route("/admin/diet-plans/<int:diet_plan_id>")
@admin_required
def diet_plan_detail(diet_plan_id):
    """Dettaglio e builder del piano: pasti, alimenti, totali."""
    plan = DietPlan.query.get_or_404(diet_plan_id)
    paziente = Patient.query.get_or_404(plan.patient_id)
    totals = _build_totals(plan)
    return render_template(
        "admin/diet_plan_detail.html",
        plan=plan,
        paziente=paziente,
        totals=totals,
    )


# ========================
# PAZIENTE: VISTA DIETA (read-only)
# ========================

@diete_plans_bp.route("/paziente/diet-plans/<int:diet_plan_id>")
@login_required
def user_diet_plan(diet_plan_id):
    """Vista read-only del piano.

    - Il paziente vede SOLO i propri piani.
    - L'admin può aprire qualsiasi piano come anteprima.
    """
    plan = DietPlan.query.get_or_404(diet_plan_id)

    role = session.get("role")
    if role == "user":
        if plan.patient_id != session.get("user_id"):
            abort(403)
        if plan.status != "published":
            abort(404)
    elif role != "admin":
        abort(403)

    paziente = Patient.query.get_or_404(plan.patient_id)
    totals = _build_totals(plan)
    is_preview = role == "admin"
    return render_template(
        "user/diet_plan_detail.html",
        plan=plan,
        paziente=paziente,
        totals=totals,
        is_preview=is_preview,
    )
