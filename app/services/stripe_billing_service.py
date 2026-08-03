"""Stripe Checkout + sync abbonamento → Utente nutrizionista."""

from __future__ import annotations

import logging
import secrets
from typing import Any, Optional

from werkzeug.security import generate_password_hash

from app.billing.plans import (
    PURCHASABLE_PLANS,
    normalize_plan,
    plan_from_stripe_price_id,
    stripe_price_id_for_plan,
)
from app.config.config import Config
from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import db
from app.services.utente_service import find_utente_by_phone
from app.utils.helpers import normalize_phone

logger = logging.getLogger(__name__)


class StripeBillingError(Exception):
    pass


def _stripe():
    if not Config.STRIPE_SECRET_KEY:
        raise StripeBillingError("STRIPE_SECRET_KEY non configurata")
    import stripe

    stripe.api_key = Config.STRIPE_SECRET_KEY
    return stripe


def create_checkout_session(
    *,
    plan: str,
    email: str,
    nome: str,
    cognome: str,
    telefono: str,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
) -> dict[str, Any]:
    """Crea Checkout Session in mode=subscription. Ritorna {id, url}."""
    plan_key = normalize_plan(plan)
    if plan_key not in PURCHASABLE_PLANS:
        raise StripeBillingError("Piano non acquistabile online")

    price_id = stripe_price_id_for_plan(plan_key)
    if not price_id:
        raise StripeBillingError(f"Price ID Stripe mancante per piano {plan_key}")

    email = (email or "").strip().lower()
    nome = (nome or "").strip()
    cognome = (cognome or "").strip()
    telefono = normalize_phone(telefono or "")
    if not email or "@" not in email:
        raise StripeBillingError("Email non valida")
    if not nome or not cognome:
        raise StripeBillingError("Nome e cognome obbligatori")
    if len(telefono) < 9:
        raise StripeBillingError("Telefono non valido")

    success = (success_url or Config.STRIPE_SUCCESS_URL or "").strip()
    cancel = (cancel_url or Config.STRIPE_CANCEL_URL or "").strip()
    if not success or not cancel:
        raise StripeBillingError("STRIPE_SUCCESS_URL / STRIPE_CANCEL_URL non configurati")

    stripe = _stripe()
    session_params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success,
        "cancel_url": cancel,
        "customer_email": email,
        "client_reference_id": telefono,
        "metadata": {
            "plan": plan_key,
            "nome": nome[:100],
            "cognome": cognome[:100],
            "telefono": telefono,
            "email": email,
        },
        "subscription_data": {
            "metadata": {"plan": plan_key},
        },
        # Stripe Tax: richiede registrazione attiva in Dashboard Tax, altrimenti IVA=0.
        "automatic_tax": {"enabled": True},
        "tax_id_collection": {"enabled": True},
        "billing_address_collection": "required",
    }
    session = stripe.checkout.Session.create(**session_params)
    return {"id": session.id, "url": session.url}


class StaleStripeCustomerError(StripeBillingError):
    """Customer ID presente in DB ma assente sull'account Stripe corrente."""


def clear_stale_stripe_link(utente: Utente) -> None:
    """Rimuove riferimenti Stripe non più validi (es. dopo cambio account)."""
    utente.stripe_customer_id = None
    utente.stripe_subscription_id = None
    if (utente.subscription_status or "") not in ("none", ""):
        utente.subscription_status = "none"
    db.session.commit()
    logger.warning("Cleared stale Stripe link for utente_id=%s", utente.id)


def create_billing_portal_session(
    *,
    stripe_customer_id: str,
    return_url: Optional[str] = None,
) -> dict[str, Any]:
    """Crea sessione Customer Portal. Ritorna {url}."""
    customer_id = (stripe_customer_id or "").strip()
    if not customer_id.startswith("cus_"):
        raise StripeBillingError("Customer Stripe non valido")

    ret = (return_url or Config.STRIPE_PORTAL_RETURN_URL or "").strip()
    if not ret:
        raise StripeBillingError("STRIPE_PORTAL_RETURN_URL non configurata")

    stripe = _stripe()
    try:
        stripe.Customer.retrieve(customer_id)
    except Exception as exc:  # noqa: BLE001
        err_code = getattr(exc, "code", None)
        if err_code == "resource_missing" or "No such customer" in str(exc):
            raise StaleStripeCustomerError(
                "Il collegamento Stripe di questo account non è più valido "
                "(probabile migrazione da sandbox/account precedente). "
                "Sottoscrivi di nuovo un piano dalla landing per riattivare "
                "la gestione abbonamento."
            ) from exc
        raise

    params: dict[str, Any] = {
        "customer": customer_id,
        "return_url": ret,
    }
    config_id = (Config.STRIPE_PORTAL_CONFIGURATION_ID or "").strip()
    if config_id:
        params["configuration"] = config_id

    try:
        portal = stripe.billing_portal.Session.create(**params)
    except Exception as exc:  # noqa: BLE001
        err_code = getattr(exc, "code", None)
        if err_code == "resource_missing" or "No such customer" in str(exc):
            raise StaleStripeCustomerError(
                "Il collegamento Stripe di questo account non è più valido. "
                "Sottoscrivi di nuovo un piano dalla landing."
            ) from exc
        raise
    return {"url": portal.url}


