"""Test revisione umana diario (Fase 5).

    venv/bin/python -m unittest tests.test_diary_review -v
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime

from flask import Flask
from werkzeug.security import generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)

from app.config.config import Config
from app.models import (
    Consultation,
    ConsultationStato,
    DiaryEntry,
    Patient,
    Transcript,
    Utente,
    db,
)
from app.routes.consultations_audio import consultations_audio_bp


CONTENUTO = {
    "peso_kg": 70.0,
    "misure": {"vita_cm": 80, "fianchi_cm": None, "massa_grassa_pct": None},
    "aderenza_piano": "media",
    "sintomi_riportati": [],
    "difficolta_segnalate": [],
    "abitudini_alimentari": ["colazione ok"],
    "attivita_fisica": None,
    "obiettivi_concordati": [],
    "modifiche_al_piano": [],
    "note_cliniche": None,
    "prossimo_controllo": None,
    "riassunto": "Riassunto iniziale del colloquio.",
}


class DiaryReviewApiTest(unittest.TestCase):
    def setUp(self):
        Config.JOB_BACKEND = "sync"
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="t",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            WTF_CSRF_ENABLED=False,
        )
        db.init_app(self.app)
        self.app.register_blueprint(consultations_audio_bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.owner = Utente(nome="N", cognome="U", email="n@ex.com", attivo=True)
        self.other = Utente(nome="A", cognome="B", email="a@ex.com", attivo=True)
        db.session.add_all([self.owner, self.other])
        db.session.flush()

        self.patient = Patient(
            password_hash=generate_password_hash("x"),
            telefono="+391234567890",
            nome="Paolo",
            cognome="Verdi",
            sesso="M",
            data_nascita=datetime(1990, 1, 1).date(),
            altezza_cm=175,
            peso_iniziale=80,
            consenso_registrazione=True,
            nutrizionista_id=self.owner.id,
        )
        db.session.add(self.patient)
        db.session.flush()

        self.consultation = Consultation(
            patient_id=self.patient.id,
            nutrizionista_id=self.owner.id,
            data_colloquio=datetime.utcnow(),
            stato=ConsultationStato.ELABORATO,
        )
        db.session.add(self.consultation)
        db.session.flush()
        db.session.add(
            Transcript(
                consultation_id=self.consultation.id,
                testo="Trascrizione di prova",
                lingua="it",
                provider="fake",
                modello="fake",
            )
        )
        db.session.add(
            DiaryEntry(
                consultation_id=self.consultation.id,
                patient_id=self.patient.id,
                contenuto_json=CONTENUTO,
                riassunto_testo=CONTENUTO["riassunto"],
                modello_usato="claude-test",
            )
        )
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["role"] = "admin"
            sess["utente_id"] = self.owner.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_get_diary_flags_da_revisionare(self):
        res = self.client.get(f"/api/consultations/{self.consultation.id}/diary")
        self.assertEqual(res.status_code, 200, res.get_json())
        body = res.get_json()
        self.assertTrue(body["da_revisionare"])
        self.assertFalse(body["confermato"])
        self.assertFalse(body["valido_storico"])
        self.assertTrue(body["diary_entry"]["da_revisionare"])
        self.assertIn("Trascrizione", body["transcript"]["testo"])

    def test_patch_sets_modificato_manualmente(self):
        updated = dict(CONTENUTO)
        updated["riassunto"] = "Riassunto modificato dal nutrizionista."
        res = self.client.patch(
            f"/api/consultations/{self.consultation.id}/diary",
            json={"contenuto_json": updated, "riassunto_testo": updated["riassunto"]},
        )
        self.assertEqual(res.status_code, 200, res.get_json())
        entry = DiaryEntry.query.filter_by(consultation_id=self.consultation.id).one()
        self.assertTrue(entry.modificato_manualmente)
        self.assertEqual(entry.riassunto_testo, updated["riassunto"])

    def test_confirm(self):
        res = self.client.post(
            f"/api/consultations/{self.consultation.id}/diary/confirm"
        )
        self.assertEqual(res.status_code, 200, res.get_json())
        body = res.get_json()
        self.assertTrue(body["confermato"])
        self.assertFalse(body["da_revisionare"])
        self.assertTrue(body["valido_storico"])
        db.session.refresh(self.consultation)
        self.assertEqual(self.consultation.stato, ConsultationStato.CONFERMATO)
        entry = DiaryEntry.query.one()
        self.assertEqual(entry.revisionato_da, self.owner.id)
        self.assertIsNotNone(entry.revisionato_il)

    def test_patch_blocked_when_confirmed(self):
        self.client.post(f"/api/consultations/{self.consultation.id}/diary/confirm")
        res = self.client.patch(
            f"/api/consultations/{self.consultation.id}/diary",
            json={"riassunto_testo": "non deve passare"},
        )
        self.assertEqual(res.status_code, 409)
        self.assertIn("post-confirm", res.get_json()["error"])

    def test_post_confirm_amend(self):
        self.client.post(f"/api/consultations/{self.consultation.id}/diary/confirm")
        updated = dict(CONTENUTO)
        updated["riassunto"] = "Correzione dopo conferma."
        res = self.client.patch(
            f"/api/consultations/{self.consultation.id}/diary/post-confirm",
            json={
                "contenuto_json": updated,
                "riassunto_testo": updated["riassunto"],
                "motivo": "typo",
            },
        )
        self.assertEqual(res.status_code, 200, res.get_json())
        entry = DiaryEntry.query.one()
        self.assertEqual(entry.riassunto_testo, updated["riassunto"])
        self.assertTrue(entry.modificato_manualmente)
        self.assertTrue(res.get_json()["confermato"])

    def test_reject_regenerates(self):
        # mock extract job to recreate entry quickly
        from unittest import mock
        from app.schemas.diary_extraction import DiaryExtractionSchema

        def fake_extract(self_ex, text):
            return DiaryExtractionSchema.model_validate(CONTENUTO)

        with mock.patch(
            "app.services.diario_extraction_service.OpenAIDiaryExtractor.extract",
            fake_extract,
        ):
            res = self.client.post(
                f"/api/consultations/{self.consultation.id}/diary/reject"
            )
        self.assertEqual(res.status_code, 202, res.get_json())
        db.session.refresh(self.consultation)
        # dopo sync extract torna ELABORATO
        self.assertEqual(self.consultation.stato, ConsultationStato.ELABORATO)
        self.assertIsNotNone(self.consultation.diary_entry)
        self.assertTrue(res.get_json().get("in_progress") or res.get_json().get("job") == "accepted")

    def test_non_owner_forbidden(self):
        from app.config.config import Config

        Config.SINGLE_TENANT = False
        try:
            with self.client.session_transaction() as sess:
                sess["utente_id"] = self.other.id
            res = self.client.get(f"/api/consultations/{self.consultation.id}/diary")
            self.assertEqual(res.status_code, 403)
        finally:
            Config.SINGLE_TENANT = True


if __name__ == "__main__":
    unittest.main()
