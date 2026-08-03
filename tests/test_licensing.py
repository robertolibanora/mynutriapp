"""Test licensing: conteggio pazienti attivi, guard limiti, API subscription."""

from __future__ import annotations

import os
import unittest
from datetime import date, timedelta

from flask import Flask
from werkzeug.security import generate_password_hash

from app.billing.plans import (
    PLAN_LIMITS,
    get_patient_limit,
    normalize_plan,
    plan_from_stripe_price_id,
)
from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import Dieta, DietPlan, Patient, db
from app.services.diet_service import create_pdf_diet
from app.services.licensing_service import (
    PlanLimitError,
    assert_can_increase_active_patients,
    assert_within_plan_limit,
    count_active_patients,
    get_subscription_usage,
    is_patient_active,
)
from app.services.nutrition.service import NutritionService
from app.services.paziente_service import crea_paziente_provvisorio


class LicensingDbTestCase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        self.app.config["SECRET_KEY"] = "test-secret"
        self.app.config["WTF_CSRF_ENABLED"] = False
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.nutri = Utente(
            nome="Nutri",
            cognome="Test",
            email="nutri@test.local",
            telefono="3400000001",
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            password_hash=generate_password_hash("password123"),
            attivo=True,
            plan="starter",
            subscription_status="none",
        )
        db.session.add(self.nutri)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _patient(self, suffix: str) -> Patient:
        p = Patient(
            password_hash="x",
            telefono=f"+39000{suffix}",
            nome="Paz",
            cognome=suffix,
            sesso="M",
            data_nascita=date(1990, 1, 1),
            altezza_cm=170,
            peso_iniziale=70,
            nutrizionista_id=self.nutri.id,
            stato_cliente="attivo",
        )
        db.session.add(p)
        db.session.commit()
        return p


class PlanConfigTest(unittest.TestCase):
    def test_limits_from_config(self):
        self.assertEqual(get_patient_limit("starter"), 20)
        self.assertEqual(get_patient_limit("professional"), 50)
        self.assertEqual(get_patient_limit("studio"), 100)
        self.assertIsNone(get_patient_limit("enterprise"))
        self.assertEqual(PLAN_LIMITS["starter"]["active_patients"], 20)

    def test_normalize_and_price_mapping(self):
        self.assertEqual(normalize_plan("Professional"), "professional")
        self.assertEqual(normalize_plan("nope"), "starter")
        os.environ["STRIPE_PRICE_STARTER"] = "price_starter_test"
        try:
            self.assertEqual(
                plan_from_stripe_price_id("price_starter_test"), "starter"
            )
            self.assertIsNone(plan_from_stripe_price_id("price_unknown"))
        finally:
            os.environ.pop("STRIPE_PRICE_STARTER", None)


class CountActivePatientsTest(LicensingDbTestCase):
    def test_published_counts(self):
        p = self._patient("001")
        self.assertEqual(count_active_patients(self.nutri.id), 0)
        db.session.add(
            DietPlan(patient_id=p.id, title="A", status="published")
        )
        db.session.commit()
        self.assertEqual(count_active_patients(self.nutri.id), 1)
        self.assertTrue(is_patient_active(p.id))

    def test_draft_does_not_count(self):
        p = self._patient("002")
        db.session.add(DietPlan(patient_id=p.id, title="B", status="draft"))
        db.session.commit()
        self.assertEqual(count_active_patients(self.nutri.id), 0)
        self.assertFalse(is_patient_active(p.id))

    def test_pdf_active_and_expired(self):
        p1 = self._patient("003")
        p2 = self._patient("004")
        today = date.today()
        db.session.add(
            Dieta(
                patient_id=p1.id,
                data_inizio=today - timedelta(days=10),
                data_fine=today + timedelta(days=5),
                pdf_path="a.pdf",
                kcal=1800,
            )
        )
        db.session.add(
            Dieta(
                patient_id=p2.id,
                data_inizio=today - timedelta(days=40),
                data_fine=today - timedelta(days=1),
                pdf_path="b.pdf",
                kcal=1800,
            )
        )
        db.session.commit()
        self.assertEqual(count_active_patients(self.nutri.id), 1)
        self.assertTrue(is_patient_active(p1.id))
        self.assertFalse(is_patient_active(p2.id))

    def test_unique_patient_with_both_diet_types(self):
        p = self._patient("005")
        today = date.today()
        db.session.add(
            DietPlan(patient_id=p.id, title="P", status="published")
        )
        db.session.add(
            Dieta(
                patient_id=p.id,
                data_inizio=today,
                data_fine=today + timedelta(days=7),
                pdf_path="c.pdf",
                kcal=2000,
            )
        )
        db.session.commit()
        self.assertEqual(count_active_patients(self.nutri.id), 1)

    def test_usage_payload(self):
        p = self._patient("006")
        db.session.add(
            DietPlan(patient_id=p.id, title="U", status="published")
        )
        db.session.commit()
        usage = get_subscription_usage(self.nutri.id)
        self.assertEqual(usage["plan"], "starter")
        self.assertEqual(usage["active_patients"], 1)
        self.assertEqual(usage["patient_limit"], 20)
        self.assertEqual(usage["remaining"], 19)
        self.assertEqual(usage["percentage"], 5)


