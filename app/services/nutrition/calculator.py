"""Servizio centralizzato per il calcolo dei nutrienti.

Regola unica in tutta l'app:

    valore_calcolato = valore_per_100g * quantity_g / 100

Nessun router o template deve reimplementare questa logica.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

# Nutrienti calcolati (nome logico -> attributo *_per_100g dell'alimento).
NUTRIENTS: Dict[str, str] = {
    "kcal": "kcal_per_100g",
    "protein": "protein_per_100g",
    "carbs": "carbs_per_100g",
    "sugars": "sugars_per_100g",
    "fat": "fat_per_100g",
    "saturated_fat": "saturated_fat_per_100g",
    "fiber": "fiber_per_100g",
    "salt": "salt_per_100g",
    "sodium": "sodium_per_100g",
}


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _empty_totals() -> Dict[str, float]:
    return {key: 0.0 for key in NUTRIENTS}


class NutritionCalculatorService:
    """Calcola i totali nutrizionali a vari livelli di aggregazione.

    Gli "oggetti food" attesi espongono attributi ``*_per_100g`` (es. il
    modello :class:`Food`). I "meal item" espongono ``food`` e ``quantity_g``.
    """

    @staticmethod
    def compute_item(food: Any, quantity_g: Any, round_ndigits: int = 2) -> Dict[str, float]:
        """Totali per un singolo alimento data la quantità in grammi.

        I nutrienti mancanti (None) contano come 0 nel risultato, così il
        totale resta stabile anche se l'API non forniva quel valore.
        """
        qty = _to_float(quantity_g) or 0.0
        factor = qty / 100.0
        totals: Dict[str, float] = {}
        for key, attr in NUTRIENTS.items():
            per_100g = _to_float(getattr(food, attr, None))
            value = (per_100g * factor) if per_100g is not None else 0.0
            totals[key] = round(value, round_ndigits)
        return totals

    @classmethod
    def _sum(cls, chunks: Iterable[Dict[str, float]], round_ndigits: int = 2) -> Dict[str, float]:
        totals = _empty_totals()
        for chunk in chunks:
            for key in NUTRIENTS:
                totals[key] += chunk.get(key, 0.0) or 0.0
        return {key: round(value, round_ndigits) for key, value in totals.items()}

    @classmethod
    def compute_meal(cls, items: Iterable[Any], round_ndigits: int = 2) -> Dict[str, float]:
        """Totale di un pasto sommando i suoi item."""
        return cls._sum(
            (
                cls.compute_item(item.food, item.quantity_g, round_ndigits)
                for item in items
                if getattr(item, "food", None) is not None
            ),
            round_ndigits,
        )

    @classmethod
    def compute_day(cls, meals: Iterable[Any], round_ndigits: int = 2) -> Dict[str, float]:
        """Totale di una giornata sommando i pasti."""
        return cls._sum(
            (cls.compute_meal(getattr(meal, "items", []), round_ndigits) for meal in meals),
            round_ndigits,
        )

    @staticmethod
    def macro_percentages(totals: Dict[str, float]) -> Dict[str, float]:
        """Percentuale di calorie fornita da proteine, carboidrati e grassi.

        Usa i fattori di Atwater (P/C = 4 kcal/g, G = 9 kcal/g) e normalizza
        sulla somma delle calorie dei tre macro, così le percentuali chiudono
        sempre a 100 anche se le kcal dichiarate degli alimenti divergono.
        """
        protein_kcal = (_to_float(totals.get("protein")) or 0.0) * 4.0
        carbs_kcal = (_to_float(totals.get("carbs")) or 0.0) * 4.0
        fat_kcal = (_to_float(totals.get("fat")) or 0.0) * 9.0
        macro_kcal = protein_kcal + carbs_kcal + fat_kcal
        if macro_kcal <= 0:
            return {"protein": 0.0, "carbs": 0.0, "fat": 0.0}
        return {
            "protein": round(protein_kcal / macro_kcal * 100, 1),
            "carbs": round(carbs_kcal / macro_kcal * 100, 1),
            "fat": round(fat_kcal / macro_kcal * 100, 1),
        }

    @staticmethod
    def target_grams(kcal: Any, pct: Any, kcal_per_gram: float) -> Optional[float]:
        """Grammi di un macro dati kcal totali target e % di calorie."""
        kcal_f = _to_float(kcal)
        pct_f = _to_float(pct)
        if not kcal_f or pct_f is None:
            return None
        return round(kcal_f * pct_f / 100.0 / kcal_per_gram, 1)

    @classmethod
    def compute_plan(cls, meals: Iterable[Any], round_ndigits: int = 2) -> Dict[str, Any]:
        """Totale dieta + breakdown per giornata (``day_index`` … ``day_index_to``).

        Il totale somma ogni pasto una sola volta (non moltiplica per i giorni
        del range). ``per_day`` invece include il pasto in ogni giornata
        coperta dall'intervallo.

        Ritorna::

            {
                "total": {kcal, protein, ...},
                "per_day": {0: {...}, 1: {...}},
            }
        """
        meals = list(meals)
        per_day: Dict[int, Dict[str, float]] = {}
        buckets: Dict[int, list] = {}
        for meal in meals:
            day_from = getattr(meal, "day_index", 0) or 0
            day_to = getattr(meal, "day_index_to", None)
            if day_to is None:
                day_to = day_from
            if day_to < day_from:
                day_to = day_from
            for day in range(day_from, day_to + 1):
                buckets.setdefault(day, []).append(meal)
        for day, day_meals in buckets.items():
            per_day[day] = cls.compute_day(day_meals, round_ndigits)

        # Totale = somma pasti unici (non somma di per_day, che duplicherebbe i range)
        total = cls.compute_day(meals, round_ndigits)
        return {"total": total, "per_day": per_day}
