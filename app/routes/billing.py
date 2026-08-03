"""Billing pubblico: Checkout Session + webhook Stripe + success → dashboard."""

from __future__ import annotations

import logging

from flask import Blueprint, flash, jsonify, redirect, request, session, url_for

from app.services.stripe_billing_service import (
    StripeBillingError,
    construct_webhook_event,
    create_checkout_session,
    finalize_checkout_session,
    handle_checkout_session_completed,
    handle_subscription_updated,
)

logger = logging.getLogger(__name__)

billing_bp = Blueprint("billing", __name__, url_prefix="/billing")


def _default_success_url() -> str:
    """URL post-pagamento con placeholder Stripe per session_id."""
    base = url_for("billing.checkout_success", _external=True)
    return f"{base}?session_id={{CHECKOUT_SESSION_ID}}"


def _default_cancel_url() -> str:
    return url_for("landing.landing", _external=True) + "?checkout=cancel"


@billing_bp.route("/create-checkout-session", methods=["POST"])
def create_checkout():
    """Body JSON: plan, email, nome, cognome, telefono (+ success/cancel opzionali)."""
    data = request.get_json(silent=True) or {}
    try:
        success = (data.get("success_url") or "").strip() or _default_success_url()
        if "{CHECKOUT_SESSION_ID}" not in success:
            sep = "&" if "?" in success else "?"
            success = f"{success}{sep}session_id={{CHECKOUT_SESSION_ID}}"

        session = create_checkout_session(
            plan=data.get("plan") or "",
            email=data.get("email") or "",
            nome=data.get("nome") or "",
            cognome=data.get("cognome") or "",
            telefono=data.get("telefono") or "",
            success_url=success,
            cancel_url=(data.get("cancel_url") or "").strip() or _default_cancel_url(),
        )
        return jsonify(session), 200
    except StripeBillingError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("create-checkout-session fallita")
        return jsonify({"error": f"Errore Stripe: {exc}"}), 500


@billing_bp.route("/success", methods=["GET"])
def checkout_success():
    """Dopo Stripe Checkout: attiva account, login automatico → dashboard admin."""
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id:
        flash("Sessione di pagamento mancante. Accedi con le tue credenziali.", "warning")
        return redirect(url_for("auth.login"))

    try:
        utente = finalize_checkout_session(session_id)
    except StripeBillingError as exc:
        logger.warning("checkout success fallito: %s", exc)
        flash(str(exc), "danger")
        return redirect(url_for("auth.login"))
    except Exception:  # noqa: BLE001
        logger.exception("checkout success errore inatteso")
        flash(
            "Pagamento ricevuto, ma non è stato possibile aprire la dashboard. "
            "Accedi con email/telefono usati in fase di acquisto.",
            "warning",
        )
        return redirect(url_for("auth.login"))

    from app.routes.auth import establish_utente_session

    establish_utente_session(utente, "nutrizionista", via="stripe_checkout")
    # Mini tutorial one-shot sulla dashboard (dopo session.clear in establish)
    session["show_onboarding"] = True
    session.modified = True
    return redirect(url_for("dashboard.admin_dashboard"))


@billing_bp.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = construct_webhook_event(payload, sig)
    except StripeBillingError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook Stripe non valido: %s", exc)
        return jsonify({"error": "invalid_payload"}), 400

    etype = event.get("type") if isinstance(event, dict) else getattr(event, "type", None)
    data_obj = (
        event["data"]["object"]
        if isinstance(event, dict)
        else event.data.object
    )
    if hasattr(data_obj, "to_dict"):
        data_obj = data_obj.to_dict()
    elif not isinstance(data_obj, dict):
        try:
            data_obj = dict(data_obj)
        except Exception:  # noqa: BLE001
            data_obj = data_obj

    try:
        if etype == "checkout.session.completed":
            handle_checkout_session_completed(data_obj)
        elif etype in (
            "customer.subscription.updated",
            "customer.subscription.deleted",
            "customer.subscription.created",
        ):
            handle_subscription_updated(data_obj)
    except Exception:  # noqa: BLE001
        logger.exception("Errore gestione evento Stripe %s", etype)
        return jsonify({"error": "handler_failed"}), 500

    return jsonify({"received": True}), 200
