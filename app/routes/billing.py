"""Billing pubblico: Checkout Session stub + webhook Stripe."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from app.services.stripe_billing_service import (
    StripeBillingError,
    construct_webhook_event,
    create_checkout_session,
    handle_checkout_session_completed,
    handle_subscription_updated,
)

logger = logging.getLogger(__name__)

billing_bp = Blueprint("billing", __name__, url_prefix="/billing")


@billing_bp.route("/create-checkout-session", methods=["POST"])
def create_checkout():
    """Stub pronto per la landing: body JSON con plan, email, nome, cognome, telefono."""
    data = request.get_json(silent=True) or {}
    try:
        session = create_checkout_session(
            plan=data.get("plan") or "",
            email=data.get("email") or "",
            nome=data.get("nome") or "",
            cognome=data.get("cognome") or "",
            telefono=data.get("telefono") or "",
            success_url=data.get("success_url"),
            cancel_url=data.get("cancel_url"),
        )
        return jsonify(session), 200
    except StripeBillingError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("create-checkout-session fallita")
        return jsonify({"error": f"Errore Stripe: {exc}"}), 500


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
