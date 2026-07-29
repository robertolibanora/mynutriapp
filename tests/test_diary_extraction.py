"""Test estrazione diario (Fase 4).

    venv/bin/python -m unittest tests.test_diary_extraction -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from flask import Flask
from werkzeug.security import generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-should-never-leak-xxxxxx")

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
from app.schemas.diary_extraction import DiaryExtractionSchema
from app.services.diary_extraction_openai import (
    SYSTEM_PROMPT,
    parse_diary_json,
    redact_secrets,
)
from app.utils.anonymize import PLACEHOLDER, anonymize_text, deanonymize_structure


VALID_JSON = {
    "peso_kg": 72.5,
    "misure": {"vita_cm": 80, "fianchi_cm": None, "massa_grassa_pct": None},
    "aderenza_piano": "media",
    "sintomi_riportati": ["gonfiore"],
    "difficolta_segnalate": [],
    "abitudini_alimentari": ["colazione saltata"],
    "attivita_fisica": "camminate 3 volte a settimana",
    "obiettivi_concordati": ["ridurre zuccheri"],
    "modifiche_al_piano": [],
    "note_cliniche": f"Il {PLACEHOLDER} riferisce buon umore",
    "prossimo_controllo": "tra 4 settimane",
    "riassunto": "Colloquio su aderenza e attività fisica.",
}


class AnonymizeTest(unittest.TestCase):
    def test_replaces_name_phone_email(self):
        patient = Patient(
            password_hash="x",
            telefono="+393331112222",
            nome="Mario",
            cognome="Rossi",
            email="mario.rossi@example.com",
            sesso="M",
            data_nascita=datetime(1990, 1, 1).date(),
            altezza_cm=170,
            peso_iniziale=70,
        )
        text = (
            "Mario Rossi dice che Mario pesa 70 kg. "
            "Contatto +393331112222 o mario.rossi@example.com"
        )
        anon, mapping = anonymize_text(text, patient)
        self.assertNotIn("Mario", anon)
        self.assertNotIn("Rossi", anon)
        self.assertNotIn("3331112222", anon)
        self.assertNotIn("mario.rossi@example.com", anon)
        self.assertIn(PLACEHOLDER, anon)
        restored = mapping.restore_text(f"Nota su {PLACEHOLDER}")
        self.assertIn("Mario Rossi", restored)


class ParseSchemaTest(unittest.TestCase):
    def test_parse_valid(self):
        schema = parse_diary_json(json.dumps(VALID_JSON))
        self.assertEqual(schema.peso_kg, 72.5)
        self.assertEqual(schema.aderenza_piano, "media")

    def test_reject_markdown_fence_then_ok_if_json_inside(self):
        raw = "```json\n" + json.dumps(VALID_JSON) + "\n```"
        schema = parse_diary_json(raw)
        self.assertTrue(schema.riassunto)

    def test_reject_invalid(self):
        with self.assertRaises(Exception):
            parse_diary_json('{"peso_kg": "nope"}')

    def test_system_prompt_rules(self):
        self.assertIn("SOLO con JSON", SYSTEM_PROMPT)
        self.assertIn("NON inventare", SYSTEM_PROMPT)
        self.assertIn("NON formulare diagnosi", SYSTEM_PROMPT)


class RedactTest(unittest.TestCase):
    def test_redact_api_key(self):
        Config.OPENAI_API_KEY = "sk-test-key-should-never-leak-xxxxxx"
        msg = "error with sk-test-key-should-never-leak-xxxxxx inside"
        self.assertNotIn("sk-test-key-should-never-leak", redact_secrets(msg))


class ExtractionApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        Config.JOB_BACKEND = "sync"
        Config.OPENAI_API_KEY = "sk-test-key-should-never-leak-xxxxxx"
        Config.OPENAI_DIARY_MODEL = "gpt-4o-mini"

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

        self.owner = Utente(
            nome="N", cognome="U", email="n@example.com", attivo=True
        )
        db.session.add(self.owner)
        db.session.flush()
        self.patient = Patient(
            password_hash=generate_password_hash("x"),
            telefono="+391112223333",
            nome="Lucia",
            cognome="Bianchi",
            email="lucia@example.com",
            sesso="F",
            data_nascita=datetime(1985, 5, 5).date(),
            altezza_cm=165,
            peso_iniziale=60,
            consenso_registrazione=True,
            nutrizionista_id=self.owner.id,
        )
        db.session.add(self.patient)
        db.session.flush()
        self.consultation = Consultation(
            patient_id=self.patient.id,
            nutrizionista_id=self.owner.id,
            data_colloquio=datetime.utcnow(),
            stato=ConsultationStato.TRASCRITTO,
        )
        db.session.add(self.consultation)
        db.session.flush()
        db.session.add(
            Transcript(
                consultation_id=self.consultation.id,
                testo=(
                    "Lucia Bianchi dice di pesare 72 chili e di fare camminate. "
                    "Prossimo controllo tra 4 settimane."
                ),
                lingua="it",
                provider="fake",
                modello="fake",
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

    def test_extract_success(self):
        captured = {}

        def fake_extract(self_extractor, anonymized_transcript: str):
            captured["anon"] = anonymized_transcript
            self.assertNotIn("Lucia", anonymized_transcript)
            self.assertNotIn("Bianchi", anonymized_transcript)
            self.assertIn(PLACEHOLDER, anonymized_transcript)
            # simula output modello ancora anonimizzato
            return DiaryExtractionSchema.model_validate(VALID_JSON)

        with mock.patch(
            "app.services.diario_extraction_service.OpenAIDiaryExtractor.extract",
            fake_extract,
        ):
            resp = self.client.post(
                f"/api/consultations/{self.consultation.id}/extract"
            )
        self.assertEqual(resp.status_code, 202, resp.get_json())
        body = resp.get_json()
        self.assertNotIn("sk-test-key", json.dumps(body))

        db.session.refresh(self.consultation)
        self.assertEqual(self.consultation.stato, ConsultationStato.ELABORATO)
        entry = DiaryEntry.query.filter_by(
            consultation_id=self.consultation.id
        ).one()
        self.assertEqual(entry.modello_usato, "gpt-4o-mini")
        self.assertIn("aderenza_piano", entry.contenuto_json)
        # placeholder ripristinato nelle note
        self.assertIn("Lucia Bianchi", entry.contenuto_json["note_cliniche"])
        self.assertEqual(entry.riassunto_testo, VALID_JSON["riassunto"])

        st = self.client.get(
            f"/api/consultations/{self.consultation.id}/status"
        ).get_json()
        self.assertEqual(st["stato"], "ELABORATO")
        self.assertTrue(st["has_diary_entry"])

    def test_extract_parse_fail_no_partial_save(self):
        calls = {"n": 0}

        def fail_extract(self_extractor, anonymized_transcript: str):
            calls["n"] += 1
            from app.services.diary_extraction_openai import DiaryExtractionError

            raise DiaryExtractionError("Schema non valido dopo correzione")

        with mock.patch(
            "app.services.diario_extraction_service.OpenAIDiaryExtractor.extract",
            fail_extract,
        ):
            resp = self.client.post(
                f"/api/consultations/{self.consultation.id}/extract"
            )
        self.assertEqual(resp.status_code, 202)
        db.session.refresh(self.consultation)
        self.assertEqual(self.consultation.stato, ConsultationStato.ERRORE)
        self.assertIsNotNone(self.consultation.errore_pipeline)
        self.assertNotIn("sk-test-key", self.consultation.errore_pipeline)
        self.assertEqual(
            DiaryEntry.query.filter_by(consultation_id=self.consultation.id).count(),
            0,
        )

    def test_deanonymize_nested(self):
        patient = self.patient
        _, mapping = anonymize_text("Lucia Bianchi ok", patient)
        data = {"note_cliniche": f"Visita di {PLACEHOLDER}", "xs": [f"{PLACEHOLDER}"]}
        out = deanonymize_structure(data, mapping)
        self.assertEqual(out["note_cliniche"], "Visita di Lucia Bianchi")


if __name__ == "__main__":
    unittest.main()
