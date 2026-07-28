"""Test API upload audio consultation (Fase 2).

Eseguibili senza MySQL (SQLite in-memory):

    venv/bin/python -m unittest tests.test_consultation_audio -v
"""

from __future__ import annotations

import io
import os
import struct
import tempfile
import unittest
import wave
from datetime import datetime
from pathlib import Path

from flask import Flask
from werkzeug.security import generate_password_hash

# Chiave di test prima di importare moduli che leggono Config
os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)

from app.config.config import Config
from app.models import (
    AudioRecording,
    Consultation,
    ConsultationStato,
    Patient,
    Utente,
    db,
)
from app.routes.consultations_audio import consultations_audio_bp
from app.schemas.diario import AudioRecordingResponse


def _make_wav_bytes(duration_sec: float = 0.5, rate: int = 8000) -> bytes:
    nframes = int(rate * duration_sec)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        silence = struct.pack("<h", 0) * nframes
        wf.writeframes(silence)
    return buf.getvalue()


class ConsultationAudioApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="diario_audio_")
        Config.AUDIO_STORAGE_PATH = self.tmp_dir
        Config.AUDIO_ENCRYPTION_KEY = "ab" * 32
        Config.AUDIO_MAX_BYTES = 50 * 1024  # 50 KiB per test size
        Config.AUDIO_MAX_DURATION_SEC = 3600.0
        Config.AUDIO_CHUNK_SIZE = 1024
        Config.AUDIO_ALLOWED_MIME = {
            "audio/mpeg",
            "audio/mp4",
            "audio/webm",
            "audio/ogg",
            "audio/wav",
        }

        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config["SECRET_KEY"] = "test-secret"
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        self.app.config["WTF_CSRF_ENABLED"] = False

        db.init_app(self.app)
        self.app.register_blueprint(consultations_audio_bp)

        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.owner = Utente(
            nome="Enrico",
            cognome="Nutri",
            email="owner@example.com",
            telefono="+390000000001",
            attivo=True,
        )
        self.other = Utente(
            nome="Altro",
            cognome="Doc",
            email="other@example.com",
            telefono="+390000000002",
            attivo=True,
        )
        db.session.add_all([self.owner, self.other])
        db.session.flush()

        self.patient = Patient(
            password_hash=generate_password_hash("secret123"),
            telefono="+391111111111",
            nome="Mario",
            cognome="Rossi",
            sesso="M",
            data_nascita=datetime(1990, 1, 1).date(),
            altezza_cm=175,
            peso_iniziale=70,
            consenso_registrazione=True,
            consenso_ai=True,
            nutrizionista_id=self.owner.id,
        )
        db.session.add(self.patient)
        db.session.flush()

        self.consultation = Consultation(
            patient_id=self.patient.id,
            nutrizionista_id=self.owner.id,
            data_colloquio=datetime.utcnow(),
            stato=ConsultationStato.BOZZA,
        )
        db.session.add(self.consultation)
        db.session.commit()

        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        # cleanup files
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                Path(root, name).unlink(missing_ok=True)
            for name in dirs:
                Path(root, name).rmdir()
        Path(self.tmp_dir).rmdir()

    def _login_as(self, utente_id: int):
        with self.client.session_transaction() as sess:
            sess["role"] = "admin"
            sess["utente_id"] = utente_id
            sess["name"] = "Test Nutri"

    def _post_audio(self, data: bytes, filename: str, content_type: str, consultation_id=None):
        cid = consultation_id if consultation_id is not None else self.consultation.id
        return self.client.post(
            f"/api/consultations/{cid}/audio",
            data={"audio": (io.BytesIO(data), filename, content_type)},
            content_type="multipart/form-data",
        )

    def test_upload_valido(self):
        self._login_as(self.owner.id)
        wav = _make_wav_bytes(0.25)
        resp = self._post_audio(wav, "colloquio.wav", "audio/wav")
        self.assertEqual(resp.status_code, 201, resp.get_json())
        body = resp.get_json()
        self.assertTrue(body["cifrato"])
        self.assertEqual(body["mime_type"], "audio/wav")
        self.assertEqual(len(body["checksum_sha256"]), 64)
        self.assertGreater(body["dimensione_byte"], 0)
        self.assertIsNotNone(body["durata_sec"])
        self.assertGreater(body["durata_sec"], 0)

        rec = AudioRecording.query.filter_by(consultation_id=self.consultation.id).one()
        self.assertTrue(Path(rec.path_file).is_file())
        self.assertTrue(rec.cifrato)

        db.session.refresh(self.consultation)
        self.assertEqual(self.consultation.stato, ConsultationStato.CARICATO)

        # Response schema
        AudioRecordingResponse.model_validate(body)

    def test_mime_type_errato(self):
        self._login_as(self.owner.id)
        resp = self._post_audio(b"not-an-audio", "notes.txt", "text/plain")
        self.assertEqual(resp.status_code, 415, resp.get_json())
        self.assertIn("MIME", resp.get_json()["error"])
        self.assertEqual(
            AudioRecording.query.filter_by(consultation_id=self.consultation.id).count(),
            0,
        )
        # nessun file orfano nella cartella consultation
        cons_dir = Path(self.tmp_dir) / str(self.patient.id) / str(self.consultation.id)
        if cons_dir.exists():
            leftovers = [p for p in cons_dir.iterdir() if p.is_file()]
            self.assertEqual(leftovers, [])

    def test_file_troppo_grande(self):
        self._login_as(self.owner.id)
        # > AUDIO_MAX_BYTES (50 KiB)
        big = b"\x00" * (Config.AUDIO_MAX_BYTES + 1000)
        resp = self._post_audio(big, "huge.wav", "audio/wav")
        self.assertEqual(resp.status_code, 413, resp.get_json())
        self.assertIn("grande", resp.get_json()["error"].lower())
        self.assertEqual(
            AudioRecording.query.filter_by(consultation_id=self.consultation.id).count(),
            0,
        )

    def test_consenso_mancante(self):
        self.patient.consenso_registrazione = False
        db.session.commit()
        self._login_as(self.owner.id)
        wav = _make_wav_bytes(0.2)
        resp = self._post_audio(wav, "colloquio.wav", "audio/wav")
        self.assertEqual(resp.status_code, 403, resp.get_json())
        self.assertIn("consenso_registrazione", resp.get_json()["error"])

    def test_utente_non_proprietario(self):
        self._login_as(self.other.id)
        wav = _make_wav_bytes(0.2)
        resp = self._post_audio(wav, "colloquio.wav", "audio/wav")
        self.assertEqual(resp.status_code, 403, resp.get_json())
        self.assertIn("proprietario", resp.get_json()["error"].lower())

    def test_soft_delete_preserva_stato_db_senza_file(self):
        self._login_as(self.owner.id)
        wav = _make_wav_bytes(0.2)
        up = self._post_audio(wav, "colloquio.wav", "audio/wav")
        self.assertEqual(up.status_code, 201)
        path = Path(up.get_json()["path_file"])
        self.assertTrue(path.is_file())

        deleted = self.client.delete(
            f"/api/consultations/{self.consultation.id}/audio"
        )
        self.assertEqual(deleted.status_code, 200, deleted.get_json())
        self.assertIsNotNone(deleted.get_json()["cancellato_il"])
        self.assertFalse(path.exists())
        # riga ancora presente
        rec = AudioRecording.query.filter_by(consultation_id=self.consultation.id).one()
        self.assertIsNotNone(rec.cancellato_il)


if __name__ == "__main__":
    unittest.main()
