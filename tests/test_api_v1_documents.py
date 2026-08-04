"""Test API /api/v1/documents.

    venv/bin/python -m unittest tests.test_api_v1_documents -v
"""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask
from werkzeug.security import generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)
os.environ.setdefault("ENCRYPTION_KEY", "x" * 44)

from app.api.v1 import api_v1_bp
from app.models.models import Documento, Patient, db
from tests._fixtures import make_nutrizionista
from app.services import document_service as document_service_mod


class ApiV1DocumentsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.upload_dir = Path(self.tmp.name) / "documenti"
        self.upload_dir.mkdir()

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

        existing = self.upload_dir / "existing.pdf"
        existing.write_bytes(b"%PDF-1.4 existing")
        self.own = Documento(
            patient_id=self.patient.id,
            tipo="analisi",
            file_path=str(existing),
            descrizione="Analisi sangue",
        )
        other_file = self.upload_dir / "other.pdf"
        other_file.write_bytes(b"%PDF-1.4 other")
        self.other_doc = Documento(
            patient_id=self.other.id,
            tipo="referto",
            file_path=str(other_file),
            descrizione="Altrui",
        )
        db.session.add_all([self.own, self.other_doc])
        db.session.commit()
        self.client = self.app.test_client()

        self._folder_patch = mock.patch.object(
            document_service_mod,
            "get_upload_folder",
            return_value=str(self.upload_dir),
        )
        self._folder_patch.start()

    def tearDown(self):
        self._folder_patch.stop()
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

    def test_list_only_own_no_path(self):
        token = self._token()
        res = self.client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 200)
        docs = res.get_json()["documents"]
        ids = {d["id"] for d in docs}
        self.assertIn(self.own.id, ids)
        self.assertNotIn(self.other_doc.id, ids)
        self.assertNotIn("file_path", docs[0])
        self.assertIn("filename", docs[0])

    def test_detail_other_404(self):
        token = self._token()
        bad = self.client.get(
            f"/api/v1/documents/{self.other_doc.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(bad.status_code, 404)

    def test_upload_download_delete(self):
        token = self._token()
        data = {
            "tipo": "pdf_altro",
            "descrizione": "Referto prova",
            "file": (io.BytesIO(b"%PDF-1.4 upload"), "prova.pdf"),
        }
        created = self.client.post(
            "/api/v1/documents",
            data=data,
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(created.status_code, 201)
        body = created.get_json()
        self.assertEqual(body["tipo"], "pdf_altro")
        self.assertNotIn("file_path", body)
        doc_id = body["id"]

        download = self.client.get(
            f"/api/v1/documents/{doc_id}/download",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(download.status_code, 200)
        self.assertTrue(download.data.startswith(b"%PDF"))

        other = self._token("3330001111")
        denied = self.client.get(
            f"/api/v1/documents/{doc_id}/download",
            headers={"Authorization": f"Bearer {other}"},
        )
        self.assertEqual(denied.status_code, 404)

        deleted = self.client.delete(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(deleted.status_code, 200)

        missing = self.client.get(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(missing.status_code, 404)

    def test_upload_invalid_tipo(self):
        token = self._token()
        res = self.client.post(
            "/api/v1/documents",
            data={
                "tipo": "invalido",
                "file": (io.BytesIO(b"%PDF-1.4"), "x.pdf"),
            },
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
