"""Test redesign patient-centric: search, note, timeline, attività, isolation.

    venv/bin/python -m unittest tests.test_patient_centric -v
"""

from __future__ import annotations

import os
import unittest
from datetime import date, datetime, timedelta

from flask import Flask
from werkzeug.security import generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)
os.environ.setdefault("ENCRYPTION_KEY", "x" * 44)

from app.config.config import Config
from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import Activity, Appuntamento, DietPlan, Patient, PatientNote, db
from app.routes.attivita import attivita_bp
from app.routes.patients import patients_bp
from app.services.patient_search_service import search_patients
from app.services.patient_timeline_service import get_patient_timeline
from app.utils.db_schema import ensure_activity_notes_schema


class PatientCentricTest(unittest.TestCase):
    def setUp(self):
        Config.SINGLE_TENANT = False
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.app = Flask(
            __name__,
            template_folder=os.path.join(root, "templates"),
            static_folder=os.path.join(root, "static"),
        )
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            WTF_CSRF_ENABLED=False,
            SINGLE_TENANT=False,
        )
        db.init_app(self.app)
        self.app.register_blueprint(patients_bp)
        self.app.register_blueprint(attivita_bp)

        # Blueprint minimi referenziati dai template cartella paziente
        from app.routes.appuntamenti import appuntamenti_bp
        from app.routes.diete_plans import diete_plans_bp
        from app.routes.allenamenti import allenamenti_bp
        from app.routes.progressi import progressi_bp
        from app.routes.documenti import documenti_bp
        from app.routes.diario_ui import diario_ui_bp
        from app.routes.whatsapp.broadcast_routes import broadcast_bp
        from app.routes.diete import diete_bp
        from app.routes.agenda import agenda_bp

        from app.routes.dashboard import dashboard_bp
        from app.routes.auth import auth_bp
        from app.routes.slot import slot_bp

        for bp in (
            appuntamenti_bp,
            diete_plans_bp,
            allenamenti_bp,
            progressi_bp,
            documenti_bp,
            diario_ui_bp,
            broadcast_bp,
            diete_bp,
            agenda_bp,
            dashboard_bp,
            auth_bp,
            slot_bp,
        ):
            if bp.name not in self.app.blueprints:
                self.app.register_blueprint(bp)

        @self.app.context_processor
        def _inject():
            from app.utils.admin_icons import admin_icon

            return {
                "admin_name": "Anna Nutri",
                "icon": admin_icon,
                "static_version": "1",
                "csrf_token": lambda: "test",
            }

        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.nutri_a = Utente(
            nome="Anna",
            cognome="Nutri",
            email="anna@pc.com",
            telefono="3910000001",
            password_hash=generate_password_hash("pwd"),
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            attivo=True,
        )
        self.nutri_b = Utente(
            nome="Bruno",
            cognome="Nutri",
            email="bruno@pc.com",
            telefono="3910000002",
            password_hash=generate_password_hash("pwd"),
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            attivo=True,
        )
        db.session.add_all([self.nutri_a, self.nutri_b])
        db.session.flush()

        self.paz_a = Patient(
            nome="Mario",
            cognome="Rossi",
            telefono="3331112222",
            email="mario@ex.com",
            password_hash=generate_password_hash("pwd"),
            nutrizionista_id=self.nutri_a.id,
            stato_cliente="attivo",
            data_nascita=date(1990, 1, 1),
            peso_iniziale=80,
        )
        self.paz_b = Patient(
            nome="Luigi",
            cognome="Verdi",
            telefono="3339998888",
            email="luigi@ex.com",
            password_hash=generate_password_hash("pwd"),
            nutrizionista_id=self.nutri_b.id,
            stato_cliente="attivo",
        )
        db.session.add_all([self.paz_a, self.paz_b])
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        Config.SINGLE_TENANT = False

    def _login_a(self):
        with self.client.session_transaction() as sess:
            sess["role"] = "nutrizionista"
            sess["utente_id"] = self.nutri_a.id
            sess["name"] = "Anna Nutri"

    def test_search_tenant_scoped(self):
        self._login_a()
        with self.app.test_request_context():
            from flask import session

            session["role"] = "nutrizionista"
            session["utente_id"] = self.nutri_a.id
            results = search_patients("Mario", limit=8)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["id"], self.paz_a.id)
            results_other = search_patients("Luigi", limit=8)
            self.assertEqual(results_other, [])

    def test_search_api_endpoint(self):
        self._login_a()
        res = self.client.get("/admin/pazienti/api/search?q=Rossi")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["cognome"], "Rossi")

    def test_cross_tenant_detail_forbidden(self):
        self._login_a()
        res = self.client.get(f"/admin/pazienti/{self.paz_b.id}")
        self.assertIn(res.status_code, (403, 302, 404))

    def test_note_crud_ownership(self):
        self._login_a()
        res = self.client.post(
            f"/admin/pazienti/{self.paz_a.id}/note",
            data={"body": "Nota di prova"},
            follow_redirects=False,
        )
        self.assertEqual(res.status_code, 302)
        note = PatientNote.query.filter_by(patient_id=self.paz_a.id).first()
        self.assertIsNotNone(note)
        self.assertEqual(note.body, "Nota di prova")
        self.assertEqual(note.utente_id, self.nutri_a.id)

    def test_timeline_aggregates_real_data(self):
        db.session.add(
            DietPlan(
                patient_id=self.paz_a.id,
                professional_id=self.nutri_a.id,
                title="Piano test",
                status="draft",
            )
        )
        db.session.add(
            Appuntamento(
                patient_id=self.paz_a.id,
                utente_id=self.nutri_a.id,
                created_by="admin",
                data_appuntamento=datetime.now() + timedelta(days=1),
                tipo="check",
                stato="confermato",
            )
        )
        db.session.commit()
        with self.app.test_request_context():
            from flask import session

            session["role"] = "nutrizionista"
            session["utente_id"] = self.nutri_a.id
            tl = get_patient_timeline(patient=self.paz_a, page=1, per_page=50)
        tipi = {e["tipo"] for e in tl["items"]}
        self.assertIn("paziente", tipi)
        self.assertIn("dieta", tipi)
        self.assertIn("appuntamento", tipi)

    def test_attivita_page_and_manual(self):
        self._login_a()
        res = self.client.get("/admin/attivita/")
        self.assertEqual(res.status_code, 200)
        res = self.client.post(
            "/admin/attivita/nuova",
            data={"title": "Ricontattare Mario", "priority": "high"},
            follow_redirects=False,
        )
        self.assertEqual(res.status_code, 302)
        act = Activity.query.filter_by(utente_id=self.nutri_a.id).first()
        self.assertIsNotNone(act)
        self.assertEqual(act.title, "Ricontattare Mario")

    def test_scadenze_redirects_to_attivita(self):
        self._login_a()
        res = self.client.get("/admin/pazienti/scadenze", follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/admin/attivita", res.headers.get("Location", ""))

    def test_patient_detail_tabs(self):
        self._login_a()
        res = self.client.get(f"/admin/pazienti/{self.paz_a.id}?tab=timeline")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Timeline", res.data)
        res = self.client.get(f"/admin/pazienti/{self.paz_a.id}?tab=diete")
        self.assertEqual(res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
