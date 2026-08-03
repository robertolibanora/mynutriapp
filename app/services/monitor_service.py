"""Snapshot monitoraggio piattaforma per super_admin."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func

from app.config.config import Config
from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import Patient, db
from app.services.licensing_service import count_active_patients

logger = logging.getLogger(__name__)


def _cents_to_euro(amount: int | None, currency: str | None = "eur") -> str:
    if amount is None:
        return "—"
    cur = (currency or "eur").upper()
    value = amount / 100.0
    if cur == "EUR":
        return f"€ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{value:,.2f} {cur}"


def platform_kpis() -> dict[str, Any]:
    nutri_q = Utente.query.filter_by(ruolo=UtenteRuolo.NUTRIZIONISTA.value)
    total = nutri_q.count()
    attivi = nutri_q.filter_by(attivo=True).count()
    by_status = dict(
        db.session.query(Utente.subscription_status, func.count(Utente.id))
        .filter(Utente.ruolo == UtenteRuolo.NUTRIZIONISTA.value)
        .group_by(Utente.subscription_status)
        .all()
    )
    by_plan = dict(
        db.session.query(Utente.plan, func.count(Utente.id))
        .filter(Utente.ruolo == UtenteRuolo.NUTRIZIONISTA.value)
        .group_by(Utente.plan)
        .all()
    )
    subscribed = sum(
        n
        for status, n in by_status.items()
        if status in ("active", "trialing", "past_due")
    )
    patients_total = db.session.query(func.count(Patient.id)).scalar() or 0
    patients_attivi_stato = (
        db.session.query(func.count(Patient.id))
        .filter(Patient.stato_cliente == "attivo")
        .scalar()
        or 0
    )
    past_due = int(by_status.get("past_due", 0) or 0) + int(
        by_status.get("unpaid", 0) or 0
    )
    setup_pending = (
        Utente.query.filter_by(
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            needs_password_setup=True,
        ).count()
    )
    canceled = int(by_status.get("canceled", 0) or 0) + int(
        by_status.get("incomplete_expired", 0) or 0
    )
    return {
        "nutrizionisti_total": total,
        "nutrizionisti_attivi": attivi,
        "abbonati_attivi": subscribed,
        "past_due": past_due,
        "setup_pending": int(setup_pending),
        "canceled": canceled,
        "by_status": by_status,
        "by_plan": by_plan,
        "pazienti_total": int(patients_total),
        "pazienti_stato_attivo": int(patients_attivi_stato),
    }


def signup_series(weeks: int = 8) -> dict[str, Any]:
    """Iscrizioni nutrizionisti per settimana (ultime N)."""
    weeks = max(1, min(int(weeks), 26))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start = (now - timedelta(weeks=weeks - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # allinea a lunedì
    start = start - timedelta(days=start.weekday())

    rows = (
        Utente.query.filter(
            Utente.ruolo == UtenteRuolo.NUTRIZIONISTA.value,
            Utente.creato_il >= start,
        )
        .with_entities(Utente.creato_il)
        .all()
    )
    buckets: dict[str, int] = defaultdict(int)
    labels: list[str] = []
    for i in range(weeks):
        week_start = start + timedelta(weeks=i)
        key = week_start.strftime("%Y-%m-%d")
        labels.append(week_start.strftime("%d/%m"))
        buckets[key] = 0

    for (created,) in rows:
        if not created:
            continue
        week_start = created - timedelta(days=created.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        key = week_start.strftime("%Y-%m-%d")
        if key in buckets:
            buckets[key] += 1

    values = []
    for i in range(weeks):
        key = (start + timedelta(weeks=i)).strftime("%Y-%m-%d")
        values.append(buckets.get(key, 0))

    return {"labels": labels, "values": values}


def list_subscribers(*, limit: int = 100) -> list[dict[str, Any]]:
    rows = (
        Utente.query.filter_by(ruolo=UtenteRuolo.NUTRIZIONISTA.value)
        .order_by(Utente.creato_il.desc())
        .limit(limit)
        .all()
    )
    out: list[dict[str, Any]] = []
    for u in rows:
        try:
            active_patients = count_active_patients(u.id)
        except Exception:  # noqa: BLE001
            active_patients = 0
        out.append(
            {
                "id": u.id,
                "nome": f"{u.nome} {u.cognome}".strip(),
                "email": u.email,
                "telefono": u.telefono or "—",
                "plan": u.plan or "—",
                "subscription_status": u.subscription_status or "none",
                "attivo": bool(u.attivo),
                "needs_password_setup": bool(u.needs_password_setup),
                "stripe_customer_id": u.stripe_customer_id,
                "stripe_subscription_id": u.stripe_subscription_id,
                "pazienti_attivi": active_patients,
                "creato_il": u.creato_il,
            }
        )
    return out


def attention_subscribers(subscribers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Account che richiedono attenzione (pagamento / setup / disattivi)."""
    flagged: list[dict[str, Any]] = []
    for s in subscribers:
        reasons: list[str] = []
        st = s.get("subscription_status") or "none"
        if st in ("past_due", "unpaid"):
            reasons.append("pagamento in ritardo")
        if st in ("canceled", "incomplete_expired"):
            reasons.append("abbonamento cancellato")
        if s.get("needs_password_setup"):
            reasons.append("setup password incompleto")
        if not s.get("attivo"):
            reasons.append("account disattivo")
        if reasons:
            flagged.append({**s, "reasons": reasons})
    return flagged


