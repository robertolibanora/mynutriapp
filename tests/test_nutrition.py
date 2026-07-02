"""Test minimi per il modulo nutrizione.

Copre:
- normalizzazione alimento (provider -> NormalizedFood)
- calcolo nutrienti per quantità
- somma totale pasto
- import alimento già esistente (dedup provider + external_id)

Eseguibili senza rete e senza MySQL (SQLite in-memory):

    venv/bin/python -m unittest tests.test_nutrition -v
"""

from __future__ import annotations

import unittest
from datetime import date

from flask import Flask

from app.models.models import (
    DietMeal,
    DietMealItem,
    DietPlan,
    Food,
    Patient,
    db,
)
from app.services.nutrition import (
    NormalizedFood,
    NutritionCalculatorService,
    NutritionService,
)
from app.services.nutrition.openfoodfacts import OpenFoodFactsProvider
from app.services.nutrition.providers import NutritionProvider


# --------------------------------------------------------------------------
# Provider fittizio: nessuna chiamata di rete nei test
# --------------------------------------------------------------------------
class FakeProvider(NutritionProvider):
    name = "fake"

    def __init__(self):
        self.details_calls = 0

    def search_foods(self, query, limit=10):
        return [
            NormalizedFood.build("fake", "1", "Yogurt Greco", kcal_per_100g=59)
        ]

    def get_food_details(self, external_id):
        self.details_calls += 1
        return NormalizedFood.build(
            "fake",
            external_id,
            "Yogurt Greco",
            brand="TestBrand",
            kcal_per_100g=59,
            protein_per_100g=10,
            carbs_per_100g=3.6,
            fat_per_100g=0.4,
        )


class NormalizationTest(unittest.TestCase):
    """Normalizzazione della risposta grezza del provider."""

    def test_openfoodfacts_normalization(self):
        provider = OpenFoodFactsProvider()
        raw_product = {
            "code": "123456789",
            "product_name": "Yogurt Greco 0%",
            "brands": "Fage, Total",
            "categories": "Dairy, Yogurts",
            "serving_quantity": 170,
            "nutriments": {
                "energy-kcal_100g": 59,
                "proteins_100g": 10.3,
                "carbohydrates_100g": 3.6,
                "sugars_100g": 3.6,
                "fat_100g": 0.4,
                # saturated-fat, fiber, salt, sodium assenti di proposito
            },
        }
        food = provider._normalize(raw_product)

        self.assertIsNotNone(food)
        self.assertEqual(food.provider, "openfoodfacts")
        self.assertEqual(food.external_id, "123456789")
        self.assertEqual(food.name, "Yogurt Greco 0%")
        self.assertEqual(food.brand, "Fage")  # prima voce
        self.assertEqual(food.category, "Dairy")
        self.assertEqual(food.kcal_per_100g, 59.0)
        self.assertEqual(food.protein_per_100g, 10.3)
        self.assertEqual(food.serving_size, 170.0)
        self.assertEqual(food.serving_unit, "g")
        # Nutrienti mancanti => None, nessun crash
        self.assertIsNone(food.saturated_fat_per_100g)
        self.assertIsNone(food.fiber_per_100g)

    def test_normalization_survives_missing_nutriments(self):
        provider = OpenFoodFactsProvider()
        food = provider._normalize({"code": "1", "product_name": "Test"})
        self.assertIsNotNone(food)
        self.assertIsNone(food.kcal_per_100g)

    def test_energy_fallback_from_kj(self):
        provider = OpenFoodFactsProvider()
        food = provider._normalize(
            {"code": "1", "product_name": "Test", "nutriments": {"energy_100g": 418.4}}
        )
        self.assertEqual(food.kcal_per_100g, 100.0)


class CalculatorTest(unittest.TestCase):
    """Calcolo nutrienti per quantità e somma pasto."""

    def _food(self):
        return Food(
            name="Yogurt Greco",
            kcal_per_100g=59,
            protein_per_100g=10,
            carbs_per_100g=3.6,
            fat_per_100g=0.4,
            # sugars/saturated/fiber/salt/sodium None -> contano 0
        )

    def test_compute_item_for_quantity(self):
        totals = NutritionCalculatorService.compute_item(self._food(), 170)
        # 59 * 170 / 100 = 100.3
        self.assertEqual(totals["kcal"], 100.3)
        self.assertEqual(totals["protein"], 17.0)
        self.assertEqual(totals["carbs"], 6.12)
        self.assertEqual(totals["fat"], 0.68)
        # Nutriente mancante -> 0, mai crash
        self.assertEqual(totals["fiber"], 0.0)

    def test_compute_meal_sum(self):
        class Item:
            def __init__(self, food, quantity_g):
                self.food = food
                self.quantity_g = quantity_g

        food = self._food()
        items = [Item(food, 170), Item(food, 100)]  # 270 g totali
        totals = NutritionCalculatorService.compute_meal(items)
        # 59 * 270 / 100 = 159.3
        self.assertEqual(totals["kcal"], 159.3)
        self.assertEqual(totals["protein"], 27.0)


class DbTestCase(unittest.TestCase):
    """Base con app Flask + SQLite in-memory."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()


class ImportDedupTest(DbTestCase):
    """Import alimento già esistente: riuso, niente duplicati."""

    def test_import_reuses_existing_food(self):
        provider = FakeProvider()
        service = NutritionService(provider=provider)

        first = service.import_food("fake", "999")
        self.assertIsNotNone(first.id)
        self.assertEqual(provider.details_calls, 1)

        # Secondo import stesso provider+external_id: nessuna nuova riga,
        # nessuna nuova chiamata al provider.
        second = service.import_food("fake", "999")
        self.assertEqual(first.id, second.id)
        self.assertEqual(provider.details_calls, 1)
        self.assertEqual(Food.query.count(), 1)


class MealTotalsTest(DbTestCase):
    """Totale pasto calcolato dal servizio usando dati locali."""

    def test_meal_totals_end_to_end(self):
        patient = Patient(
            password_hash="x",
            telefono="+390000000000",
            nome="Mario",
            cognome="Rossi",
            sesso="M",
            data_nascita=date(1990, 1, 1),
            altezza_cm=180,
            peso_iniziale=80,
        )
        db.session.add(patient)
        db.session.commit()

        service = NutritionService(provider=FakeProvider())
        food = service.import_food("fake", "1")

        plan = service.create_diet_plan({"patient_id": patient.id, "title": "Piano test"})
        meal = service.add_meal(plan.id, {"meal_name": "Colazione", "day_index": 0})
        service.add_meal_item(meal.id, {"food_id": food.id, "quantity_g": 170})

        totals = service.meal_totals(meal.id)
        self.assertEqual(totals["kcal"], 100.3)
        self.assertEqual(totals["protein"], 17.0)

        plan_totals = service.plan_totals(plan.id)
        self.assertEqual(plan_totals["total"]["kcal"], 100.3)
        self.assertIn(0, plan_totals["per_day"])


if __name__ == "__main__":
    unittest.main()