def _upsert_nutrizionista_from_checkout(
    *,
    email: str,
    nome: str,
    cognome: str,
    telefono: str,
    plan: str,
    stripe_customer_id: Optional[str],
    stripe_subscription_id: Optional[str],
    subscription_status: str,
) -> Utente:
    email = (email or "").strip().lower()
    telefono = normalize_phone(telefono or "")
    plan_key = normalize_plan(plan)

    row = None
    if stripe_customer_id:
        row = Utente.query.filter_by(stripe_customer_id=stripe_customer_id).first()
    if row is None and email:
        row = Utente.query.filter_by(email=email).first()
    if row is None and telefono:
        row = find_utente_by_phone(telefono)

    if row is None:
        # Password temporanea: verrà sostituita in /billing/completa-account
        temp_password = secrets.token_urlsafe(16)
        row = Utente(
            nome=(nome or "Nutrizionista")[:100],
            cognome=(cognome or "")[:100] or "Account",
            email=email[:255],
            telefono=telefono or None,
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            password_hash=generate_password_hash(temp_password),
            creato_da=None,
            attivo=True,
            plan=plan_key,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            subscription_status=subscription_status or "active",
            needs_password_setup=True,
        )
        db.session.add(row)
        logger.info("Creato nutrizionista da Stripe checkout: %s plan=%s", email, plan_key)
    else:
        row.plan = plan_key
        if stripe_customer_id:
            row.stripe_customer_id = stripe_customer_id
        if stripe_subscription_id:
            row.stripe_subscription_id = stripe_subscription_id
        row.subscription_status = subscription_status or row.subscription_status
        if row.ruolo != UtenteRuolo.NUTRIZIONISTA.value and not row.is_super_admin:
            row.ruolo = UtenteRuolo.NUTRIZIONISTA.value
        row.attivo = True
        # Non forzare setup se ha già completato la registrazione
        if row.password_hash is None:
            row.needs_password_setup = True
        logger.info("Aggiornato nutrizionista da Stripe: %s plan=%s", email, plan_key)

    db.session.commit()
    return row


def complete_account_setup(
    utente_id: int,
    *,
    nome: str,
    cognome: str,
    telefono: str,
    password: str,
    password_confirm: str,
) -> Utente:
    """Completa registrazione post-pagamento: dati + password definitiva."""
    row = Utente.query.get(utente_id)
    if row is None or not row.is_nutrizionista:
        raise StripeBillingError("Account non trovato")
    if not row.needs_password_setup:
        raise StripeBillingError("Account già configurato")

    nome = (nome or "").strip()
    cognome = (cognome or "").strip()
    telefono = normalize_phone(telefono or "")
    password = password or ""
    password_confirm = password_confirm or ""

    if not nome or not cognome:
        raise StripeBillingError("Nome e cognome obbligatori")
    if len(telefono) < 9:
        raise StripeBillingError("Telefono non valido")
    if len(password) < 8:
        raise StripeBillingError("Password minimo 8 caratteri")
    if password != password_confirm:
        raise StripeBillingError("Le password non coincidono")

    other = find_utente_by_phone(telefono)
    if other and other.id != row.id:
        raise StripeBillingError("Telefono già in uso")

    row.nome = nome[:100]
    row.cognome = cognome[:100]
    row.telefono = telefono
    row.password_hash = generate_password_hash(password)
    row.needs_password_setup = False
    row.attivo = True
    db.session.commit()
    logger.info("Account nutrizionista completato id=%s", row.id)
    return row


def finalize_checkout_session(session_id: str) -> Utente:
    """Recupera la Checkout Session da Stripe, crea/aggiorna l'utente e lo restituisce.

    Usato dalla success URL: non dipende dal webhook (che resta idempotente).
    """
    session_id = (session_id or "").strip()
    if not session_id.startswith("cs_"):
        raise StripeBillingError("Session ID non valido")

    stripe = _stripe()
    session = stripe.checkout.Session.retrieve(
        session_id,
        expand=["line_items.data.price"],
    )
    status = getattr(session, "status", None)
    payment_status = getattr(session, "payment_status", None)
    if status != "complete" and payment_status not in ("paid", "no_payment_required"):
        raise StripeBillingError("Pagamento non completato")

    if hasattr(session, "to_dict"):
        session_obj = session.to_dict()
    else:
        session_obj = dict(session)

    utente = handle_checkout_session_completed(session_obj)
    if utente is None:
        raise StripeBillingError("Impossibile attivare l'account dopo il pagamento")
    return utente


