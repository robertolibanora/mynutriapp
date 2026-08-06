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


class TenantForbiddenError(NutritionServiceError):
    """Accesso a risorsa di un altro tenant."""


def _assert_patient_tenant_access(patient: Patient) -> None:
    """Negazione accesso se il paziente non appartiene al tenant corrente."""
    from app.utils.tenant import (
        current_utente_id,
        is_staff_role,
        tenant_filter_enabled,
    )

    if not tenant_filter_enabled() or not is_staff_role():
        return
    uid = current_utente_id()
    if not uid or getattr(patient, "nutrizionista_id", None) != uid:
        raise TenantForbiddenError("Accesso negato a paziente di altro professionista")


def _assert_plan_tenant_access(plan: DietPlan) -> None:
    from app.utils.tenant import current_utente_id, is_staff_role, tenant_filter_enabled

    if not tenant_filter_enabled() or not is_staff_role():
        return
    uid = current_utente_id()
    if not uid:
        raise TenantForbiddenError("Accesso negato")
    patient = getattr(plan, "patient", None) or db.session.get(Patient, plan.patient_id)
    if patient is None:
        raise ResourceNotFoundError(f"Paziente {plan.patient_id} inesistente")
    _assert_patient_tenant_access(patient)
    professional_id = getattr(plan, "professional_id", None)
    if professional_id is not None and int(professional_id) != uid:
        raise TenantForbiddenError("Accesso negato a piano di altro professionista")


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
        from app.utils.tenant import current_professional_id, tenant_filter_enabled

        pattern = f"%{query}%"
        q = Food.query.filter(
            db.or_(
                Food.name.ilike(pattern),
                Food.brand.ilike(pattern),
            )
        )
        if tenant_filter_enabled():
            pid = current_professional_id()
            # Catalogo globale (professional_id NULL) + custom del tenant
            q = q.filter(
                db.or_(Food.professional_id.is_(None), Food.professional_id == pid)
            )
        foods = (
            q.order_by(Food.is_custom.desc(), Food.name.asc())
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

        patient = db.session.get(Patient, patient_id)
        if patient is None:
            raise ResourceNotFoundError(f"Paziente {patient_id} inesistente")
        _assert_patient_tenant_access(patient)

        status = (data.get("status") or "draft").strip()
        if status not in ("draft", "published"):
            raise NutritionServiceError("status deve essere 'draft' o 'published'")
        if status == "published":
            self._assert_plan_limit_for_patient(patient)

        plan = DietPlan(
            patient_id=patient_id,
            professional_id=professional_id,
            title=title,
            goal=(data.get("goal") or None),
            notes=(data.get("notes") or None),
            status=status,
        )
        db.session.add(plan)
        db.session.commit()
        return plan

    def update_diet_plan(self, diet_plan_id: int, data: Dict[str, Any]) -> DietPlan:
        """Aggiorna metadati del piano (es. bozza ↔ pubblicata)."""
        plan = db.session.get(DietPlan, diet_plan_id)
        if plan is None:
            raise ResourceNotFoundError(f"Piano dieta {diet_plan_id} inesistente")
        _assert_plan_tenant_access(plan)

        if "status" in data:
            status = (data.get("status") or "").strip()
            if status not in ("draft", "published"):
                raise NutritionServiceError("status deve essere 'draft' o 'published'")
            if status == "published" and plan.status != "published":
                patient = db.session.get(Patient, plan.patient_id)
                if patient is None:
                    raise ResourceNotFoundError(f"Paziente {plan.patient_id} inesistente")
                self._assert_plan_limit_for_patient(patient)
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
    def _assert_plan_limit_for_patient(patient: Patient) -> None:
        from app.services.licensing_service import assert_can_increase_active_patients

        nutri_id = getattr(patient, "nutrizionista_id", None)
        if nutri_id is None:
            return
        assert_can_increase_active_patients(int(nutri_id), patient_id=int(patient.id))

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
        _assert_plan_tenant_access(plan)

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
        plan = db.session.get(DietPlan, meal.diet_plan_id)
        if plan is not None:
            _assert_plan_tenant_access(plan)

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

    def update_meal_item(self, item_id: int, data: Dict[str, Any]) -> DietMealItem:
        """Aggiorna la quantità (grammi) di un alimento nel pasto."""
        item = db.session.get(DietMealItem, item_id)
        if item is None:
            raise ResourceNotFoundError(f"Alimento nel pasto {item_id} inesistente")
        meal = db.session.get(DietMeal, item.diet_meal_id)
        if meal is not None:
            plan = db.session.get(DietPlan, meal.diet_plan_id)
            if plan is not None:
                _assert_plan_tenant_access(plan)

        if "quantity_g" not in data:
            raise NutritionServiceError("quantity_g è obbligatorio")
        quantity_g = self._num(data.get("quantity_g"))
        if quantity_g is None or quantity_g <= 0:
            raise NutritionServiceError("quantity_g deve essere un numero positivo")

        item.quantity_g = quantity_g
        if "notes" in data:
            item.notes = data.get("notes") or None
        db.session.commit()
        return item

    def ensure_day_meals(self, diet_plan_id: int, data: Dict[str, Any]) -> List[DietMeal]:
        """Crea i pasti mancanti per un giorno (1-based in input)."""
        plan = db.session.get(DietPlan, diet_plan_id)
        if plan is None:
            raise ResourceNotFoundError(f"Piano dieta {diet_plan_id} inesistente")
        _assert_plan_tenant_access(plan)

        day_1based = int(data.get("day") or 1)
        if day_1based < 1:
            raise NutritionServiceError("day deve essere >= 1")
        day_idx = day_1based - 1

        meal_names = data.get("meals") or [
            "Colazione",
            "Spuntino",
            "Pranzo",
            "Cena",
        ]
        if not isinstance(meal_names, list) or not meal_names:
            raise NutritionServiceError("meals deve essere una lista non vuota")

        existing_names = {
            (m.meal_name or "").strip().lower()
            for m in plan.meals
            if self._meal_covers_day(m, day_idx)
        }

        created: List[DietMeal] = []
        for raw_name in meal_names:
            name = (raw_name or "").strip()
            if not name:
                continue
            if name.lower() in existing_names:
                continue
            meal = DietMeal(
                diet_plan_id=plan.id,
                day_index=day_idx,
                day_index_to=day_idx,
                meal_name=name,
            )
            db.session.add(meal)
            created.append(meal)
            existing_names.add(name.lower())

        if created:
            db.session.commit()
            for meal in created:
                db.session.refresh(meal)
        return created

    def copy_day(self, diet_plan_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Copia i pasti di un giorno su altri giorni (input 1-based).

        Per ogni destinazione: se esiste già un pasto con lo stesso nome che
        copre quel giorno, viene eliminato e sostituito da un pasto single-day
        con gli stessi alimenti.
        """
        plan = db.session.get(DietPlan, diet_plan_id)
        if plan is None:
            raise ResourceNotFoundError(f"Piano dieta {diet_plan_id} inesistente")
        _assert_plan_tenant_access(plan)

        from_day_1 = int(data.get("from_day") or 0)
        if from_day_1 < 1:
            raise NutritionServiceError("from_day deve essere >= 1")
        from_idx = from_day_1 - 1

        raw_to = data.get("to_days") or []
        if not isinstance(raw_to, list) or not raw_to:
            raise NutritionServiceError("to_days deve essere una lista non vuota")

        to_indices: List[int] = []
        for raw in raw_to:
            day_1 = int(raw)
            if day_1 < 1:
                raise NutritionServiceError("ogni giorno in to_days deve essere >= 1")
            if day_1 == from_day_1:
                continue
            idx = day_1 - 1
            if idx not in to_indices:
                to_indices.append(idx)

        if not to_indices:
            raise NutritionServiceError("Seleziona almeno un giorno destinazione diverso dalla sorgente")

        source_meals = [m for m in plan.meals if self._meal_covers_day(m, from_idx)]
        if not source_meals:
            raise NutritionServiceError(f"Nessun pasto da copiare dal giorno {from_day_1}")

        source_ids = {m.id for m in source_meals}
        # Snapshot item sorgente prima delle delete sulle destinazioni
        snapshots = []
        for meal in source_meals:
            day_from = meal.day_index or 0
            day_to = meal.day_index_to if meal.day_index_to is not None else day_from
            if day_to < day_from:
                day_to = day_from
            snapshots.append({
                "source_id": meal.id,
                "meal_name": meal.meal_name,
                "meal_time": meal.meal_time,
                "notes": meal.notes,
                "covers_days": set(range(day_from, day_to + 1)),
                "items": [
                    {
                        "food_id": item.food_id,
                        "quantity_g": item.quantity_g,
                        "notes": item.notes,
                    }
                    for item in meal.items
                ],
            })

        created_meals: List[DietMeal] = []
        replaced = 0
        skipped = 0
        for to_idx in to_indices:
            for snap in snapshots:
                # Pasto range già presente sulla destinazione: niente da fare
                if to_idx in snap["covers_days"]:
                    skipped += 1
                    continue

                name_key = (snap["meal_name"] or "").strip().lower()
                to_replace = [
                    m for m in list(plan.meals)
                    if m.id not in source_ids
                    and self._meal_covers_day(m, to_idx)
                    and (m.meal_name or "").strip().lower() == name_key
                ]
                for old in to_replace:
                    db.session.delete(old)
                    replaced += 1
                db.session.flush()

                new_meal = DietMeal(
                    diet_plan_id=plan.id,
                    day_index=to_idx,
                    day_index_to=to_idx,
                    meal_name=snap["meal_name"],
                    meal_time=snap["meal_time"],
                    notes=snap["notes"],
                )
                db.session.add(new_meal)
                db.session.flush()
                for item_data in snap["items"]:
                    db.session.add(DietMealItem(
                        diet_meal_id=new_meal.id,
                        food_id=item_data["food_id"],
                        quantity_g=item_data["quantity_g"],
                        notes=item_data["notes"],
                    ))
                created_meals.append(new_meal)

        if not created_meals and skipped:
            raise NutritionServiceError(
                "I pasti del giorno sorgente coprono già le destinazioni selezionate "
                "(intervallo condiviso). Nessuna copia necessaria."
            )

        db.session.commit()
        return {
            "from_day": from_day_1,
            "to_days": [i + 1 for i in to_indices],
            "meals_created": len(created_meals),
            "meals_replaced": replaced,
            "meals_skipped": skipped,
            "meals": [diet_meal_to_dict(m) for m in created_meals],
        }

    @staticmethod
    def _meal_covers_day(meal: DietMeal, day_idx: int) -> bool:
        day_from = meal.day_index or 0
        day_to = meal.day_index_to if meal.day_index_to is not None else day_from
        if day_to < day_from:
            day_to = day_from
        return day_from <= day_idx <= day_to

    # ==================================================================
    # TOTALI (delegati al calcolatore)
    # ==================================================================
    def meal_totals(self, meal_id: int) -> Dict[str, Any]:
        meal = db.session.get(DietMeal, meal_id)
        if meal is None:
            raise ResourceNotFoundError(f"Pasto {meal_id} inesistente")
        plan = db.session.get(DietPlan, meal.diet_plan_id)
        if plan is not None:
            _assert_plan_tenant_access(plan)
        return NutritionCalculatorService.compute_meal(meal.items)

    def plan_totals(self, diet_plan_id: int) -> Dict[str, Any]:
        plan = db.session.get(DietPlan, diet_plan_id)
        if plan is None:
            raise ResourceNotFoundError(f"Piano dieta {diet_plan_id} inesistente")
        _assert_plan_tenant_access(plan)
        return NutritionCalculatorService.compute_plan(plan.meals)

    # ==================================================================
    # ELIMINAZIONE
    # ==================================================================
    def delete_diet_plan(self, diet_plan_id: int) -> int:
        """Elimina un piano alimentare e tutti i pasti/item collegati."""
        plan = db.session.get(DietPlan, diet_plan_id)
        if plan is None:
            raise ResourceNotFoundError(f"Piano dieta {diet_plan_id} inesistente")
        _assert_plan_tenant_access(plan)
        patient_id = plan.patient_id
        db.session.delete(plan)
        db.session.commit()
        return patient_id

    def delete_meal(self, meal_id: int) -> int:
        """Elimina un pasto e i suoi item."""
        meal = db.session.get(DietMeal, meal_id)
        if meal is None:
            raise ResourceNotFoundError(f"Pasto {meal_id} inesistente")
        plan = db.session.get(DietPlan, meal.diet_plan_id)
        if plan is not None:
            _assert_plan_tenant_access(plan)
        plan_id = meal.diet_plan_id
        db.session.delete(meal)
        db.session.commit()
        return plan_id

    def delete_meal_item(self, item_id: int) -> int:
        """Elimina un alimento da un pasto."""
        item = db.session.get(DietMealItem, item_id)
        if item is None:
            raise ResourceNotFoundError(f"Alimento nel pasto {item_id} inesistente")
        meal = db.session.get(DietMeal, item.diet_meal_id)
        if meal is not None:
            plan = db.session.get(DietPlan, meal.diet_plan_id)
            if plan is not None:
                _assert_plan_tenant_access(plan)
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
