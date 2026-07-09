"""API admin per ricerca alimenti, import e alimenti custom.

I router restano "sottili": validano l'input, delegano a
:class:`NutritionService` e serializzano la risposta. Nessuna logica di
calcolo o di rete vive qui.
"""

from __future__ import annotations

from functools import wraps

from flask import Blueprint, jsonify, request, session

from app.services.nutrition import (
    FoodNotFoundError,
    NutritionService,
    NutritionServiceError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ResourceNotFoundError,
    UnsupportedProviderError,
    food_to_dict,
)
from app.utils.db_schema import ensure_nutrition_schema

admin_nutrition_bp = Blueprint("admin_nutrition", __name__, url_prefix="/api/admin")


# ========================
# AUTH + SCHEMA (JSON)
# ========================

def api_admin_required(func):
    """Consente l'accesso solo all'admin; risponde in JSON (no redirect)."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            return jsonify({"error": "Accesso non autorizzato"}), 403
        return func(*args, **kwargs)

    return wrapper


@admin_nutrition_bp.before_request
def _ensure_schema():
    ensure_nutrition_schema()


def _current_professional_id():
    """ID del professionista corrente (admin). Nel modello attuale è opzionale."""
    return session.get("professional_id")


# ========================
# GESTIONE ERRORI CENTRALIZZATA
# ========================

def handle_service_errors(func):
    """Mappa le eccezioni del servizio su risposte HTTP chiare."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except UnsupportedProviderError as exc:
            return jsonify({"error": str(exc)}), 400
        except ResourceNotFoundError as exc:
            return jsonify({"error": str(exc)}), 404
        except FoodNotFoundError as exc:
            return jsonify({"error": str(exc)}), 404
        except NutritionServiceError as exc:
            return jsonify({"error": str(exc)}), 400
        except ProviderTimeoutError as exc:
            return jsonify({"error": str(exc)}), 504
        except ProviderUnavailableError as exc:
            return jsonify({"error": str(exc)}), 502

    return wrapper


# ========================
# ENDPOINTS
# ========================

@admin_nutrition_bp.route("/nutrition/search", methods=["GET"])
@api_admin_required
@handle_service_errors
def search_foods():
    """GET /api/admin/nutrition/search?q=...&limit=... — ricerca normalizzata."""
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "Parametro 'q' obbligatorio"}), 400

    try:
        limit = int(request.args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    limit = max(1, min(limit, 50))

    payload = NutritionService().search_foods(query, limit=limit)
    results = payload.get("results") or []
    response = {"query": query, "count": len(results), "results": results}
    if payload.get("warning"):
        response["warning"] = payload["warning"]
    return jsonify(response)


@admin_nutrition_bp.route("/foods/import", methods=["POST"])
@api_admin_required
@handle_service_errors
def import_food():
    """POST /api/admin/foods/import — importa/riusa alimento locale."""
    data = request.get_json(silent=True) or {}
    provider = data.get("provider")
    external_id = data.get("external_id")
    if not provider or not external_id:
        return jsonify({"error": "'provider' ed 'external_id' sono obbligatori"}), 400

    food = NutritionService().import_food(provider, external_id)
    return jsonify({"food": food_to_dict(food)}), 200


@admin_nutrition_bp.route("/foods/custom", methods=["POST"])
@api_admin_required
@handle_service_errors
def create_custom_food():
    """POST /api/admin/foods/custom — crea alimento manuale."""
    data = request.get_json(silent=True) or {}
    food = NutritionService().create_custom_food(data, professional_id=_current_professional_id())
    return jsonify({"food": food_to_dict(food)}), 201
