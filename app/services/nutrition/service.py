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
    NutritionProviderError,
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
    def search_foods(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Cerca alimenti: prima nel DB locale, poi sul provider esterno."""
        query = (query or "").strip()
        if not query:
            return {"results": [], "warning": None}

        limit = max(1, min(int(limit or 10), 50))
        merged: List[Dict[str, Any]] = []
        seen: set = set()
        warning: Optional[str] = None

        for item in self._search_local_foods(query, limit):
            key = ("local", item.get("local_food_id"))
            if key not in seen:
                seen.add(key)
                merged.append(item)

        try:
            external = self.provider.search_foods(query, limit=limit)
            for food in external:
                key = (food.provider, food.external_id)
                if key not in seen:
                    seen.add(key)
                    merged.append(food.to_dict())
        except NutritionProviderError as exc:
            warning = str(exc)
            if not merged:
                raise
        except Exception as exc:
            warning = "Ricerca alimenti temporaneamente non disponibile."
            logger = __import__("logging").getLogger(__name__)
            logger.warning("Errore provider nutrizionale durante search: %s", exc)
            if not merged:
                raise NutritionServiceError(warning) from exc

        return {"results": merged[:limit], "warning": warning}

    def _search_local_foods(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Alimenti già salvati in DB (custom o importati in precedenza)."""
        pattern = f"%{query}%"
        foods = (
            Food.query.filter(
                db.or_(
                    Food.name.ilike(pattern),
                    Food.brand.ilike(pattern),
                )
            )
            .order_by(Food.is_custom.desc(), Food.name.asc())
            .limit(limit)
            .all()
        )
        out: List[Dict[str, Any]] = []
        for food in foods:
            d = food_to_dict(food)
            d["provider"] = food.provider or "local"
            d["external_id"] = str(food.id)
            d["local_food_id"] = food.id
            d["source"] = "local"
            out.append(d)
        return out

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

        # Alimento già locale (ricerca DB o custom): riusa per id.
        if provider_name == "local":
            food = db.session.get(Food, int(external_id))
            if food is None:
                raise ResourceNotFoundError(f"Alimento locale {external_id} inesistente")
            return food

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

    def update_diet_plan(self, diet_plan_id: int, data: Dict[str, Any]) -> DietPlan:
        """Aggiorna metadati del piano (es. bozza ↔ pubblicata)."""
        plan = db.session.get(DietPlan, diet_plan_id)
        if plan is None:
            raise ResourceNotFoundError(f"Piano dieta {diet_plan_id} inesistente")

        if "status" in data:
            status = (data.get("status") or "").strip()
            if status not in ("draft", "published"):
                raise NutritionServiceError("status deve essere 'draft' o 'published'")
            plan.status = status

        if "title" in data:
            title = (data.get("title") or "").strip()
            if title:
                plan.title = title

        if "goal" in data:
            plan.goal = (data.get("goal") or None)

        if "notes" in data:
            plan.notes = (data.get("notes") or None)

        self._apply_targets(plan, data)

        db.session.commit()
        return plan

    @staticmethod
    def _apply_targets(plan: DietPlan, data: Dict[str, Any]) -> None:
        """Aggiorna gli obiettivi nutrizionali del piano (kcal + % macro).

        Valori vuoti/None azzerano il campo. Le tre percentuali, se tutte
        presenti, devono sommare ~100 (tolleranza ±2).
        """

        def _num(key, lo, hi, integer=False):
            raw = data.get(key)
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                return None
            try:
                value = float(raw)
            except (TypeError, ValueError):
                raise NutritionServiceError(f"{key} deve essere un numero")
            if not (lo <= value <= hi):
                raise NutritionServiceError(f"{key} deve essere tra {lo} e {hi}")
            return int(round(value)) if integer else round(value, 2)

        if "target_kcal" in data:
            plan.target_kcal = _num("target_kcal", 1, 20000, integer=True)

        pct_fields = ("target_protein_pct", "target_carbs_pct", "target_fat_pct")
        touched = [f for f in pct_fields if f in data]
        for field in touched:
            setattr(plan, field, _num(field, 0, 100))

        if touched:
            pcts = [getattr(plan, f) for f in pct_fields]
            if all(p is not None for p in pcts):
                total = sum(float(p) for p in pcts)
                if abs(total - 100) > 2:
                    raise NutritionServiceError(
                        "Le percentuali dei macronutrienti devono sommare 100"
                        f" (attuale: {total:.0f})"
                    )

    def add_meal(self, diet_plan_id: int, data: Dict[str, Any]) -> DietMeal:
        plan = db.session.get(DietPlan, diet_plan_id)
        if plan is None:
            raise ResourceNotFoundError(f"Piano dieta {diet_plan_id} inesistente")

        meal_name = (data.get("meal_name") or "").strip()
        if not meal_name:
            raise NutritionServiceError("meal_name è obbligatorio")

        day_from, day_to = self._parse_day_range(data)

        meal = DietMeal(
            diet_plan_id=plan.id,
            day_index=day_from,
            day_index_to=day_to,
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
    # ELIMINAZIONE
    # ==================================================================
    def delete_diet_plan(self, diet_plan_id: int) -> int:
        """Elimina un piano alimentare e tutti i pasti/item collegati."""
        plan = db.session.get(DietPlan, diet_plan_id)
        if plan is None:
            raise ResourceNotFoundError(f"Piano dieta {diet_plan_id} inesistente")
        patient_id = plan.patient_id
        db.session.delete(plan)
        db.session.commit()
        return patient_id

    def delete_meal(self, meal_id: int) -> int:
        """Elimina un pasto e i suoi item."""
        meal = db.session.get(DietMeal, meal_id)
        if meal is None:
            raise ResourceNotFoundError(f"Pasto {meal_id} inesistente")
        plan_id = meal.diet_plan_id
        db.session.delete(meal)
        db.session.commit()
        return plan_id

    def delete_meal_item(self, item_id: int) -> int:
        """Elimina un alimento da un pasto."""
        item = db.session.get(DietMealItem, item_id)
        if item is None:
            raise ResourceNotFoundError(f"Alimento nel pasto {item_id} inesistente")
        meal_id = item.diet_meal_id
        db.session.delete(item)
        db.session.commit()
        return meal_id

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

    @classmethod
    def _parse_day_range(cls, data: Dict[str, Any]) -> tuple[int, int]:
        """Intervallo giorni 0-based da ``day_index`` / ``day_index_to``.

        Se manca ``day_index_to``, il pasto vale un solo giorno.
        """
        day_from = int(data.get("day_index") or 0)
        if day_from < 0:
            raise NutritionServiceError("day_index non può essere negativo")

        if data.get("day_index_to") is None or data.get("day_index_to") == "":
            day_to = day_from
        else:
            day_to = int(data.get("day_index_to"))

        if day_to < day_from:
            raise NutritionServiceError("day_index_to deve essere >= day_index")
        return day_from, day_to

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
        "target_kcal": plan.target_kcal,
        "target_protein_pct": float(plan.target_protein_pct) if plan.target_protein_pct is not None else None,
        "target_carbs_pct": float(plan.target_carbs_pct) if plan.target_carbs_pct is not None else None,
        "target_fat_pct": float(plan.target_fat_pct) if plan.target_fat_pct is not None else None,
    }


def diet_meal_to_dict(meal: DietMeal) -> Dict[str, Any]:
    return {
        "id": meal.id,
        "diet_plan_id": meal.diet_plan_id,
        "day_index": meal.day_index,
        "day_index_to": meal.day_index_to,
        "day_label": meal.day_label,
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