def handle_checkout_session_completed(session_obj: dict[str, Any]) -> Optional[Utente]:
    metadata = session_obj.get("metadata") or {}
    plan = metadata.get("plan") or "starter"
    email = metadata.get("email") or session_obj.get("customer_details", {}).get("email")
    if not email and session_obj.get("customer_email"):
        email = session_obj["customer_email"]
    nome = metadata.get("nome") or ""
    cognome = metadata.get("cognome") or ""
    telefono = metadata.get("telefono") or session_obj.get("client_reference_id") or ""

    price_id = None
    try:
        items = (session_obj.get("line_items") or {}).get("data") or []
        if items:
            price_id = (items[0].get("price") or {}).get("id")
    except Exception:  # noqa: BLE001
        price_id = None
    if price_id:
        resolved = plan_from_stripe_price_id(price_id)
        if resolved:
            plan = resolved

    if not email:
        logger.warning("checkout.session.completed senza email")
        return None

    return _upsert_nutrizionista_from_checkout(
        email=email,
        nome=nome,
        cognome=cognome,
        telefono=telefono,
        plan=plan,
        stripe_customer_id=session_obj.get("customer"),
        stripe_subscription_id=session_obj.get("subscription"),
        subscription_status="active",
    )


def handle_subscription_updated(subscription_obj: dict[str, Any]) -> Optional[Utente]:
    customer_id = subscription_obj.get("customer")
    sub_id = subscription_obj.get("id")
    status = subscription_obj.get("status") or "none"

    plan = None
    meta = subscription_obj.get("metadata") or {}
    if meta.get("plan"):
        plan = normalize_plan(meta["plan"])
    items = (subscription_obj.get("items") or {}).get("data") or []
    if items:
        price_id = (items[0].get("price") or {}).get("id")
        resolved = plan_from_stripe_price_id(price_id)
        if resolved:
            plan = resolved

    row = None
    if customer_id:
        row = Utente.query.filter_by(stripe_customer_id=customer_id).first()
    if row is None and sub_id:
        row = Utente.query.filter_by(stripe_subscription_id=sub_id).first()
    if row is None:
        logger.warning("subscription update: utente non trovato customer=%s", customer_id)
        return None

    if plan:
        row.plan = plan
    if sub_id:
        row.stripe_subscription_id = sub_id
    row.subscription_status = status
    if status in ("canceled", "unpaid", "incomplete_expired"):
        # Non disattiviamo l'account automaticamente: solo sync status.
        pass
    db.session.commit()
    return row


def _utente_from_invoice(invoice_obj: dict[str, Any]) -> Optional[Utente]:
    customer_id = invoice_obj.get("customer")
    sub_id = invoice_obj.get("subscription")
    row = None
    if customer_id:
        row = Utente.query.filter_by(stripe_customer_id=customer_id).first()
    if row is None and sub_id:
        row = Utente.query.filter_by(stripe_subscription_id=sub_id).first()
    return row


def handle_invoice_paid(invoice_obj: dict[str, Any]) -> Optional[Utente]:
    """Rinnovo ok / recupero pagamento → status active."""
    row = _utente_from_invoice(invoice_obj)
    if row is None:
        logger.warning(
            "invoice.paid: utente non trovato customer=%s",
            invoice_obj.get("customer"),
        )
        return None

    sub_id = invoice_obj.get("subscription")
    if sub_id:
        row.stripe_subscription_id = sub_id
    # Solo se non è in cancellazione programmata lasciamo active.
    if row.subscription_status not in ("canceled", "incomplete_expired"):
        row.subscription_status = "active"
    db.session.commit()
    logger.info("invoice.paid sync utente_id=%s", row.id)
    return row


def handle_invoice_payment_failed(invoice_obj: dict[str, Any]) -> Optional[Utente]:
    """Pagamento fallito → past_due (dunning Stripe gestisce i retry)."""
    row = _utente_from_invoice(invoice_obj)
    if row is None:
        logger.warning(
            "invoice.payment_failed: utente non trovato customer=%s",
            invoice_obj.get("customer"),
        )
        return None

    sub_id = invoice_obj.get("subscription")
    if sub_id:
        row.stripe_subscription_id = sub_id
    row.subscription_status = "past_due"
    db.session.commit()
    logger.warning("invoice.payment_failed sync utente_id=%s → past_due", row.id)
    return row


def construct_webhook_event(payload: bytes, sig_header: str):
    stripe = _stripe()
    secret = Config.STRIPE_WEBHOOK_SECRET
    if not secret:
        raise StripeBillingError("STRIPE_WEBHOOK_SECRET non configurata")
    return stripe.Webhook.construct_event(payload, sig_header, secret)
