"""Test auto-provision utente admin (fix redirect diario).

    venv/bin/python -m unittest tests.test_utente_ensure -v
"""

from __future__ import annotations

import os
import unittest

from flask import Flask, session

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)
os.environ.setdefault("ADMIN_PHONE", "+393331112233")
os.environ.setdefault("ADMIN_NAME", "Enrico Test")

from app.models import Utente, db
from app.routes.diario_ui import diario_ui_bp
from app.services.utente_service import ensure_admin_utente, ensure_session_utente_id


class EnsureAdminUtenteTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            WTF_CSRF_ENABLED=False,
        )
        db.init_app(self.app)
        self.app.register_blueprint(diario_ui_bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_ensure_creates_utente_when_missing(self):
        self.assertEqual(Utente.query.count(), 0)
        uid = ensure_admin_utente(telefono="+393331112233", admin_name="Enrico Test")
        self.assertIsInstance(uid, int)
        self.assertEqual(Utente.query.count(), 1)
        u = db.session.get(Utente, uid)
        self.assertEqual(u.nome, "Enrico")
        self.assertEqual(u.cognome, "Test")
        self.assertTrue(u.attivo)
        # idempotente
        uid2 = ensure_admin_utente(telefono="+393331112233", admin_name="Enrico Test")
        self.assertEqual(uid, uid2)
        self.assertEqual(Utente.query.count(), 1)

    def test_diary_ui_without_utente_id_does_not_bounce(self):
        from app.routes.diario_ui import _admin_required
        from flask import jsonify

        @self.app.route("/_diary_probe")
        @_admin_required
        def _probe():
            return jsonify({"utente_id": session.get("utente_id")}), 200

        with self.client.session_transaction() as sess:
            sess["role"] = "admin"
            # intenzionalmente senza utente_id

        res = self.client.get("/_diary_probe")
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertIsNotNone(res.get_json().get("utente_id"))
        self.assertEqual(Utente.query.count(), 1)

        # non redirect a login
        self.assertNotIn("/login", res.headers.get("Location", ""))

    def test_ensure_session_utente_id(self):
        with self.app.test_request_context():
            session["role"] = "admin"
            uid = ensure_session_utente_id()
            self.assertIsNotNone(uid)
            self.assertEqual(session.get("utente_id"), uid)


if __name__ == "__main__":
    unittest.main()
