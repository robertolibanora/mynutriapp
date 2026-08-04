"""Billing pubblico: Checkout Session + webhook Stripe + setup account."""

from __future__ import annotations

import logging

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.models.diario import Utente
from app.services.stripe_billing_service import (
    StaleStripeCustomerError,
    StripeBillingError,
    clear_stale_stripe_link,
    complete_account_setup,
    construct_webhook_event,
    create_billing_portal_session,
    create_checkout_session,
    finalize_checkout_session,
    handle_checkout_session_completed,
    handle_invoice_paid,
    handle_invoice_payment_failed,
    handle_subscription_updated,
)

logger = logging.getLogger(__name__)

billing_bp = Blueprint("billing", __name__, url_prefix="/billing")

_SETUP_UID_KEY = "setup_utente_id"
_SETUP_CS_KEY = "setup_checkout_session_id"


def _default_success_url() -> str:
    """URL post-pagamento con placeholder Stripe per session_id."""
    base = url_for("billing.checkout_success", _external=True)
    return f"{base}?session_id={{CHECKOUT_SESSION_ID}}"


def _default_cancel_url() -> str:
    return url_for("landing.landing", _external=True) + "?checkout=cancel"


def _begin_account_setup(utente: Utente, checkout_session_id: str) -> None:
    session.clear()
    session[_SETUP_UID_KEY] = int(utente.id)
    session[_SETUP_CS_KEY] = checkout_session_id
    session.permanent = True
    session.modified = True


def _setup_utente_from_session() -> Utente | None:
    uid = session.get(_SETUP_UID_KEY)
    if not uid:
        return None
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return None
    return Utente.query.get(uid)


@billing_bp.route("/create-checkout-session", methods=["POST"])
def create_checkout():
    """Body JSON: plan, email, nome, cognome, telefono (+ success/cancel opzionali)."""
    data = request.get_json(silent=True) or {}
    try:
        success = (data.get("success_url") or "").strip() or _default_success_url()
        if "{CHECKOUT_SESSION_ID}" not in success:
            sep = "&" if "?" in success else "?"
            success = f"{success}{sep}session_id={{CHECKOUT_SESSION_ID}}"

        checkout = create_checkout_session(
            plan=data.get("plan") or "",
            email=data.get("email") or "",
            nome=data.get("nome") or "",
            cognome=data.get("cognome") or "",
            telefono=data.get("telefono") or "",
            success_url=success,
            cancel_url=(data.get("cancel_url") or "").strip() or _default_cancel_url(),
        )
        return jsonify(checkout), 200
    except StripeBillingError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("create-checkout-session fallita")
        return jsonify({"error": f"Errore Stripe: {exc}"}), 500


@billing_bp.route("/success", methods=["GET"])
def checkout_success():
    """Dopo Stripe Checkout: crea/aggiorna utente → pagina creazione account o dashboard."""
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
            "Pagamento ricevuto, ma non è stato possibile aprire l'account. "
            "Riprova dal link di conferma Stripe o contatta il supporto.",
            "warning",
        )
        return redirect(url_for("auth.login"))

    if getattr(utente, "needs_password_setup", False):
        _begin_account_setup(utente, session_id)
        return redirect(url_for("billing.completa_account"))

    # Rinnovo / account già completo → login diretto
    from app.routes.auth import establish_utente_session

    establish_utente_session(utente, "nutrizionista", via="stripe_checkout")
    flash("Abbonamento aggiornato. Bentornato.", "success")
    return redirect(url_for("dashboard.admin_dashboard"))


@billing_bp.route("/portal", methods=["POST"])
def customer_portal():
    """Apre Stripe Customer Portal per l'utente nutrizionista loggato."""
    if session.get("role") not in ("nutrizionista", "admin"):
        flash("Accedi come nutrizionista per gestire l'abbonamento.", "warning")
        return redirect(url_for("auth.login"))

    from app.utils.tenant import current_utente_id

    uid = current_utente_id()
    if not uid:
        flash("Sessione non valida. Effettua di nuovo l'accesso.", "warning")
        return redirect(url_for("auth.login"))

    utente = Utente.query.get(int(uid))
    if utente is None or not getattr(utente, "stripe_customer_id", None):
        flash(
            "Nessun abbonamento Stripe collegato a questo account. "
            "Se hai appena pagato, attendi qualche minuto o contatta il supporto.",
            "warning",
        )
        return redirect(url_for("dashboard.admin_dashboard"))

    try:
        from app.config.config import Config

        portal = create_billing_portal_session(
            stripe_customer_id=utente.stripe_customer_id,
            return_url=(Config.STRIPE_PORTAL_RETURN_URL or "").strip()
            or url_for("dashboard.admin_dashboard", _external=True),
        )
        return redirect(portal["url"])
    except StaleStripeCustomerError as exc:
        clear_stale_stripe_link(utente)
        flash(str(exc), "warning")
        return redirect(url_for("landing.landing") + "#pricing")
    except StripeBillingError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("dashboard.admin_dashboard"))
    except Exception:  # noqa: BLE001
        logger.exception("customer portal fallito")
        flash("Impossibile aprire il portale abbonamento. Riprova più tardi.", "danger")
        return redirect(url_for("dashboard.admin_dashboard"))


@billing_bp.route("/completa-account", methods=["GET", "POST"])
def completa_account():
    """Pagina post-pagamento: conferma dati e imposta password, poi tutorial."""
    utente = _setup_utente_from_session()
    if utente is None:
        flash(
            "Sessione di registrazione scaduta. Se hai già pagato, usa di nuovo "
            "il link di conferma Stripe oppure contatta il supporto.",
            "warning",
        )
        return redirect(url_for("auth.login"))

    if not utente.needs_password_setup:
        from app.routes.auth import establish_utente_session

        session.pop(_SETUP_UID_KEY, None)
        session.pop(_SETUP_CS_KEY, None)
        establish_utente_session(utente, "nutrizionista", via="stripe_checkout")
        return redirect(url_for("dashboard.admin_dashboard"))

    if request.method == "POST":
        try:
            utente = complete_account_setup(
                int(utente.id),
                nome=request.form.get("nome") or "",
                cognome=request.form.get("cognome") or "",
                telefono=request.form.get("telefono") or "",
                password=request.form.get("password") or "",
                password_confirm=request.form.get("password_confirm") or "",
                nome_studio=request.form.get("nome_studio") or "",
            )
        except StripeBillingError as exc:
            flash(str(exc), "danger")
            return render_template(
                "billing/completa_account.html",
                utente=utente,
                nome_studio=request.form.get("nome_studio") or "",
            )

        from app.routes.auth import establish_utente_session

        establish_utente_session(utente, "nutrizionista", via="stripe_account_setup")
        session["show_onboarding"] = True
        session.modified = True
        return redirect(url_for("dashboard.admin_tutorial"))

    suggested = ""
    if utente.nome or utente.cognome:
        suggested = f"{utente.nome or ''} {utente.cognome or ''}".strip()
    return render_template(
        "billing/completa_account.html",
        utente=utente,
        nome_studio=suggested,
    )


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
        elif etype == "invoice.paid":
            handle_invoice_paid(data_obj)
        elif etype in ("invoice.payment_failed", "invoice.payment_action_required"):
            handle_invoice_payment_failed(data_obj)
    except Exception:  # noqa: BLE001
        logger.exception("Errore gestione evento Stripe %s", etype)
        return jsonify({"error": "handler_failed"}), 500

    return jsonify({"received": True}), 200
