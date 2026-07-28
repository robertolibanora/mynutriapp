"""Test trascrizione consultation (Fase 3).

    venv/bin/python -m unittest tests.test_consultation_transcription -v
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
from unittest import mock

from flask import Flask
from werkzeug.security import generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)

from app.config.config import Config
from app.models import (
    AudioRecording,
    Consultation,
    ConsultationStato,
    Patient,
    Transcript,
    Utente,
    db,
)
from app.routes.consultations_audio import consultations_audio_bp
from app.services.transcription.base import (
    TranscriptionResult,
    TransientTranscriptionError,
)
from app.services import transcription as transcription_pkg
from app.utils.audio_crypto import encrypt_file_streaming, load_audio_key


def _make_wav_bytes(duration_sec: float = 0.25, rate: int = 8000) -> bytes:
    nframes = int(rate * duration_sec)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<h", 0) * nframes)
    return buf.getvalue()


class FakeTranscriber:
    provider_name = "fake"

    def __init__(self, text: str = "Ho mangiato pasta al pomodoro"):
        self.text = text
        self.calls = 0
        self.seen_paths: list[str] = []

    def transcribe(self, audio_path: str, *, language: str) -> TranscriptionResult:
        self.calls += 1
        self.seen_paths.append(audio_path)
        assert Path(audio_path).is_file(), "temp audio deve esistere durante transcribe"
        return TranscriptionResult(
            text=self.text,
            language=language,
            provider=self.provider_name,
            model="fake-1",
            duration_sec=0.01,
        )


class FlakyTranscriber(FakeTranscriber):
    def __init__(self, fail_times: int = 2):
        super().__init__()
        self.fail_times = fail_times

    def transcribe(self, audio_path: str, *, language: str) -> TranscriptionResult:
        self.calls += 1
        self.seen_paths.append(audio_path)
        if self.calls <= self.fail_times:
            raise TransientTranscriptionError("temporaneo")
        return TranscriptionResult(
            text=self.text,
            language=language,
            provider=self.provider_name,
            model="fake-1",
            duration_sec=0.02,
        )


class BoomTranscriber(FakeTranscriber):
    def transcribe(self, audio_path: str, *, language: str) -> TranscriptionResult:
        self.calls += 1
        self.seen_paths.append(audio_path)
        raise RuntimeError("fallimento permanente simulato")


class TranscriptionApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="diario_tx_")
        Config.AUDIO_STORAGE_PATH = self.tmp_dir
        Config.AUDIO_ENCRYPTION_KEY = "ab" * 32
        Config.AUDIO_MAX_BYTES = 200_000
        Config.AUDIO_CHUNK_SIZE = 1024
        Config.AUDIO_ALLOWED_MIME = {"audio/wav"}
        Config.JOB_BACKEND = "sync"
        Config.TRANSCRIPTION_PROVIDER = "local_whisper"
        Config.TRANSCRIPTION_LANGUAGE = "it"
        Config.TRANSCRIPTION_MAX_ATTEMPTS = 3
        Config.TRANSCRIPTION_RETRY_BASE_SEC = 0.01
        transcription_pkg.reset_transcriber_cache()

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
            nome="Enrico", cognome="Nutri", email="owner@example.com", attivo=True
        )
        db.session.add(self.owner)
        db.session.flush()

        self.patient = Patient(
            password_hash=generate_password_hash("x"),
            telefono="+391234567890",
            nome="Mario",
            cognome="Rossi",
            sesso="M",
            data_nascita=datetime(1990, 1, 1).date(),
            altezza_cm=170,
            peso_iniziale=70,
            consenso_registrazione=True,
            nutrizionista_id=self.owner.id,
        )
        db.session.add(self.patient)
        db.session.flush()

        self.consultation = Consultation(
            patient_id=self.patient.id,
            nutrizionista_id=self.owner.id,
            data_colloquio=datetime.utcnow(),
            stato=ConsultationStato.CARICATO,
        )
        db.session.add(self.consultation)
        db.session.flush()

        # audio cifrato reale su disco
        plain = Path(self.tmp_dir) / "plain.wav"
        plain.write_bytes(_make_wav_bytes())
        enc = Path(self.tmp_dir) / str(self.patient.id) / str(self.consultation.id) / "a.wav.enc"
        enc.parent.mkdir(parents=True, exist_ok=True)
        encrypt_file_streaming(plain, enc, load_audio_key(Config.AUDIO_ENCRYPTION_KEY))
        plain.unlink()

        db.session.add(
            AudioRecording(
                consultation_id=self.consultation.id,
                path_file=str(enc),
                nome_originale="a.wav",
                mime_type="audio/wav",
                dimensione_byte=enc.stat().st_size,
                durata_sec=0.25,
                checksum_sha256="a" * 64,
                cifrato=True,
            )
        )
        db.session.commit()

        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["role"] = "admin"
            sess["utente_id"] = self.owner.id

        self.fake = FakeTranscriber()
        self._patcher = mock.patch(
            "app.services.diario_transcription_service.get_transcriber",
            return_value=self.fake,
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        transcription_pkg.reset_transcriber_cache()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
            for name in files:
                Path(root, name).unlink(missing_ok=True)
            for name in dirs:
                Path(root, name).rmdir()
        Path(self.tmp_dir).rmdir()

    def test_transcribe_success_and_status(self):
        resp = self.client.post(f"/api/consultations/{self.consultation.id}/transcribe")
        self.assertEqual(resp.status_code, 202, resp.get_json())
        self.assertEqual(self.fake.calls, 1)
        # temp rimosso
        for p in self.fake.seen_paths:
            self.assertFalse(Path(p).exists())

        st = self.client.get(f"/api/consultations/{self.consultation.id}/status")
        self.assertEqual(st.status_code, 200)
        body = st.get_json()
        self.assertEqual(body["stato"], "TRASCRITTO")
        self.assertFalse(body["in_progress"])
        self.assertIsNone(body["errore"])
        self.assertTrue(body["has_transcript"])

        tx = Transcript.query.filter_by(consultation_id=self.consultation.id).one()
        self.assertIn("pasta", tx.testo)
        self.assertEqual(tx.provider, "fake")
        self.assertEqual(tx.lingua, "it")
        self.assertEqual(tx.modello, "fake-1")

    def test_retry_transient_then_ok(self):
        flaky = FlakyTranscriber(fail_times=2)
        self._patcher.stop()
        self._patcher = mock.patch(
            "app.services.diario_transcription_service.get_transcriber",
            return_value=flaky,
        )
        self._patcher.start()

        resp = self.client.post(f"/api/consultations/{self.consultation.id}/transcribe")
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(flaky.calls, 3)
        db.session.refresh(self.consultation)
        self.assertEqual(self.consultation.stato, ConsultationStato.TRASCRITTO)

    def test_permanent_failure_sets_errore(self):
        boom = BoomTranscriber()
        self._patcher.stop()
        self._patcher = mock.patch(
            "app.services.diario_transcription_service.get_transcriber",
            return_value=boom,
        )
        self._patcher.start()

        resp = self.client.post(f"/api/consultations/{self.consultation.id}/transcribe")
        self.assertEqual(resp.status_code, 202)
        st = self.client.get(f"/api/consultations/{self.consultation.id}/status").get_json()
        self.assertEqual(st["stato"], "ERRORE")
        self.assertIn("fallimento permanente", st["errore"])
        for p in boom.seen_paths:
            self.assertFalse(Path(p).exists())

    def test_factory_selects_openai_from_config(self):
        Config.TRANSCRIPTION_PROVIDER = "openai_whisper"
        Config.OPENAI_API_KEY = "sk-test"
        transcription_pkg.reset_transcriber_cache()
        t = transcription_pkg.get_transcriber()
        from app.services.transcription.openai_whisper import OpenAIWhisperTranscriber

        self.assertIsInstance(t, OpenAIWhisperTranscriber)
        transcription_pkg.reset_transcriber_cache()
        Config.TRANSCRIPTION_PROVIDER = "local_whisper"
        t2 = transcription_pkg.get_transcriber()
        from app.services.transcription.local_whisper import LocalWhisperTranscriber

        self.assertIsInstance(t2, LocalWhisperTranscriber)


if __name__ == "__main__":
    unittest.main()
