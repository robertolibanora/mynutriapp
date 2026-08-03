"""Unit test sync stato abbonamento da eventi invoice Stripe."""

from __future__ import annotations

import unittest

from flask import Flask
from werkzeug.security import generate_password_hash

from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import db
from app.services.stripe_billing_service import (
    handle_invoice_paid,
    handle_invoice_payment_failed,
)


class InvoiceWebhookHandlersTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        self.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        self.app.config["SECRET_KEY"] = "test-secret"
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.nutri = Utente(
            nome="Nutri",
            cognome="Invoice",
            email="invoice@test.local",
            telefono="3400000099",
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            password_hash=generate_password_hash("password123"),
            attivo=True,
            plan="starter",
            stripe_customer_id="cus_test_invoice",
            stripe_subscription_id="sub_test_invoice",
            subscription_status="active",
        )
        db.session.add(self.nutri)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_payment_failed_sets_past_due(self):
        handle_invoice_payment_failed(
            {
                "customer": "cus_test_invoice",
                "subscription": "sub_test_invoice",
            }
        )
        row = Utente.query.get(self.nutri.id)
        self.assertEqual(row.subscription_status, "past_due")

    def test_invoice_paid_sets_active(self):
        self.nutri.subscription_status = "past_due"
        db.session.commit()
        handle_invoice_paid(
            {
                "customer": "cus_test_invoice",
                "subscription": "sub_test_invoice",
            }
        )
        row = Utente.query.get(self.nutri.id)
        self.assertEqual(row.subscription_status, "active")


if __name__ == "__main__":
    unittest.main()
