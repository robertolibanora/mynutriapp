"""Test API GDPR paziente (/api/v1/me/privacy|export|erasure).

    venv/bin/python -m unittest tests.test_api_v1_gdpr -v
"""

from __future__ import annotations

import json
import os
import unittest

from flask import Flask
from werkzeug.security import generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)
os.environ.setdefault("ENCRYPTION_KEY", "x" * 44)

from app.api.v1 import api_v1_bp
from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import Patient, db


class ApiV1GdprTest(unittest.TestCase):
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
            PRIVACY_POLICY_VERSION="1.0",
        )
        db.init_app(self.app)
        self.app.register_blueprint(api_v1_bp)

        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        nutri = Utente(
            nome="Nutri",
            cognome="Test",
            email="nutri-gdpr@ex.com",
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            attivo=True,
        )
        db.session.add(nutri)
        db.session.flush()

        self.patient = Patient(
            nome="Giulia",
            cognome="Rossi",
            telefono="3331234567",
            email="giulia@ex.com",
            password_hash=generate_password_hash("secret123"),
            stato_cliente="attivo",
            nutrizionista_id=nutri.id,
            consenso_privacy=True,
            consenso_marketing=False,
            consenso_registrazione=False,
            consenso_ai=False,
        )
        db.session.add(self.patient)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _token(self) -> str:
        res = self.client.post(
            "/api/v1/auth/login",
            json={"telefono": "3331234567", "password": "secret123"},
        )
        self.assertEqual(res.status_code, 200)
        return res.get_json()["access_token"]

    def test_privacy_get(self):
        token = self._token()
        res = self.client.get(
            "/api/v1/me/privacy",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["consenso_privacy"])
        self.assertFalse(data["consenso_marketing"])
        self.assertIsNone(data["erasure_requested_at"])

    def test_privacy_patch_marketing(self):
        token = self._token()
        res = self.client.patch(
            "/api/v1/me/privacy",
            json={"consenso_marketing": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["privacy"]["consenso_marketing"])
        db.session.refresh(self.patient)
        self.assertTrue(self.patient.consenso_marketing)

    def test_privacy_cannot_revoke_without_erasure(self):
        token = self._token()
        res = self.client.patch(
            "/api/v1/me/privacy",
            json={"consenso_privacy": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["code"], "privacy_revoke_via_erasure")

    def test_export(self):
        token = self._token()
        res = self.client.get(
            "/api/v1/me/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        payload = json.loads(res.data.decode("utf-8"))
        self.assertEqual(payload["patient"]["id"], self.patient.id)
        self.assertIn("consensi", payload)

    def test_erasure_request(self):
        token = self._token()
        res = self.client.post(
            "/api/v1/me/erasure",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["ok"])
        db.session.refresh(self.patient)
        self.assertIsNotNone(self.patient.erasure_requested_at)

    def test_unauthorized(self):
        res = self.client.get("/api/v1/me/privacy")
        self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
