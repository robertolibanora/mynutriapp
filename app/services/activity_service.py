"""Inbox attività: manuali persistite + regole automatiche (non persistite)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, exists, func, not_
from sqlalchemy.orm import joinedload

from app.models.models import (
    Activity,
    Allenamento,
    Appuntamento,
    Dieta,
    DietPlan,
    Patient,
    Progresso,
    RichiestaAppuntamento,
    db,
)
from app.utils.tenant import patients_query_for_tenant, require_tenant, tenant_filter_enabled

# Soglie configurabili (giorni)
CHECK_MISSING_DAYS = 30
EXPIRY_WARNING_DAYS = 14


def _uid() -> int:
    return require_tenant()


def list_manual_activities(*, status: Optional[str] = None) -> list[Activity]:
    q = Activity.query.filter_by(utente_id=_uid())
    if status:
        q = q.filter(Activity.status == status)
    return (
        q.options(joinedload(Activity.patient))
        .order_by(
            Activity.due_at.is_(None).asc(),
            Activity.due_at.asc(),
            Activity.created_at.desc(),
        )
        .all()
    )


def create_manual_activity(
    *,
    title: str,
    patient_id: Optional[int] = None,
    due_at: Optional[datetime] = None,
    priority: str = "medium",
    notes: Optional[str] = None,
) -> Activity:
    act = Activity(
        utente_id=_uid(),
        patient_id=patient_id,
        title=title.strip(),
        tipo="manuale",
        priority=priority if priority in ("high", "medium", "low") else "medium",
        due_at=due_at,
        status="open",
        source="manual",
        notes=notes,
    )
    db.session.add(act)
    return act


def complete_activity(activity_id: int) -> Activity:
    act = Activity.query.get_or_404(activity_id)
    if act.utente_id != _uid():
        from werkzeug.exceptions import Forbidden

        raise Forbidden()
    act.status = "done"
    act.completed_at = datetime.now()
    return act


def reopen_activity(activity_id: int) -> Activity:
    act = Activity.query.get_or_404(activity_id)
    if act.utente_id != _uid():
        from werkzeug.exceptions import Forbidden

        raise Forbidden()
    act.status = "open"
    act.completed_at = None
    return act


def delete_activity(activity_id: int) -> None:
    act = Activity.query.get_or_404(activity_id)
    if act.utente_id != _uid():
        from werkzeug.exceptions import Forbidden

        raise Forbidden()
    db.session.delete(act)


def _auto_item(
    *,
    key: str,
    title: str,
    patient: Optional[Patient],
    due_at: Optional[datetime],
    priority: str,
    tipo: str,
    action_label: str,
    action_url: str,
) -> dict[str, Any]:
    return {
        "id": f"auto:{key}",
        "source": "auto",
        "title": title,
        "patient": patient,
        "patient_id": patient.id if patient else None,
        "patient_name": f"{patient.nome} {patient.cognome}" if patient else None,
        "due_at": due_at,
        "priority": priority,
        "tipo": tipo,
        "status": "open",
        "action_label": action_label,
        "action_url": action_url,
        "is_manual": False,
    }


def generate_automatic_activities() -> list[dict[str, Any]]:
    """Regole centralizzate — nessuna persistenza."""
    uid = _uid()
    oggi = date.today()
    now = datetime.now()
    items: list[dict[str, Any]] = []

    patients_q = patients_query_for_tenant() if tenant_filter_enabled() else Patient.query
    patient_map = {p.id: p for p in patients_q.all()}

    # Diete in bozza
    draft_q = DietPlan.query.filter(DietPlan.status == "draft")
    if tenant_filter_enabled():
        draft_q = draft_q.filter(
            DietPlan.patient_id.in_(list(patient_map.keys()) or [-1])
        )
    for plan in draft_q.order_by(DietPlan.updated_at.desc()).limit(50).all():
        p = patient_map.get(plan.patient_id)
        if not p:
            continue
        items.append(
            _auto_item(
                key=f"diet_draft:{plan.id}",
                title=f"Dieta in bozza: {plan.title}",
                patient=p,
                due_at=_dt(plan.updated_at) or now,
                priority="medium",
                tipo="dieta_bozza",
                action_label="Apri dieta",
                action_url=f"/admin/diet-plans/{plan.id}",
            )
        )

    # Appuntamenti da confermare
    app_q = Appuntamento.query.filter(
        Appuntamento.stato == "in_attesa",
        Appuntamento.data_appuntamento >= now,
    )
    if tenant_filter_enabled():
        app_q = app_q.filter(Appuntamento.utente_id == uid)
    for a in app_q.options(joinedload(Appuntamento.patient)).order_by(
        Appuntamento.data_appuntamento.asc()
    ).limit(50).all():
        p = a.patient or patient_map.get(a.patient_id)
        items.append(
            _auto_item(
                key=f"appt_pending:{a.id}",
                title="Appuntamento da confermare",
                patient=p,
                due_at=a.data_appuntamento,
                priority="high",
                tipo="appuntamento_confermare",
                action_label="Apri agenda",
                action_url="/agenda/admin?tab=appuntamenti&filtro=da_confermare",
            )
        )

    # Richieste online
    req_q = RichiestaAppuntamento.query.filter_by(stato="in_attesa")
    if tenant_filter_enabled():
        req_q = req_q.filter(RichiestaAppuntamento.utente_id == uid)
    for r in req_q.order_by(RichiestaAppuntamento.data_richiesta.asc()).limit(30).all():
        items.append(
            _auto_item(
                key=f"req:{r.id}",
                title=f"Richiesta online: {r.nome} {r.cognome}",
                patient=None,
                due_at=_dt(r.data_richiesta) or now,
                priority="high",
                tipo="richiesta_online",
                action_label="Gestisci",
                action_url="/appuntamenti/admin/richieste",
            )
        )

    # Pazienti attivi senza appuntamento futuro
    future_exists = (
        exists()
        .where(
            and_(
                Appuntamento.patient_id == Patient.id,
                Appuntamento.data_appuntamento >= now,
                Appuntamento.stato.in_(("in_attesa", "confermato")),
            )
        )
        .correlate(Patient)
    )
    no_future_q = patients_q.filter(
        Patient.stato_cliente == "attivo",
        not_(future_exists),
    ).limit(40)
    for p in no_future_q.all():
        items.append(
            _auto_item(
                key=f"no_future:{p.id}",
                title="Senza appuntamento futuro",
                patient=p,
                due_at=None,
                priority="low",
                tipo="senza_appuntamento",
                action_label="Apri paziente",
                action_url=f"/admin/pazienti/{p.id}?tab=appuntamenti",
            )
        )

    # Scadenze diete PDF
    limite = oggi + timedelta(days=EXPIRY_WARNING_DAYS)
    diet_exp = Dieta.query.filter(
        Dieta.data_fine >= oggi,
        Dieta.data_fine <= limite,
        Dieta.patient_id.in_(list(patient_map.keys()) or [-1]),
    ).limit(40)
    for d in diet_exp.all():
        p = patient_map.get(d.patient_id)
        if not p:
            continue
        days = (d.data_fine - oggi).days
        items.append(
            _auto_item(
                key=f"diet_exp:{d.id}",
                title=f"Dieta in scadenza tra {days} giorni",
                patient=p,
                due_at=datetime.combine(d.data_fine, datetime.min.time()),
                priority="high" if days <= 7 else "medium",
                tipo="scadenza_dieta",
                action_label="Apri paziente",
                action_url=f"/admin/pazienti/{p.id}?tab=diete",
            )
        )

    # Scadenze allenamenti
    w_exp = Allenamento.query.filter(
        Allenamento.data_fine >= oggi,
        Allenamento.data_fine <= limite,
        Allenamento.patient_id.in_(list(patient_map.keys()) or [-1]),
    ).limit(40)
    for w in w_exp.all():
        p = patient_map.get(w.patient_id)
        if not p:
            continue
        days = (w.data_fine - oggi).days
        items.append(
            _auto_item(
                key=f"work_exp:{w.id}",
                title=f"Allenamento in scadenza tra {days} giorni",
                patient=p,
                due_at=datetime.combine(w.data_fine, datetime.min.time()),
                priority="high" if days <= 7 else "medium",
                tipo="scadenza_allenamento",
                action_label="Apri paziente",
                action_url=f"/admin/pazienti/{p.id}?tab=allenamenti",
            )
        )

    # Check mancante
    cutoff = oggi - timedelta(days=CHECK_MISSING_DAYS)
    for p in patients_q.filter(Patient.stato_cliente == "attivo").limit(80).all():
        last = (
            Progresso.query.filter_by(patient_id=p.id)
            .order_by(Progresso.data_check.desc())
            .first()
        )
        if last is None:
            items.append(
                _auto_item(
                    key=f"check_never:{p.id}",
                    title="Nessun progresso registrato",
                    patient=p,
                    due_at=None,
                    priority="medium",
                    tipo="progresso_mancante",
                    action_label="Registra progresso",
                    action_url=f"/admin/pazienti/{p.id}?tab=progressi",
                )
            )
            continue
        last_d = last.data_check.date() if hasattr(last.data_check, "date") else last.data_check
        if last_d and last_d < cutoff:
            days = (oggi - last_d).days
            items.append(
                _auto_item(
                    key=f"check_old:{p.id}",
                    title=f"Nessun progresso da {days} giorni",
                    patient=p,
                    due_at=datetime.combine(last_d, datetime.min.time()),
                    priority="high" if days > 60 else "medium",
                    tipo="progresso_mancante",
                    action_label="Registra progresso",
                    action_url=f"/admin/pazienti/{p.id}?tab=progressi",
                )
            )

    return items


def _dt(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.combine(value, datetime.min.time())
    except Exception:  # noqa: BLE001
        return None


def build_inbox(*, bucket: str = "oggi") -> dict[str, Any]:
    """Unisce manuali + automatiche e filtra per bucket."""
    now = datetime.now()
    today_end = datetime.combine(date.today(), datetime.max.time())

    auto = generate_automatic_activities()
    manuals_open = list_manual_activities(status="open")
    manuals_done = list_manual_activities(status="done")

    open_items: list[dict[str, Any]] = list(auto)
    for m in manuals_open:
        open_items.append(
            {
                "id": f"manual:{m.id}",
                "manual_id": m.id,
                "source": "manual",
                "title": m.title,
                "patient": m.patient,
                "patient_id": m.patient_id,
                "patient_name": (
                    f"{m.patient.nome} {m.patient.cognome}" if m.patient else None
                ),
                "due_at": m.due_at,
                "priority": m.priority,
                "tipo": m.tipo,
                "status": m.status,
                "action_label": "Completa",
                "action_url": f"/admin/attivita/{m.id}/completa",
                "is_manual": True,
            }
        )

    def sort_key(it: dict) -> tuple:
        due = it.get("due_at") or datetime.max
        pri = {"high": 0, "medium": 1, "low": 2}.get(it.get("priority") or "medium", 1)
        return (pri, due)

    open_items.sort(key=sort_key)

    oggi_items = []
    overdue = []
    upcoming = []
    for it in open_items:
        due = it.get("due_at")
        if due is None:
            upcoming.append(it)
        elif due < now.replace(hour=0, minute=0, second=0, microsecond=0):
            overdue.append(it)
        elif due <= today_end:
            oggi_items.append(it)
        else:
            upcoming.append(it)

    done_items = [
        {
            "id": f"manual:{m.id}",
            "manual_id": m.id,
            "source": "manual",
            "title": m.title,
            "patient": m.patient,
            "patient_id": m.patient_id,
            "patient_name": (
                f"{m.patient.nome} {m.patient.cognome}" if m.patient else None
            ),
            "due_at": m.due_at,
            "priority": m.priority,
            "tipo": m.tipo,
            "status": "done",
            "action_label": "Riapri",
            "action_url": f"/admin/attivita/{m.id}/riapri",
            "is_manual": True,
        }
        for m in manuals_done[:50]
    ]

    buckets = {
        "oggi": oggi_items + overdue[:10],  # overdue surfaced in Oggi too
        "ritardo": overdue,
        "prossime": upcoming,
        "completate": done_items,
    }
    selected = buckets.get(bucket, buckets["oggi"])

    return {
        "bucket": bucket,
        "items": selected,
        "counts": {
            "oggi": len(oggi_items) + min(len(overdue), 10),
            "ritardo": len(overdue),
            "prossime": len(upcoming),
            "completate": len(done_items),
            "total_open": len(open_items),
        },
        "all_open": open_items,
    }


def dashboard_todo_preview(limit: int = 8) -> list[dict[str, Any]]:
    inbox = build_inbox(bucket="oggi")
    # Prefer overdue + today, then upcoming
    merged = inbox["counts"] and (
        [i for i in inbox["all_open"] if i.get("due_at") and i["due_at"] < datetime.now()]
        + [i for i in inbox["all_open"] if i.get("due_at") and i["due_at"].date() == date.today()]
        + [i for i in inbox["all_open"] if not i.get("due_at") or i["due_at"].date() > date.today()]
    )
    seen = set()
    out = []
    for it in merged:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        out.append(it)
        if len(out) >= limit:
            break
    return out
