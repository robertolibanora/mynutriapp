"""Test API /api/v1/appointments.

    venv/bin/python -m unittest tests.test_api_v1_appointments -v
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, time

from flask import Flask
from werkzeug.security import generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)
os.environ.setdefault("ENCRYPTION_KEY", "x" * 44)
os.environ.setdefault("ADMIN_NAME", "Dr. Test")

from app.api.v1 import api_v1_bp
from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import Appuntamento, OrarioSettimanale, Patient, db


class ApiV1AppointmentsTest(unittest.TestCase):
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
            SINGLE_TENANT=False,
        )
        db.init_app(self.app)
        self.app.register_blueprint(api_v1_bp)

        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.nutri = Utente(
            nome="Anna",
            cognome="Nutri",
            email="anna@test.local",
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            attivo=True,
            password_hash=generate_password_hash("admin123"),
        )
        db.session.add(self.nutri)
        db.session.flush()

        self.patient = Patient(
            nome="Giulia",
            cognome="Rossi",
            telefono="3331234567",
            password_hash=generate_password_hash("secret123"),
            stato_cliente="attivo",
            consenso_registrazione=False,
            consenso_ai=False,
            nutrizionista_id=self.nutri.id,
        )
        self.other = Patient(
            nome="Mario",
            cognome="Verdi",
            telefono="3330001111",
            password_hash=generate_password_hash("secret123"),
            stato_cliente="attivo",
            consenso_registrazione=False,
            consenso_ai=False,
            nutrizionista_id=self.nutri.id,
        )
        db.session.add_all([self.patient, self.other])
        db.session.flush()

        self.appt = Appuntamento(
            patient_id=self.patient.id,
            utente_id=self.nutri.id,
            created_by="user",
            data_appuntamento=datetime.now() + timedelta(days=3),
            tipo="check",
            stato="confermato",
            note="Controllo mensile",
        )
        self.other_appt = Appuntamento(
            patient_id=self.other.id,
            utente_id=self.nutri.id,
            created_by="Enrico",
            data_appuntamento=datetime.now() + timedelta(days=5),
            tipo="altro",
            stato="in_attesa",
            note="Privato",
        )
        db.session.add_all([self.appt, self.other_appt])

        # Slot settimanali: tutti i giorni alle 10:00
        for giorno in range(7):
            db.session.add(
                OrarioSettimanale(
                    utente_id=self.nutri.id,
                    giorno_settimana=giorno,
                    ora=time(10, 0),
                    attivo=True,
                )
            )
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

    def _next_free_slot_iso(self) -> str:
        """Primo slot libero futuro alle 10:00 (saltando eventuali già occupati)."""
        from app.services.agenda_service import AgendaService

        slots = AgendaService.slot_liberi(utente_id=self.nutri.id)
        self.assertTrue(slots, "attesi slot liberi dai orari settimanali")
        return slots[0].data_ora.strftime("%Y-%m-%dT%H:%M:%S")

    def test_list_requires_auth(self):
        res = self.client.get("/api/v1/appointments")
        self.assertEqual(res.status_code, 401)

    def test_list_only_own_appointments(self):
        token = self._token()
        res = self.client.get(
            "/api/v1/appointments",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        items = data["appointments"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], self.appt.id)
        self.assertEqual(items[0]["tipo"], "check")
        self.assertEqual(items[0]["stato"], "confermato")
        self.assertIn("professionista", items[0])
        self.assertIn("cancellabile", items[0])
        self.assertIn("data", items[0])
        self.assertIn("ora", items[0])

    def test_list_empty(self):
        lonely = Patient(
            nome="Anna",
            cognome="Neri",
            telefono="3335556666",
            password_hash=generate_password_hash("secret123"),
            stato_cliente="attivo",
            consenso_registrazione=False,
            consenso_ai=False,
            nutrizionista_id=self.nutri.id,
        )
        db.session.add(lonely)
        db.session.commit()
        token = self._token("3335556666")
        res = self.client.get(
            "/api/v1/appointments",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["appointments"], [])

    def test_detail_ok(self):
        token = self._token()
        res = self.client.get(
            f"/api/v1/appointments/{self.appt.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["id"], self.appt.id)
        self.assertEqual(data["note"], "Controllo mensile")
        self.assertEqual(data["titolo"], "Check")

    def test_detail_other_patient_is_not_found(self):
        token = self._token()
        res = self.client.get(
            f"/api/v1/appointments/{self.other_appt.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.get_json()["code"], "not_found")

    def test_detail_missing(self):
        token = self._token()
        res = self.client.get(
            "/api/v1/appointments/99999",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 404)

    def test_invalid_token(self):
        res = self.client.get(
            "/api/v1/appointments",
            headers={"Authorization": "Bearer garbage"},
        )
        self.assertEqual(res.status_code, 401)

    def test_availability_lists_slots(self):
        token = self._token()
        res = self.client.get(
            "/api/v1/appointments/availability",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("slots", data)
        self.assertIn("tipi", data)
        self.assertTrue(len(data["slots"]) > 0)
        self.assertIn("data_appuntamento", data["slots"][0])
        self.assertIn("ora", data["slots"][0])
        self.assertTrue(any(t["value"] == "check" for t in data["tipi"]))

    def test_book_slot(self):
        token = self._token()
        slot = self._next_free_slot_iso()
        res = self.client.post(
            "/api/v1/appointments",
            headers={"Authorization": f"Bearer {token}"},
            json={"data_appuntamento": slot, "tipo": "check", "note": "Da app"},
        )
        self.assertEqual(res.status_code, 201, res.get_json())
        body = res.get_json()
        self.assertEqual(body["tipo"], "check")
        self.assertEqual(body["stato"], "in_attesa")
        self.assertEqual(body["note"], "Da app")

        # Slot non più disponibile
        res2 = self.client.post(
            "/api/v1/appointments",
            headers={"Authorization": f"Bearer {token}"},
            json={"data_appuntamento": slot, "tipo": "check"},
        )
        self.assertEqual(res2.status_code, 409)
        self.assertEqual(res2.get_json()["code"], "slot_unavailable")


if __name__ == "__main__":
    unittest.main()
