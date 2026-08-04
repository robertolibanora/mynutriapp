"""Test API /api/v1/progress.

    venv/bin/python -m unittest tests.test_api_v1_progress -v
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
from app.models.models import MisureAntropometriche, Patient, Progresso, db
from tests._fixtures import make_nutrizionista


class ApiV1ProgressTest(unittest.TestCase):
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
        photo = Path(self.tmp.name) / "foto.jpg"
        photo.write_bytes(b"\xff\xd8\xfffakejpeg")

        self.own = Progresso(
            patient_id=self.patient.id,
            data_check=date.today() - timedelta(days=1),
            tipo_check="nutrizionista",
            peso_settimanale=71.5,
            aderenza=8,
            frequenza_allenamenti="3",
            check_richiesta=False,
            foto_path=str(photo),
        )
        self.other_p = Progresso(
            patient_id=self.other.id,
            data_check=date.today(),
            tipo_check="paziente",
            peso_settimanale=80,
            check_richiesta=True,
        )
        db.session.add_all([self.own, self.other_p])
        db.session.flush()
        db.session.add(
            MisureAntropometriche(
                patient_id=self.patient.id,
                progresso_id=self.own.id,
                data_misurazione=date.today() - timedelta(days=1),
                circonferenza_vita=80,
            )
        )
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
        self.assertEqual(self.client.get("/api/v1/progress").status_code, 401)

    def test_list_only_own(self):
        token = self._token()
        res = self.client.get(
            "/api/v1/progress",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        ids = {p["id"] for p in res.get_json()["progress"]}
        self.assertIn(self.own.id, ids)
        self.assertNotIn(self.other_p.id, ids)
        self.assertNotIn("foto_path", res.get_json()["progress"][0])

    def test_latest(self):
        token = self._token()
        res = self.client.get(
            "/api/v1/progress/latest",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["progress"]["id"], self.own.id)

    def test_detail_ok_and_other_404(self):
        token = self._token()
        ok = self.client.get(
            f"/api/v1/progress/{self.own.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(ok.status_code, 200)
        body = ok.get_json()
        self.assertTrue(body["has_foto"])
        self.assertEqual(body["misure"]["circonferenza_vita"], 80.0)
        self.assertNotIn("foto_path", body)

        bad = self.client.get(
            f"/api/v1/progress/{self.other_p.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(bad.status_code, 404)
        self.assertEqual(bad.get_json()["code"], "not_found")

    def test_create_and_validation(self):
        token = self._token()
        bad = self.client.post(
            "/api/v1/progress",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(bad.status_code, 400)

        ok = self.client.post(
            "/api/v1/progress",
            json={
                "peso_settimanale": 70.2,
                "aderenza": 7,
                "frequenza_allenamenti": "2",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(ok.status_code, 201)
        data = ok.get_json()
        self.assertEqual(data["peso_settimanale"], 70.2)
        self.assertEqual(data["tipo_check"], "paziente")
        self.assertTrue(data["check_richiesta"])

    def test_photo(self):
        token = self._token()
        res = self.client.get(
            f"/api/v1/progress/{self.own.id}/photo",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)

        other_token = self._token("3330001111")
        denied = self.client.get(
            f"/api/v1/progress/{self.own.id}/photo",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(denied.status_code, 404)


if __name__ == "__main__":
    unittest.main()
