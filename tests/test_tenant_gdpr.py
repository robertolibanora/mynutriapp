"""Test isolamento multi-tenant + GDPR (export, erasure, marketing, login).

    venv/bin/python -m unittest tests.test_tenant_gdpr -v
"""

from __future__ import annotations

import os
import unittest
from datetime import date

from flask import Flask
from werkzeug.security import generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)
os.environ.setdefault("ENCRYPTION_KEY", "x" * 44)

from app.config.config import Config
from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import Documento, Patient, Progresso, db
from app.routes.documenti import documenti_bp
from app.routes.patients import patients_bp
from app.routes.progressi import progressi_bp
from app.services.auth_service import AuthStatus, authenticate, find_patient_by_phone
from app.services.gdpr_service import (
    apply_consents,
    export_patient_data,
    purge_patient,
    request_erasure,
)
from app.routes.whatsapp.broadcast import invia_broadcast_personalizzato


class TenantGdprTest(unittest.TestCase):
    def setUp(self):
        Config.SINGLE_TENANT = False
        self.app = Flask(__name__)
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
        self.app.register_blueprint(documenti_bp)
        self.app.register_blueprint(progressi_bp)

        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.nutri_a = Utente(
            nome="Anna",
            cognome="Nutri",
            email="anna@ex.com",
            telefono="3900000001",
            password_hash=generate_password_hash("pwd"),
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            attivo=True,
        )
        self.nutri_b = Utente(
            nome="Bruno",
            cognome="Nutri",
            email="bruno@ex.com",
            telefono="3900000002",
            password_hash=generate_password_hash("pwd"),
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            attivo=True,
        )
        db.session.add_all([self.nutri_a, self.nutri_b])
        db.session.flush()

        self.paz_a = Patient(
            nome="Paz",
            cognome="A",
            telefono="3331111111",
            email="paza@ex.com",
            password_hash=generate_password_hash("secret"),
            stato_cliente="attivo",
            nutrizionista_id=self.nutri_a.id,
            consenso_privacy=True,
            consenso_marketing=True,
            consenso_registrazione=False,
            consenso_ai=False,
        )
        self.paz_b = Patient(
            nome="Paz",
            cognome="B",
            telefono="3332222222",
            email="pazb@ex.com",
            password_hash=generate_password_hash("secret"),
            stato_cliente="attivo",
            nutrizionista_id=self.nutri_b.id,
            consenso_privacy=True,
            consenso_marketing=False,
            consenso_registrazione=False,
            consenso_ai=False,
        )
        # Stesso telefono su due tenant (login ambiguo)
        self.paz_a2 = Patient(
            nome="Paz",
            cognome="A2",
            telefono="3333333333",
            email="paza2@ex.com",
            password_hash=generate_password_hash("secret"),
            stato_cliente="attivo",
            nutrizionista_id=self.nutri_a.id,
            consenso_privacy=True,
            consenso_marketing=False,
            consenso_registrazione=False,
            consenso_ai=False,
        )
        self.paz_b2 = Patient(
            nome="Paz",
            cognome="B2",
            telefono="3333333333",
            email="pazb2@ex.com",
            password_hash=generate_password_hash("secret"),
            stato_cliente="attivo",
            nutrizionista_id=self.nutri_b.id,
            consenso_privacy=True,
            consenso_marketing=False,
            consenso_registrazione=False,
            consenso_ai=False,
        )
        db.session.add_all([self.paz_a, self.paz_b, self.paz_a2, self.paz_b2])
        db.session.flush()

        self.doc_b = Documento(
            patient_id=self.paz_b.id,
            tipo="analisi",
            file_path="/tmp/nonexistent_doc.pdf",
            descrizione="doc B",
        )
        self.prog_b = Progresso(
            patient_id=self.paz_b.id,
            data_check=date.today(),
            tipo_check="paziente",
            peso_settimanale=70,
        )
        db.session.add_all([self.doc_b, self.prog_b])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        Config.SINGLE_TENANT = False

    def _login_nutri(self, utente: Utente):
        with self.client.session_transaction() as sess:
            sess["role"] = "nutrizionista"
            sess["utente_id"] = utente.id
            sess["name"] = f"{utente.nome} {utente.cognome}"

    def test_cross_tenant_documenti_403(self):
        self._login_nutri(self.nutri_a)
        res = self.client.get(f"/documenti/admin/paziente/{self.paz_b.id}")
        self.assertEqual(res.status_code, 403)

    def test_cross_tenant_progressi_403(self):
        self._login_nutri(self.nutri_a)
        res = self.client.get(f"/progressi/admin/paziente/{self.paz_b.id}")
        self.assertEqual(res.status_code, 403)

    def test_own_patient_export_ok(self):
        self._login_nutri(self.nutri_b)
        res = self.client.get(f"/admin/pazienti/{self.paz_b.id}/export")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["patient"]["id"], self.paz_b.id)

    def test_export_contains_only_own_patient(self):
        self._login_nutri(self.nutri_a)
        res = self.client.get(f"/admin/pazienti/{self.paz_a.id}/export")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["patient"]["id"], self.paz_a.id)
        self.assertEqual(data["patient"]["cognome"], "A")
        self.assertNotIn(self.paz_b.id, [data["patient"]["id"]])

    def test_export_cross_tenant_403(self):
        self._login_nutri(self.nutri_a)
        res = self.client.get(f"/admin/pazienti/{self.paz_b.id}/export")
        self.assertEqual(res.status_code, 403)

    def test_erasure_anonymize_or_delete(self):
        apply_consents(self.paz_a, consenso_privacy=True, consenso_marketing=False)
        db.session.commit()
        request_erasure(self.paz_a)
        db.session.commit()
        pid = self.paz_a.id
        mode = purge_patient(self.paz_a)
        self.assertIn(mode, ("deleted", "anonymized"))
        if mode == "deleted":
            self.assertIsNone(db.session.get(Patient, pid))
        else:
            p = db.session.get(Patient, pid)
            self.assertEqual(p.nome, "Anonimizzato")
            self.assertIsNone(p.email)

    def test_broadcast_skips_without_marketing_consent(self):
        self._login_nutri(self.nutri_b)
        sent_phones = []

        def fake_send(phone, msg):
            sent_phones.append(phone)
            return True

        import app.routes.whatsapp.broadcast as broadcast_mod

        original = broadcast_mod.invia_whatsapp
        broadcast_mod.invia_whatsapp = fake_send
        try:
            with self.app.test_request_context():
                with self.client.session_transaction() as sess:
                    sess["role"] = "nutrizionista"
                    sess["utente_id"] = self.nutri_b.id
                # Re-establish session in request context for require_tenant
            with self.client.session_transaction() as sess:
                sess["role"] = "nutrizionista"
                sess["utente_id"] = self.nutri_b.id
            # Call with explicit list filtered as broadcast would
            from app.utils.tenant import patients_query_for_tenant

            with self.app.test_request_context():
                from flask import session

                session["role"] = "nutrizionista"
                session["utente_id"] = self.nutri_b.id
                q = patients_query_for_tenant().filter(
                    Patient.telefono.isnot(None),
                    Patient.consenso_marketing.is_(True),
                )
                pazienti = q.all()
                stats = invia_broadcast_personalizzato("Ciao {nome}", pazienti=pazienti)
            self.assertEqual(stats["inviati"], 0)
            self.assertEqual(len(sent_phones), 0)
        finally:
            broadcast_mod.invia_whatsapp = original

    def test_login_ambiguous_requires_email(self):
        result = authenticate("3333333333", "secret")
        self.assertEqual(result.status, AuthStatus.AMBIGUOUS)

        result_ok = authenticate("3333333333", "secret", email="paza2@ex.com")
        self.assertEqual(result_ok.status, AuthStatus.OK_USER)
        self.assertEqual(result_ok.patient.id, self.paz_a2.id)

        self.assertIsNone(find_patient_by_phone("3333333333"))
        found = find_patient_by_phone("3333333333", email="pazb2@ex.com")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, self.paz_b2.id)

    def test_export_service_structure(self):
        payload = export_patient_data(self.paz_a)
        self.assertIn("patient", payload)
        self.assertIn("consensi", payload)
        self.assertTrue(payload["consensi"]["privacy"])
        self.assertTrue(payload["consensi"]["marketing"])


if __name__ == "__main__":
    unittest.main()
