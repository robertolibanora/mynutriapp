"""Servizio applicativo per alimenti e diete.

Fa da unico punto di ingresso per i router: ricerca alimenti (via provider),
import/riuso di alimenti locali, creazione alimenti custom, gestione del
piano alimentare e calcolo dei totali. La logica di business NON deve vivere
nei router.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.models import (
    DietMeal,
    DietMealItem,
    DietPlan,
    Food,
    Patient,
    db,
)

from .calculator import NUTRIENTS, NutritionCalculatorService
from .providers import (
    NutritionProvider,
    get_nutrition_provider,
)
from .schemas import NormalizedFood

_PER_100G_FIELDS = tuple(NUTRIENTS.values())


class NutritionServiceError(Exception):
    """Errore di validazione/dominio del servizio nutrizionale."""


class ResourceNotFoundError(NutritionServiceError):
    """Risorsa locale (paziente, piano, pasto, alimento) inesistente."""


class NutritionService:
    """Coordina provider esterni, persistenza locale e calcolo nutrienti."""

    def __init__(self, provider: Optional[NutritionProvider] = None) -> None:
        # Provider iniettabile per i test; altrimenti risolto dalla factory.
        self._provider = provider

    @property
    def provider(self) -> NutritionProvider:
        if self._provider is None:
            self._provider = get_nutrition_provider()
        return self._provider

    # ==================================================================
    # RICERCA (provider esterno)
    # ==================================================================
    def search_foods(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Cerca alimenti tramite il provider e ritorna risultati normalizzati."""
        results = self.provider.search_foods(query, limit=limit)
        return [food.to_dict() for food in results]

    # ==================================================================
    # IMPORT / RIUSO ALIMENTO LOCALE
    # ==================================================================
    def import_food(self, provider_name: str, external_id: str) -> Food:
        """Importa (o riusa) un alimento da un provider esterno.

        Se esiste già un Food con lo stesso ``provider`` + ``external_id``
        viene riutilizzato senza richiamare l'API. Il payload originale è
        salvato in ``source_payload_json``.
        """
        provider_name = (provider_name or "").strip().lower()
        external_id = (external_id or "").strip()
        if not provider_name or not external_id:
            raise NutritionServiceError("provider ed external_id sono obbligatori")

        existing = Food.query.filter_by(
            provider=provider_name, external_id=external_id
        ).first()
        if existing is not None:
            return existing

        # Usa il provider iniettato (test/uso avanzato) o quello risolto per nome.
        provider = self._provider or get_nutrition_provider(provider_name)
        normalized = provider.get_food_details(external_id)

        food = self._food_from_normalized(normalized)
        db.session.add(food)
        db.session.commit()
        return food

    def _food_from_normalized(self, normalized: NormalizedFood) -> Food:
        return Food(
            provider=normalized.provider,
            external_id=normalized.external_id,
            name=normalized.name,
            brand=normalized.brand,
            category=normalized.category,
            serving_size=normalized.serving_size,
            serving_unit=normalized.serving_unit,
            kcal_per_100g=normalized.kcal_per_100g,
            protein_per_100g=normalized.protein_per_100g,
            carbs_per_100g=normalized.carbs_per_100g,
            sugars_per_100g=normalized.sugars_per_100g,
            fat_per_100g=normalized.fat_per_100g,
            saturated_fat_per_100g=normalized.saturated_fat_per_100g,
            fiber_per_100g=normalized.fiber_per_100g,
            salt_per_100g=normalized.salt_per_100g,
            sodium_per_100g=normalized.sodium_per_100g,
            source_payload_json=normalized.source_payload,
            is_custom=False,
        )

    # ==================================================================
    # ALIMENTO CUSTOM
    # ==================================================================
    def create_custom_food(self, data: Dict[str, Any], professional_id: Optional[int] = None) -> Food:
        """Crea un alimento custom con valori nutrizionali manuali."""
        name = (data.get("name") or "").strip()
        if not name:
            raise NutritionServiceError("Il campo 'name' è obbligatorio")

        food = Food(
            professional_id=professional_id,
            provider=None,
            external_id=None,
            name=name,
            brand=(data.get("brand") or None),
            category=(data.get("category") or None),
            serving_size=self._num(data.get("serving_size")),
            serving_unit=(data.get("serving_unit") or None),
            is_custom=True,
        )
        for field in _PER_100G_FIELDS:
            setattr(food, field, self._num(data.get(field)))

        db.session.add(food)
        db.session.commit()
        return food

    # ==================================================================
    # PIANO ALIMENTARE
    # ==================================================================
    def create_diet_plan(self, data: Dict[str, Any], professional_id: Optional[int] = None) -> DietPlan:
        patient_id = data.get("patient_id")
        title = (data.get("title") or "").strip()
        if not patient_id:
            raise NutritionServiceError("patient_id è obbligatorio")
        if not title:
            raise NutritionServiceError("title è obbligatorio")

        if db.session.get(Patient, patient_id) is None:
            raise ResourceNotFoundError(f"Paziente {patient_id} inesistente")

        plan = DietPlan(
            patient_id=patient_id,
            professional_id=professional_id,
            title=title,
            goal=(data.get("goal") or None),
            notes=(data.get("notes") or None),
            status=(data.get("status") or "draft"),
        )
        db.session.add(plan)
        db.session.commit()
        return plan

    def add_meal(self, diet_plan_id: int, data: Dict[str, Any]) -> DietMeal:
        plan = db.session.get(DietPlan, diet_plan_id)
        if plan is None:
            raise ResourceNotFoundError(f"Piano dieta {diet_plan_id} inesistente")

        meal_name = (data.get("meal_name") or "").strip()
        if not meal_name:
            raise NutritionServiceError("meal_name è obbligatorio")

        meal = DietMeal(
            diet_plan_id=plan.id,
            day_index=int(data.get("day_index") or 0),
            meal_name=meal_name,
            meal_time=self._parse_time(data.get("meal_time")),
            notes=(data.get("notes") or None),
        )
        db.session.add(meal)
        db.session.commit()
        return meal

    def add_meal_item(self, meal_id: int, data: Dict[str, Any]) -> DietMealItem:
        meal = db.session.get(DietMeal, meal_id)
        if meal is None:
            raise ResourceNotFoundError(f"Pasto {meal_id} inesistente")

        food_id = data.get("food_id")
        if not food_id:
            raise NutritionServiceError("food_id è obbligatorio")
        if db.session.get(Food, food_id) is None:
            raise ResourceNotFoundError(f"Alimento {food_id} inesistente")

        quantity_g = self._num(data.get("quantity_g"))
        if quantity_g is None or quantity_g <= 0:
            raise NutritionServiceError("quantity_g deve essere un numero positivo")

        item = DietMealItem(
            diet_meal_id=meal.id,
            food_id=food_id,
            quantity_g=quantity_g,
            notes=(data.get("notes") or None),
        )
        db.session.add(item)
        db.session.commit()
        return item

    # ==================================================================
    # TOTALI (delegati al calcolatore)
    # ==================================================================
    def meal_totals(self, meal_id: int) -> Dict[str, Any]:
        meal = db.session.get(DietMeal, meal_id)
        if meal is None:
            raise ResourceNotFoundError(f"Pasto {meal_id} inesistente")
        return NutritionCalculatorService.compute_meal(meal.items)

    def plan_totals(self, diet_plan_id: int) -> Dict[str, Any]:
        plan = db.session.get(DietPlan, diet_plan_id)
        if plan is None:
            raise ResourceNotFoundError(f"Piano dieta {diet_plan_id} inesistente")
        return NutritionCalculatorService.compute_plan(plan.meals)

    # ==================================================================
    # Helper
    # ==================================================================
    @staticmethod
    def _num(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            if isinstance(value, str):
                value = value.strip().replace(",", ".")
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_time(value: Any):
        if not value:
            return None
        if hasattr(value, "hour"):
            return value
        from datetime import datetime

        text = str(value).strip()
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(text, fmt).time()
            except ValueError:
                continue
        return None


# ==================================================================
# Serializzazione modelli -> dict (per le risposte API)
# ==================================================================

def food_to_dict(food: Food) -> Dict[str, Any]:
    return {
        "id": food.id,
        "professional_id": food.professional_id,
        "provider": food.provider,
        "external_id": food.external_id,
        "name": food.name,
        "brand": food.brand,
        "category": food.category,
        "serving_size": _decimal(food.serving_size),
        "serving_unit": food.serving_unit,
        "kcal_per_100g": _decimal(food.kcal_per_100g),
        "protein_per_100g": _decimal(food.protein_per_100g),
        "carbs_per_100g": _decimal(food.carbs_per_100g),
        "sugars_per_100g": _decimal(food.sugars_per_100g),
        "fat_per_100g": _decimal(food.fat_per_100g),
        "saturated_fat_per_100g": _decimal(food.saturated_fat_per_100g),
        "fiber_per_100g": _decimal(food.fiber_per_100g),
        "salt_per_100g": _decimal(food.salt_per_100g),
        "sodium_per_100g": _decimal(food.sodium_per_100g),
        "is_custom": bool(food.is_custom),
    }


def diet_plan_to_dict(plan: DietPlan) -> Dict[str, Any]:
    return {
        "id": plan.id,
        "patient_id": plan.patient_id,
        "professional_id": plan.professional_id,
        "title": plan.title,
        "goal": plan.goal,
        "notes": plan.notes,
        "status": plan.status,
    }


def diet_meal_to_dict(meal: DietMeal) -> Dict[str, Any]:
    return {
        "id": meal.id,
        "diet_plan_id": meal.diet_plan_id,
        "day_index": meal.day_index,
        "meal_name": meal.meal_name,
        "meal_time": meal.meal_time.strftime("%H:%M") if meal.meal_time else None,
        "notes": meal.notes,
    }


def diet_meal_item_to_dict(item: DietMealItem) -> Dict[str, Any]:
    return {
        "id": item.id,
        "diet_meal_id": item.diet_meal_id,
        "food_id": item.food_id,
        "quantity_g": _decimal(item.quantity_g),
        "notes": item.notes,
        "computed": NutritionCalculatorService.compute_item(item.food, item.quantity_g),
    }


def _decimal(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
