"""Vista paziente read-only del piano alimentare strutturato."""

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


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "user":
            flash("Effettua il login", "warning")
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)

    return wrapper


@diete_plans_bp.before_request
def _ensure_schema():
    ensure_nutrition_schema()


def _build_totals(plan: DietPlan) -> dict:
    meal_totals = {}
    item_totals = {}
    for meal in plan.meals:
        meal_totals[meal.id] = NutritionCalculatorService.compute_meal(meal.items)
        for item in meal.items:
            item_totals[item.id] = NutritionCalculatorService.compute_item(
                item.food, item.quantity_g
            )
    plan_totals = NutritionCalculatorService.compute_plan(plan.meals)
    return {
        "plan": plan_totals,
        "meal": meal_totals,
        "item": item_totals,
        "perc": NutritionCalculatorService.macro_percentages(plan_totals["total"]),
    }


def _build_targets(plan: DietPlan) -> dict | None:
    if not plan.target_kcal:
        return None
    calc = NutritionCalculatorService
    return {
        "kcal": plan.target_kcal,
        "protein_pct": float(plan.target_protein_pct) if plan.target_protein_pct is not None else None,
        "carbs_pct": float(plan.target_carbs_pct) if plan.target_carbs_pct is not None else None,
        "fat_pct": float(plan.target_fat_pct) if plan.target_fat_pct is not None else None,
        "protein_g": calc.target_grams(plan.target_kcal, plan.target_protein_pct, 4),
        "carbs_g": calc.target_grams(plan.target_kcal, plan.target_carbs_pct, 4),
        "fat_g": calc.target_grams(plan.target_kcal, plan.target_fat_pct, 9),
    }


@diete_plans_bp.route("/paziente/diet-plans/<int:diet_plan_id>")
@login_required
def user_diet_plan(diet_plan_id):
    plan = DietPlan.query.get_or_404(diet_plan_id)

    if plan.patient_id != session.get("user_id"):
        abort(403)
    if plan.status != "published":
        abort(404)

    paziente = Patient.query.get_or_404(plan.patient_id)
    return render_template(
        "user/diet_plan_detail.html",
        plan=plan,
        paziente=paziente,
        totals=_build_totals(plan),
        targets=_build_targets(plan),
        is_preview=False,
    )
