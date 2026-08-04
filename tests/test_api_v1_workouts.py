"""Test API /api/v1/workouts.

    venv/bin/python -m unittest tests.test_api_v1_workouts -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from flask import Flask
from werkzeug.security import generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)
os.environ.setdefault("ENCRYPTION_KEY", "x" * 44)

from app.api.v1 import api_v1_bp
from app.models.models import Allenamento, Patient, db
from tests._fixtures import make_nutrizionista


class ApiV1WorkoutsTest(unittest.TestCase):
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

        nutri = make_nutrizionista()
        self.patient = Patient(
            nome="Giulia",
            cognome="Rossi",
            telefono="3331234567",
            password_hash=generate_password_hash("secret123"),
            stato_cliente="attivo",
            account_status="active",
            consenso_registrazione=False,
            consenso_ai=False,
            nutrizionista_id=nutri.id,
        )
        self.other = Patient(
            nome="Mario",
            cognome="Verdi",
            telefono="3330001111",
            password_hash=generate_password_hash("secret123"),
            stato_cliente="attivo",
            account_status="active",
            consenso_registrazione=False,
            consenso_ai=False,
            nutrizionista_id=nutri.id,
        )
        db.session.add_all([self.patient, self.other])
        db.session.flush()

        self.tmp = tempfile.TemporaryDirectory()
        pdf = Path(self.tmp.name) / "piano.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")

        self.own = Allenamento(
            patient_id=self.patient.id,
            data_inizio=date.today() - timedelta(days=7),
            data_fine=date.today() + timedelta(days=21),
            pdf_path=str(pdf),
            note="Full body",
        )
        self.other_w = Allenamento(
            patient_id=self.other.id,
            data_inizio=date.today(),
            data_fine=date.today() + timedelta(days=30),
            pdf_path=str(pdf),
            note="Altrui",
        )
        db.session.add_all([self.own, self.other_w])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        self.tmp.cleanup()

    def _token(self, telefono="3331234567"):
        res = self.client.post(
            "/api/v1/auth/login",
            json={"telefono": telefono, "password": "secret123"},
        )
        self.assertEqual(res.status_code, 200)
        return res.get_json()["access_token"]

    def test_list_requires_auth(self):
        self.assertEqual(self.client.get("/api/v1/workouts").status_code, 401)

    def test_list_and_active(self):
        token = self._token()
        res = self.client.get(
            "/api/v1/workouts",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        ids = {w["id"] for w in data["workouts"]}
        self.assertIn(self.own.id, ids)
        self.assertNotIn(self.other_w.id, ids)
        self.assertEqual(data["active"]["id"], self.own.id)
        self.assertTrue(data["workouts"][0]["attiva"])
        self.assertNotIn("pdf_path", data["workouts"][0])

        active = self.client.get(
            "/api/v1/workouts/active",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(active.status_code, 200)
        self.assertEqual(active.get_json()["workout"]["id"], self.own.id)

    def test_detail_other_404(self):
        token = self._token()
        bad = self.client.get(
            f"/api/v1/workouts/{self.other_w.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(bad.status_code, 404)

    def test_pdf(self):
        token = self._token()
        res = self.client.get(
            f"/api/v1/workouts/{self.own.id}/pdf",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data.startswith(b"%PDF"))

        other = self._token("3330001111")
        denied = self.client.get(
            f"/api/v1/workouts/{self.own.id}/pdf",
            headers={"Authorization": f"Bearer {other}"},
        )
        self.assertEqual(denied.status_code, 404)


if __name__ == "__main__":
    unittest.main()
