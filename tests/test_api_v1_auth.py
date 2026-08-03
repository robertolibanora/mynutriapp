"""Test API /api/v1 auth (login, refresh, /me).

    venv/bin/python -m unittest tests.test_api_v1_auth -v
"""

from __future__ import annotations

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


class ApiV1AuthTest(unittest.TestCase):
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

        nutri = Utente(
            nome="Nutri",
            cognome="Test",
            email="nutri-auth@ex.com",
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            attivo=True,
        )
        db.session.add(nutri)
        db.session.flush()

        self.patient = Patient(
            nome="Giulia",
            cognome="Rossi",
            telefono="3331234567",
            password_hash=generate_password_hash("secret123"),
            stato_cliente="attivo",
            altezza_cm=168,
            peso_iniziale=72.0,
            nutrizionista_id=nutri.id,
            consenso_registrazione=False,
            consenso_ai=False,
        )
        self.inactive = Patient(
            nome="Luca",
            cognome="Bianchi",
            telefono="3339998877",
            password_hash=generate_password_hash("secret123"),
            stato_cliente="provvisorio",
            nutrizionista_id=nutri.id,
            consenso_registrazione=False,
            consenso_ai=False,
        )
        db.session.add_all([self.patient, self.inactive])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_login_ok(self):
        res = self.client.post(
            "/api/v1/auth/login",
            json={"telefono": "3331234567", "password": "secret123"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("access_token", data)
        self.assertIn("refresh_token", data)
        self.assertEqual(data["token_type"], "Bearer")
        self.assertEqual(data["user"]["id"], self.patient.id)
        self.assertEqual(data["user"]["role"], "user")
        self.assertNotIn("password_hash", data["user"])

    def test_login_wrong_password(self):
        res = self.client.post(
            "/api/v1/auth/login",
            json={"telefono": "3331234567", "password": "wrong"},
        )
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data["code"], "invalid_credentials")

    def test_login_inactive(self):
        res = self.client.post(
            "/api/v1/auth/login",
            json={"telefono": "3339998877", "password": "secret123"},
        )
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertEqual(data["code"], "account_inactive")

    def test_me_without_token(self):
        res = self.client.get("/api/v1/me")
        self.assertEqual(res.status_code, 401)

    def test_me_with_access_token(self):
        login = self.client.post(
            "/api/v1/auth/login",
            json={"telefono": "3331234567", "password": "secret123"},
        ).get_json()
        res = self.client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {login['access_token']}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["id"], self.patient.id)
        self.assertEqual(data["nome"], "Giulia")
        self.assertNotIn("password_hash", data)

    def test_me_with_garbage_token(self):
        res = self.client.get(
            "/api/v1/me",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json()["code"], "invalid_token")

    def test_refresh_ok_and_access_rejected_as_refresh(self):
        login = self.client.post(
            "/api/v1/auth/login",
            json={"telefono": "3331234567", "password": "secret123"},
        ).get_json()

        refreshed = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login["refresh_token"]},
        )
        self.assertEqual(refreshed.status_code, 200)
        body = refreshed.get_json()
        self.assertIn("access_token", body)
        self.assertIn("refresh_token", body)

        bad = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login["access_token"]},
        )
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(bad.get_json()["code"], "invalid_token")


if __name__ == "__main__":
    unittest.main()
