"""Test timeline / trends diario paziente (Fase 6).

    venv/bin/python -m unittest tests.test_diary_timeline -v
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta

from flask import Flask
from werkzeug.security import generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)

from app.models import (
    Consultation,
    ConsultationStato,
    DiaryEntry,
    Patient,
    Utente,
    db,
)
from app.routes.patients_diary_api import patients_diary_api_bp


def _contenuto(peso, aderenza="media", vita=None):
    return {
        "peso_kg": peso,
        "misure": {
            "vita_cm": vita,
            "fianchi_cm": None,
            "massa_grassa_pct": None,
        },
        "aderenza_piano": aderenza,
        "sintomi_riportati": [],
        "difficolta_segnalate": [],
        "abitudini_alimentari": [],
        "attivita_fisica": None,
        "obiettivi_concordati": [],
        "modifiche_al_piano": [],
        "note_cliniche": None,
        "prossimo_controllo": None,
        "riassunto": f"Riassunto peso {peso}",
    }


class DiaryTimelineApiTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="t",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            WTF_CSRF_ENABLED=False,
        )
        db.init_app(self.app)
        self.app.register_blueprint(patients_diary_api_bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.owner = Utente(nome="N", cognome="U", email="n@ex.com", attivo=True)
        self.other = Utente(nome="X", cognome="Y", email="x@ex.com", attivo=True)
        db.session.add_all([self.owner, self.other])
        db.session.flush()

        self.patient = Patient(
            password_hash=generate_password_hash("x"),
            telefono="+391111111111",
            nome="Sara",
            cognome="Neri",
            sesso="F",
            data_nascita=datetime(1992, 2, 2).date(),
            altezza_cm=165,
            peso_iniziale=68,
            consenso_registrazione=True,
            nutrizionista_id=self.owner.id,
        )
        db.session.add(self.patient)
        db.session.flush()

        base = datetime(2026, 1, 10, 10, 0, 0)
        # confermata più vecchia
        self._add_entry(base, ConsultationStato.CONFERMATO, 70.0, vita=80)
        # confermata recente
        self._add_entry(base + timedelta(days=30), ConsultationStato.CONFERMATO, 68.5, vita=78)
        # confermata senza peso (null saltato nei trend)
        self._add_entry(base + timedelta(days=45), ConsultationStato.CONFERMATO, None, vita=77)
        # pending (ELABORATO)
        self._add_entry(base + timedelta(days=50), ConsultationStato.ELABORATO, 67.0, vita=76)
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["role"] = "admin"
            sess["utente_id"] = self.owner.id

    def _add_entry(self, when, stato, peso, vita=None):
        c = Consultation(
            patient_id=self.patient.id,
            nutrizionista_id=self.owner.id,
            data_colloquio=when,
            stato=stato,
        )
        db.session.add(c)
        db.session.flush()
        db.session.add(
            DiaryEntry(
                consultation_id=c.id,
                patient_id=self.patient.id,
                contenuto_json=_contenuto(peso, vita=vita),
                riassunto_testo=f"Riassunto peso {peso}",
                modello_usato="test",
            )
        )
        return c

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_timeline_default_only_confirmed(self):
        res = self.client.get(f"/api/patients/{self.patient.id}/diary")
        self.assertEqual(res.status_code, 200, res.get_json())
        body = res.get_json()
        self.assertEqual(body["total"], 3)
        self.assertTrue(all(i["confermato"] for i in body["items"]))
        # ordine decrescente per data
        dates = [i["data_colloquio"] for i in body["items"]]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertIn("consultation_url", body["items"][0])
        self.assertIn("peso_kg", body["items"][0])
        self.assertIn("aderenza_piano", body["items"][0])

    def test_include_pending(self):
        res = self.client.get(
            f"/api/patients/{self.patient.id}/diary?include_pending=true"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["total"], 4)
        pending = [i for i in res.get_json()["items"] if i["da_revisionare"]]
        self.assertEqual(len(pending), 1)

    def test_date_filter_and_pagination(self):
        res = self.client.get(
            f"/api/patients/{self.patient.id}/diary"
            f"?from=2026-02-01&to=2026-03-31&per_page=1&page=1"
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["per_page"], 1)
        self.assertEqual(len(body["items"]), 1)
        self.assertTrue(body["has_next"] or body["total"] >= 1)

    def test_trends_skip_null_peso(self):
        res = self.client.get(f"/api/patients/{self.patient.id}/diary/trends")
        self.assertEqual(res.status_code, 200, res.get_json())
        series = res.get_json()["series"]
        # 2 pesi non-null (70 e 68.5); il None è saltato; pending escluso
        self.assertEqual(len(series["peso_kg"]), 2)
        self.assertEqual(series["peso_kg"][0]["value"], 70.0)
        self.assertEqual(series["peso_kg"][1]["value"], 68.5)
        # vita ha 3 punti confermati (anche dove peso null)
        self.assertEqual(len(series["vita_cm"]), 3)
        # ordine ascendente
        dates = [p["date"] for p in series["peso_kg"]]
        self.assertEqual(dates, sorted(dates))

    def test_non_owner_forbidden(self):
        with self.client.session_transaction() as sess:
            sess["utente_id"] = self.other.id
        res = self.client.get(f"/api/patients/{self.patient.id}/diary")
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