def stripe_monitor_snapshot(*, payment_limit: int = 15) -> dict[str, Any]:
    """Balance + ultimi pagamenti Stripe. Fail-soft se Stripe non disponibile."""
    empty = {
        "ok": False,
        "error": None,
        "available": [],
        "pending": [],
        "available_total": "—",
        "pending_total": "—",
        "payments": [],
    }
    if not Config.STRIPE_SECRET_KEY:
        empty["error"] = "STRIPE_SECRET_KEY non configurata"
        return empty

    try:
        import stripe

        stripe.api_key = Config.STRIPE_SECRET_KEY
        bal = stripe.Balance.retrieve()
        available = [
            {
                "amount": _cents_to_euro(item.get("amount"), item.get("currency")),
                "currency": (item.get("currency") or "eur").upper(),
                "raw": item.get("amount") or 0,
            }
            for item in (bal.get("available") or [])
        ]
        pending = [
            {
                "amount": _cents_to_euro(item.get("amount"), item.get("currency")),
                "currency": (item.get("currency") or "eur").upper(),
                "raw": item.get("amount") or 0,
            }
            for item in (bal.get("pending") or [])
        ]

        # Preferisci PaymentIntent; fallback a Charge
        payments: list[dict[str, Any]] = []
        try:
            intents = stripe.PaymentIntent.list(limit=payment_limit)
            for pi in intents.data:
                payments.append(
                    {
                        "id": pi.id,
                        "amount": _cents_to_euro(pi.amount, pi.currency),
                        "status": pi.status,
                        "email": (pi.get("receipt_email") or "")
                        or ((pi.get("charges") or {}).get("data") or [{}])[0].get(
                            "billing_details", {}
                        ).get("email")
                        or "—",
                        "created": datetime.fromtimestamp(
                            pi.created, tz=timezone.utc
                        ).strftime("%d/%m/%Y %H:%M"),
                        "description": pi.description or "—",
                    }
                )
        except Exception:  # noqa: BLE001
            charges = stripe.Charge.list(limit=payment_limit)
            for ch in charges.data:
                payments.append(
                    {
                        "id": ch.id,
                        "amount": _cents_to_euro(ch.amount, ch.currency),
                        "status": ch.status,
                        "email": (ch.billing_details or {}).get("email")
                        or ch.receipt_email
                        or "—",
                        "created": datetime.fromtimestamp(
                            ch.created, tz=timezone.utc
                        ).strftime("%d/%m/%Y %H:%M"),
                        "description": ch.description or "—",
                    }
                )

        avail_sum = sum(x["raw"] for x in available)
        pend_sum = sum(x["raw"] for x in pending)
        cur = (available[0]["currency"] if available else "EUR").lower()

        return {
            "ok": True,
            "error": None,
            "available": available,
            "pending": pending,
            "available_total": _cents_to_euro(avail_sum, cur),
            "pending_total": _cents_to_euro(pend_sum, cur),
            "payments": payments,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stripe monitor snapshot fallito: %s", exc)
        msg = str(exc)
        if "claimable sandbox" in msg.lower() or "limited permissions" in msg.lower():
            msg = (
                "Chiave Stripe sandbox con permessi limitati: "
                "claima il sandbox o usa chiavi complete per vedere saldo e pagamenti."
            )
        empty["error"] = msg
        return empty


def chart_payloads(kpis: dict[str, Any], series: dict[str, Any]) -> dict[str, Any]:
    plan_counter = Counter(kpis.get("by_plan") or {})
    status_counter = Counter(kpis.get("by_status") or {})
    return {
        "signups": series,
        "plans": {
            "labels": list(plan_counter.keys()) or ["—"],
            "values": list(plan_counter.values()) or [0],
        },
        "status": {
            "labels": list(status_counter.keys()) or ["—"],
            "values": list(status_counter.values()) or [0],
        },
    }
