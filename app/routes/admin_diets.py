"""API admin per la gestione dei piani alimentari strutturati.

Crea piani, pasti e item; espone i totali aggregati (pasto/dieta). Tutta la
logica è delegata a :class:`NutritionService` e al calcolatore.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.routes.admin_nutrition import api_admin_required, handle_service_errors
from app.services.nutrition import (
    NutritionService,
    diet_meal_item_to_dict,
    diet_meal_to_dict,
    diet_plan_to_dict,
)
from app.utils.db_schema import ensure_nutrition_schema

admin_diets_bp = Blueprint("admin_diets", __name__, url_prefix="/api/admin")


@admin_diets_bp.before_request
def _ensure_schema():
    ensure_nutrition_schema()


def _current_professional_id():
    from flask import session

    return session.get("professional_id")


# ========================
# PIANI ALIMENTARI
# ========================

@admin_diets_bp.route("/diet-plans", methods=["POST"])
@api_admin_required
@handle_service_errors
def create_diet_plan():
    """POST /api/admin/diet-plans — crea un piano per un paziente."""
    data = request.get_json(silent=True) or {}
    plan = NutritionService().create_diet_plan(data, professional_id=_current_professional_id())
    return jsonify({"diet_plan": diet_plan_to_dict(plan)}), 201


@admin_diets_bp.route("/diet-plans/<int:diet_plan_id>/meals", methods=["POST"])
@api_admin_required
@handle_service_errors
def add_meal(diet_plan_id):
    """POST /api/admin/diet-plans/{id}/meals — aggiunge un pasto."""
    data = request.get_json(silent=True) or {}
    meal = NutritionService().add_meal(diet_plan_id, data)
    return jsonify({"meal": diet_meal_to_dict(meal)}), 201


@admin_diets_bp.route("/diet-meals/<int:meal_id>/items", methods=["POST"])
@api_admin_required
@handle_service_errors
def add_meal_item(meal_id):
    """POST /api/admin/diet-meals/{id}/items — aggiunge alimento + quantità."""
    data = request.get_json(silent=True) or {}
    item = NutritionService().add_meal_item(meal_id, data)
    return jsonify({"item": diet_meal_item_to_dict(item)}), 201


@admin_diets_bp.route("/diet-plans/<int:diet_plan_id>", methods=["PATCH"])
@api_admin_required
@handle_service_errors
def update_diet_plan(diet_plan_id):
    """PATCH /api/admin/diet-plans/{id} — aggiorna metadati (stato, titolo, …)."""
    data = request.get_json(silent=True) or {}
    plan = NutritionService().update_diet_plan(diet_plan_id, data)
    return jsonify({"diet_plan": diet_plan_to_dict(plan)})


@admin_diets_bp.route("/diet-plans/<int:diet_plan_id>", methods=["DELETE"])
@api_admin_required
@handle_service_errors
def delete_diet_plan(diet_plan_id):
    """DELETE /api/admin/diet-plans/{id} — elimina piano alimentare."""
    patient_id = NutritionService().delete_diet_plan(diet_plan_id)
    return jsonify({"deleted": True, "patient_id": patient_id})


@admin_diets_bp.route("/diet-meals/<int:meal_id>", methods=["DELETE"])
@api_admin_required
@handle_service_errors
def delete_meal(meal_id):
    """DELETE /api/admin/diet-meals/{id} — elimina pasto."""
    plan_id = NutritionService().delete_meal(meal_id)
    return jsonify({"deleted": True, "diet_plan_id": plan_id})


@admin_diets_bp.route("/diet-meal-items/<int:item_id>", methods=["DELETE"])
@api_admin_required
@handle_service_errors
def delete_meal_item(item_id):
    """DELETE /api/admin/diet-meal-items/{id} — rimuove alimento dal pasto."""
    meal_id = NutritionService().delete_meal_item(item_id)
    return jsonify({"deleted": True, "meal_id": meal_id})


# ========================
# TOTALI AGGREGATI
# ========================

@admin_diets_bp.route("/diet-plans/<int:diet_plan_id>/totals", methods=["GET"])
@api_admin_required
@handle_service_errors
def diet_plan_totals(diet_plan_id):
    """GET /api/admin/diet-plans/{id}/totals — totali dieta + per giorno."""
    totals = NutritionService().plan_totals(diet_plan_id)
    return jsonify({"diet_plan_id": diet_plan_id, "totals": totals})


@admin_diets_bp.route("/diet-meals/<int:meal_id>/totals", methods=["GET"])
@api_admin_required
@handle_service_errors
def diet_meal_totals(meal_id):
    """GET /api/admin/diet-meals/{id}/totals — totali pasto."""
    totals = NutritionService().meal_totals(meal_id)
    return jsonify({"meal_id": meal_id, "totals": totals})
