"""Test API /api/v1/diets.

    venv/bin/python -m unittest tests.test_api_v1_diets -v
"""

from __future__ import annotations

import os
import unittest
from datetime import date, datetime, timedelta

from flask import Flask
from werkzeug.security import generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)
os.environ.setdefault("ENCRYPTION_KEY", "x" * 44)

from app.api.v1 import api_v1_bp
from app.models.models import (
    DietMeal,
    DietMealItem,
    DietPlan,
    Dieta,
    Food,
    Patient,
    db,
)


class ApiV1DietsTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret-key",
            JWT_SECRET="test-jwt-secret",
            JWT_ACCESS_EXPIRES=900,
            JWT_REFRESH_EXPIRES=2592000,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            WTF_CSRF_ENABLED=False,
        )
        db.init_app(self.app)
        self.app.register_blueprint(api_v1_bp)

        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.patient = Patient(
            nome="Giulia",
            cognome="Rossi",
            telefono="3331234567",
            password_hash=generate_password_hash("secret123"),
            stato_cliente="attivo",
            consenso_registrazione=False,
            consenso_ai=False,
        )
        self.other = Patient(
            nome="Mario",
            cognome="Verdi",
            telefono="3330001111",
            password_hash=generate_password_hash("secret123"),
            stato_cliente="attivo",
            consenso_registrazione=False,
            consenso_ai=False,
        )
        db.session.add_all([self.patient, self.other])
        db.session.flush()

        self.food = Food(
            name="Yogurt",
            brand="Test",
            provider="custom",
            external_id="yog-1",
            kcal_per_100g=60,
            protein_per_100g=10,
            carbs_per_100g=5,
            fat_per_100g=1,
            is_custom=True,
        )
        db.session.add(self.food)
        db.session.flush()

        self.plan = DietPlan(
            patient_id=self.patient.id,
            title="Piano primavera",
            goal="Dimagrimento",
            notes="Bere acqua",
            status="published",
            target_kcal=1800,
        )
        self.draft = DietPlan(
            patient_id=self.patient.id,
            title="Bozza nascosta",
            status="draft",
        )
        self.other_plan = DietPlan(
            patient_id=self.other.id,
            title="Piano altrui",
            status="published",
            target_kcal=2000,
        )
        db.session.add_all([self.plan, self.draft, self.other_plan])
        db.session.flush()

        meal = DietMeal(
            diet_plan_id=self.plan.id,
            day_index=0,
            day_index_to=0,
            meal_name="Colazione",
        )
        db.session.add(meal)
        db.session.flush()
        db.session.add(
            DietMealItem(
                diet_meal_id=meal.id,
                food_id=self.food.id,
                quantity_g=150,
            )
        )

        self.pdf = Dieta(
            patient_id=self.patient.id,
            data_inizio=date.today() - timedelta(days=10),
            data_fine=date.today() + timedelta(days=20),
            pdf_path="diete/test.pdf",
            kcal=1900,
            note="PDF legacy",
        )
        db.session.add(self.pdf)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _token(self, telefono="3331234567"):
        res = self.client.post(
            "/api/v1/auth/login",
            json={"telefono": telefono, "password": "secret123"},
        )
        self.assertEqual(res.status_code, 200)
        return res.get_json()["access_token"]

    def test_list_requires_auth(self):
        self.assertEqual(self.client.get("/api/v1/diets").status_code, 401)

    def test_list_only_own_published_and_pdf(self):
        token = self._token()
        res = self.client.get(
            "/api/v1/diets",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        kinds_ids = {(d["kind"], d["id"]) for d in data["diets"]}
        self.assertIn(("diet_plan", self.plan.id), kinds_ids)
        self.assertIn(("dieta_pdf", self.pdf.id), kinds_ids)
        self.assertNotIn(("diet_plan", self.draft.id), kinds_ids)
        self.assertNotIn(("diet_plan", self.other_plan.id), kinds_ids)
        self.assertEqual(data["active"]["kind"], "diet_plan")
        self.assertEqual(data["active"]["id"], self.plan.id)

    def test_list_empty(self):
        lonely = Patient(
            nome="Anna",
            cognome="Neri",
            telefono="3335556666",
            password_hash=generate_password_hash("secret123"),
            stato_cliente="attivo",
            consenso_registrazione=False,
            consenso_ai=False,
        )
        db.session.add(lonely)
        db.session.commit()
        token = self._token("3335556666")
        res = self.client.get(
            "/api/v1/diets",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["diets"], [])
        self.assertIsNone(body["active"])

    def test_active(self):
        token = self._token()
        res = self.client.get(
            "/api/v1/diets/active",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        diet = res.get_json()["diet"]
        self.assertEqual(diet["kind"], "diet_plan")
        self.assertEqual(diet["id"], self.plan.id)
        self.assertTrue(diet["attiva"])
        self.assertEqual(len(diet["meals"]), 1)
        self.assertEqual(diet["meals"][0]["items"][0]["quantity_g"], 150.0)

    def test_detail_ok(self):
        token = self._token()
        res = self.client.get(
            f"/api/v1/diets/{self.plan.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["title"], "Piano primavera")
        self.assertIn("meals", data)

    def test_detail_other_is_not_found(self):
        token = self._token()
        res = self.client.get(
            f"/api/v1/diets/{self.other_plan.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.get_json()["code"], "not_found")

    def test_detail_draft_is_not_found(self):
        token = self._token()
        res = self.client.get(
            f"/api/v1/diets/{self.draft.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 404)

    def test_invalid_token(self):
        res = self.client.get(
            "/api/v1/diets",
            headers={"Authorization": "Bearer garbage"},
        )
        self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
