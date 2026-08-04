"""Test studio_slug, isolamento tenant prenota, invito e reset password.

    venv/bin/python -m unittest tests.test_studio_slug_invite_password -v
"""

from __future__ import annotations

import os
import unittest
from datetime import date
from pathlib import Path

from flask import Flask
from werkzeug.security import check_password_hash, generate_password_hash

os.environ.setdefault("AUDIO_ENCRYPTION_KEY", "ab" * 32)
os.environ.setdefault("ENCRYPTION_KEY", "x" * 44)

ROOT = Path(__file__).resolve().parents[1]

from app.api.v1 import api_v1_bp
from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import Appuntamento, AuthSecureToken, Patient, db
from app.routes.prenota_public import prenota_public_bp
from app.services.jwt_service import decode_token, issue_token_pair
from app.services.password_reset_service import (
    GENERIC_OK_MESSAGE,
    request_patient_reset,
    reset_patient_password,
)
from app.services.patient_invite_service import (
    activate_account,
    create_patient_with_invite,
    send_invite_email,
)
from app.services.stripe_billing_service import StripeBillingError, complete_account_setup
from app.utils.helpers import (
    allocate_unique_studio_slug,
    slugify_studio_name,
    validate_studio_slug_base,
)


class StudioSlugHelpersTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            WTF_CSRF_ENABLED=False,
            APP_PUBLIC_URL="https://example.test",
        )
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_slugify_and_reserved(self):
        self.assertEqual(slugify_studio_name("Studio Rossi!"), "studio-rossi")
        self.assertIsNotNone(validate_studio_slug_base("admin"))
        self.assertIsNone(validate_studio_slug_base("studio-rossi"))

    def test_allocate_unique_suffix(self):
        a = Utente(
            nome="A",
            cognome="A",
            email="a@ex.com",
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            public_slug="studio-rossi",
            attivo=True,
        )
        db.session.add(a)
        db.session.commit()
        slug = allocate_unique_studio_slug("Studio Rossi")
        self.assertEqual(slug, "studio-rossi-2")


class CompleteAccountStudioSlugTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.u = Utente(
            nome="Tmp",
            cognome="User",
            email="setup@ex.com",
            telefono="3331112233",
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            password_hash=generate_password_hash("tmp"),
            needs_password_setup=True,
            attivo=True,
        )
        db.session.add(self.u)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_complete_sets_studio_nome_and_slug(self):
        other = Utente(
            nome="O",
            cognome="O",
            email="o@ex.com",
            telefono="3330000001",
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            public_slug="studio-verde",
            attivo=True,
        )
        db.session.add(other)
        db.session.commit()

        row = complete_account_setup(
            self.u.id,
            nome="Mario",
            cognome="Rossi",
            telefono="3331112233",
            password="password1",
            password_confirm="password1",
            nome_studio="Studio Verde",
        )
        self.assertEqual(row.studio_nome, "Studio Verde")
        self.assertEqual(row.studio_slug, "studio-verde-2")
        self.assertEqual(row.public_slug, "studio-verde-2")
        self.assertFalse(row.needs_password_setup)

    def test_reserved_slug_rejected(self):
        with self.assertRaises(StripeBillingError):
            complete_account_setup(
                self.u.id,
                nome="Mario",
                cognome="Rossi",
                telefono="3331112233",
                password="password1",
                password_confirm="password1",
                nome_studio="admin",
            )


class PrenotaTenantIsolationTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(
            __name__,
            template_folder=str(ROOT / "templates"),
            static_folder=str(ROOT / "static"),
        )
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            WTF_CSRF_ENABLED=False,
            SINGLE_TENANT=False,
        )
        db.init_app(self.app)
        self.app.register_blueprint(prenota_public_bp)

        # Evita ensure_* MySQL-specific nel before_request
        prenota_public_bp.before_request_funcs[None] = []

        def _stub():
            return "ok"

        # Endpoint referenziati dai template pubblici
        self.app.add_url_rule("/login", endpoint="auth.login", view_func=_stub)
        self.app.add_url_rule(
            "/chi-sono", endpoint="presentazione_roberto", view_func=_stub
        )
        self.app.jinja_env.globals["csrf_token"] = lambda: "test-csrf"

        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.n1 = Utente(
            nome="Uno",
            cognome="Studio",
            email="n1@ex.com",
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            public_slug="studio-uno",
            studio_nome="Studio Uno",
            attivo=True,
        )
        self.n2 = Utente(
            nome="Due",
            cognome="Studio",
            email="n2@ex.com",
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            public_slug="studio-due",
            studio_nome="Studio Due",
            attivo=True,
        )
        db.session.add_all([self.n1, self.n2])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_prenota_without_slug_is_neutral_404(self):
        res = self.client.get("/prenota")
        self.assertEqual(res.status_code, 404)
        self.assertIn(b"MyNutriApp", res.data)

    def test_prenota_post_without_slug_does_not_create(self):
        before = Appuntamento.query.count()
        res = self.client.post(
            "/prenota",
            data={
                "nome": "A",
                "cognome": "B",
                "telefono": "3331234567",
                "altezza_cm": "170",
                "peso_iniziale": "70",
                "data_appuntamento": "2099-01-01 10:00:00",
                "tipo": "altro",
                "consenso_privacy": "1",
            },
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(Appuntamento.query.count(), before)

    def test_prenota_by_slug_resolves_tenant(self):
        res = self.client.get("/prenota/studio-uno")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Studio Uno", res.data)

    def test_unknown_slug_404(self):
        res = self.client.get("/prenota/inesistente")
        self.assertEqual(res.status_code, 404)


class InviteAndResetTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            JWT_SECRET="jwt-secret",
            JWT_ACCESS_EXPIRES=900,
            JWT_REFRESH_EXPIRES=2592000,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            WTF_CSRF_ENABLED=False,
            APP_PUBLIC_URL="https://example.test",
            INVITE_TOKEN_EXPIRES_MINUTES=60,
            PASSWORD_RESET_TOKEN_EXPIRES_MINUTES=45,
            SINGLE_TENANT=False,
        )
        db.init_app(self.app)
        self.app.register_blueprint(api_v1_bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.nutri = Utente(
            nome="Nutri",
            cognome="Test",
            email="nutri-inv@ex.com",
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            public_slug="studio-inv",
            studio_nome="Studio Inv",
            attivo=True,
            plan="enterprise",
        )
        db.session.add(self.nutri)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_invite_activate_login(self):
        patient = create_patient_with_invite(
            nome="Giulia",
            cognome="Rossi",
            telefono="3335556677",
            email="giulia@ex.com",
            sesso="F",
            data_nascita=date(1990, 1, 1),
            altezza_cm=165,
            peso_iniziale=60,
            nutrizionista_id=self.nutri.id,
        )
        db.session.commit()
        self.assertEqual(patient.account_status, "invited")

        # Login bloccato finché invited
        res = self.client.post(
            "/api/v1/auth/login",
            json={"telefono": "3335556677", "password": "anything1"},
        )
        self.assertEqual(res.status_code, 401)

        tok_row = AuthSecureToken.query.filter_by(
            purpose=AuthSecureToken.PURPOSE_PATIENT_INVITE,
            subject_id=patient.id,
        ).first()
        self.assertIsNotNone(tok_row)

        # Recupera raw token dal flusso di test
        raw = send_invite_email(patient)
        db.session.commit()

        activate_account(raw, "nuovaPass1", "nuovaPass1")
        db.session.commit()
        patient = db.session.get(Patient, patient.id)
        self.assertEqual(patient.account_status, "active")
        self.assertTrue(check_password_hash(patient.password_hash, "nuovaPass1"))

        res = self.client.post(
            "/api/v1/auth/login",
            json={"telefono": "3335556677", "password": "nuovaPass1"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("access_token", res.get_json())

    def test_forgot_password_generic_and_reset_invalidates_refresh(self):
        patient = Patient(
            nome="Luca",
            cognome="Verdi",
            telefono="3338887766",
            email="luca@ex.com",
            password_hash=generate_password_hash("oldpass12"),
            stato_cliente="attivo",
            account_status="active",
            token_version=0,
            nutrizionista_id=self.nutri.id,
        )
        db.session.add(patient)
        db.session.commit()

        pair = issue_token_pair(
            patient_id=patient.id, name="Luca Verdi", token_version=0
        )
        old_refresh = pair["refresh_token"]

        msg = request_patient_reset("unknown@ex.com")
        self.assertEqual(msg, GENERIC_OK_MESSAGE)

        msg2 = request_patient_reset("luca@ex.com")
        self.assertEqual(msg2, GENERIC_OK_MESSAGE)

        emails = self.app.config.get("_TEST_EMAILS") or []
        self.assertTrue(any("luca@ex.com" in e["to"] for e in emails))
        # Estrai token dal body email
        body = next(e["body"] for e in emails if e["to"] == "luca@ex.com")
        # Link: /reset-password?token=...
        if "token=" in body:
            token = body.split("token=")[1].split()[0].strip()
        else:
            token = body.split("/reset-password/")[1].split()[0].strip()

        res_api = self.client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nessuno@ex.com"},
        )
        self.assertEqual(res_api.status_code, 200)
        self.assertTrue(res_api.get_json()["ok"])

        reset_patient_password(token, "newpass99", "newpass99")
        patient = db.session.get(Patient, patient.id)
        self.assertEqual(patient.token_version, 1)
        self.assertTrue(check_password_hash(patient.password_hash, "newpass99"))

        # Refresh vecchio non più valido
        res = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        self.assertEqual(res.status_code, 401)

        # Nuovo login ok
        res = self.client.post(
            "/api/v1/auth/login",
            json={"telefono": "3338887766", "password": "newpass99"},
        )
        self.assertEqual(res.status_code, 200)
        payload = decode_token(res.get_json()["access_token"], expected_typ="access")
        self.assertEqual(int(payload.get("ver") or 0), 1)

    def test_activate_api(self):
        patient = create_patient_with_invite(
            nome="Sara",
            cognome="Neri",
            telefono="3334445566",
            email="sara@ex.com",
            sesso="F",
            data_nascita=date(1992, 2, 2),
            altezza_cm=160,
            peso_iniziale=55,
            nutrizionista_id=self.nutri.id,
        )
        raw = send_invite_email(patient)
        db.session.commit()

        res = self.client.post(
            "/api/v1/auth/activate-account",
            json={
                "token": raw,
                "password": "attivata1",
                "password_confirm": "attivata1",
            },
        )
        self.assertEqual(res.status_code, 200)
        patient = db.session.get(Patient, patient.id)
        self.assertEqual(patient.account_status, "active")

        # Alias legacy ancora disponibile
        raw2 = send_invite_email(patient)
        db.session.commit()
        # già active → activate con nuovo token dopo re-invite
        patient.account_status = "invited"
        db.session.commit()
        res_legacy = self.client.post(
            "/api/v1/auth/activate",
            json={
                "token": raw2,
                "password": "attivata2",
                "password_confirm": "attivata2",
            },
        )
        self.assertEqual(res_legacy.status_code, 200)


if __name__ == "__main__":
    unittest.main()