class GuardLimitTest(LicensingDbTestCase):
    def test_assert_within_limit_blocks_create_patient(self):
        self.nutri.plan = "starter"
        db.session.commit()
        # Forza limite 1 via monkeypatch sul piano enterprise? Better: fill 20 is slow.
        # Usa enterprise None and starter with mock: temporarily lower via patch.
        from unittest.mock import patch

        with patch(
            "app.services.licensing_service.get_patient_limit", return_value=1
        ):
            p = self._patient("010")
            db.session.add(
                DietPlan(patient_id=p.id, title="X", status="published")
            )
            db.session.commit()
            with self.assertRaises(PlanLimitError):
                assert_within_plan_limit(self.nutri.id)
            with self.assertRaises(PlanLimitError):
                crea_paziente_provvisorio(
                    "Nuovo",
                    "Cliente",
                    "3409999910",
                    nutrizionista_id=self.nutri.id,
                )

    def test_publish_blocked_for_new_active_patient(self):
        from unittest.mock import patch

        p1 = self._patient("011")
        p2 = self._patient("012")
        db.session.add(
            DietPlan(patient_id=p1.id, title="A", status="published")
        )
        db.session.commit()
        service = NutritionService()
        with patch(
            "app.services.licensing_service.get_patient_limit", return_value=1
        ):
            with self.assertRaises(PlanLimitError):
                service.create_diet_plan(
                    {
                        "patient_id": p2.id,
                        "title": "Nuovo",
                        "status": "published",
                    }
                )

    def test_publish_ok_if_patient_already_active(self):
        from unittest.mock import patch

        p = self._patient("013")
        db.session.add(
            DietPlan(patient_id=p.id, title="A", status="published")
        )
        db.session.commit()
        service = NutritionService()
        with patch(
            "app.services.licensing_service.get_patient_limit", return_value=1
        ):
            plan = service.create_diet_plan(
                {
                    "patient_id": p.id,
                    "title": "Secondo",
                    "status": "published",
                }
            )
            self.assertEqual(plan.status, "published")
            assert_can_increase_active_patients(self.nutri.id, patient_id=p.id)

    def test_pdf_create_blocked_at_limit(self):
        from unittest.mock import patch

        p1 = self._patient("014")
        p2 = self._patient("015")
        today = date.today()
        db.session.add(
            Dieta(
                patient_id=p1.id,
                data_inizio=today,
                data_fine=today + timedelta(days=3),
                pdf_path="x.pdf",
                kcal=1800,
            )
        )
        db.session.commit()
        with patch(
            "app.services.licensing_service.get_patient_limit", return_value=1
        ):
            with self.assertRaises(PlanLimitError):
                create_pdf_diet(
                    patient_id=p2.id,
                    data_inizio=today,
                    data_fine=today + timedelta(days=10),
                    pdf_path="y.pdf",
                    kcal=1900,
                )

    def test_plan_limit_error_payload(self):
        err = PlanLimitError()
        with self.app.test_request_context():
            body, status = err.to_response()
            self.assertEqual(status, 403)
            data = body.get_json()
            self.assertEqual(data["error"], "plan_limit_reached")
            self.assertIn("limite", data["message"].lower())


class SubscriptionApiTest(LicensingDbTestCase):
    def setUp(self):
        super().setUp()
        from app.api.v1 import api_v1_bp

        self.app.register_blueprint(api_v1_bp)
        self.client = self.app.test_client()

    def test_subscription_requires_nutrizionista_session(self):
        res = self.client.get("/api/v1/subscription")
        self.assertEqual(res.status_code, 401)

    def test_subscription_ok(self):
        p = self._patient("020")
        db.session.add(
            DietPlan(patient_id=p.id, title="S", status="published")
        )
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess["role"] = "nutrizionista"
            sess["utente_id"] = self.nutri.id
        res = self.client.get("/api/v1/subscription")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["plan"], "starter")
        self.assertEqual(data["active_patients"], 1)
        self.assertEqual(data["patient_limit"], 20)
        self.assertEqual(data["remaining"], 19)
        self.assertEqual(data["percentage"], 5)


if __name__ == "__main__":
    unittest.main()
