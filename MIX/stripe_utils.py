"""
stripe_utils.py — Stripe Checkout + verifica webhook
"""
import os
import stripe

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8100").rstrip("/")


def create_checkout_session(
    order_id: int,
    items: list[dict],
    *,
    invite_code_id: int | None = None,
) -> stripe.checkout.Session:
    """
    items: [{"event_nome": str, "importo_cents": int, "quantity": int}]
    """
    line_items = [
        {
            "price_data": {
                "currency": "eur",
                "product_data": {"name": it["event_nome"]},
                "unit_amount": it["importo_cents"],
            },
            "quantity": it["quantity"],
        }
        for it in items
    ]
    metadata = {"order_id": str(order_id)}
    if invite_code_id is not None:
        metadata["invite_code_id"] = str(invite_code_id)
    return stripe.checkout.Session.create(
        mode="payment",
        line_items=line_items,
        metadata=metadata,
        success_url=f"{BASE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{BASE_URL}/",
        expires_at=None,
    )


def verify_webhook(payload: bytes, sig_header: str) -> stripe.Event:
    """Solleva ValueError / stripe.error.SignatureVerificationError se non valido."""
    return stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)


def retrieve_checkout_session(session_id: str) -> stripe.checkout.Session:
    return stripe.checkout.Session.retrieve(session_id)
