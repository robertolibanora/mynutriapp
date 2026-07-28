"""Test creazione consultation (API + service).

    venv/bin/python -m unittest tests.test_consultation_create -v
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime

from flask import Flask
from werkzeug.security import generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)

from app.config.config import Config
from app.models.diario import Consultation, Utente
from app.models.enums import ConsultationStato
from app.models.models import Patient, db
from app.routes.patients_diary_api import patients_diary_api_bp
from app.services.diario_consultation_service import (
    create_consultation,
    get_consultation_for_pipeline,
)


class ConsultationCreateTest(unittest.TestCase):
    def setUp(self):
        Config.SINGLE_TENANT = True
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            WTF_CSRF_ENABLED=False,
            SINGLE_TENANT=True,
        )
        db.init_app(self.app)
        self.app.register_blueprint(patients_diary_api_bp)

        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.owner = Utente(nome="N", cognome="U", email="owner@ex.com", attivo=True)
        db.session.add(self.owner)
        db.session.flush()

        self.patient = Patient(
            nome="Maria",
            cognome="Rossi",
            telefono="3330000001",
            password_hash=generate_password_hash("x"),
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

    def _login(self):
        with self.client.session_transaction() as sess:
            sess["role"] = "admin"
            sess["utente_id"] = self.owner.id

    def test_create_consultation_api_sets_consent(self):
        self._login()
        res = self.client.post(
            f"/api/patients/{self.patient.id}/consultations",
            json={
                "data_colloquio": "2026-07-29T10:00",
                "note_manuali": "Primo controllo",
                "consenso_registrazione": True,
                "consenso_ai": True,
            },
        )
        self.assertEqual(res.status_code, 201, res.get_json())
        data = res.get_json()
        self.assertEqual(data["stato"], ConsultationStato.BOZZA.value)
        self.assertEqual(data["patient_id"], self.patient.id)
        self.assertIn("/pipeline", data["pipeline_url"])

        db.session.refresh(self.patient)
        self.assertTrue(self.patient.consenso_registrazione)
        self.assertTrue(self.patient.consenso_ai)

        c = db.session.get(Consultation, data["id"])
        self.assertIsNotNone(c)
        self.assertEqual(c.note_manuali, "Primo controllo")

    def test_pipeline_payload(self):
        payload = create_consultation(
            patient_id=self.patient.id,
            utente_id=self.owner.id,
            data_colloquio="2026-07-29T11:00",
        )
        info = get_consultation_for_pipeline(
            consultation_id=payload["id"],
            utente_id=self.owner.id,
        )
        self.assertEqual(info["patient"]["nome"], "Maria")
        self.assertEqual(info["stato"], ConsultationStato.BOZZA.value)


if __name__ == "__main__":
    unittest.main()
