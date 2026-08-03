"""Aggregazioni per lista pazienti densa (evita N+1)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import aliased

from app.models.models import (
    Allenamento,
    Appuntamento,
    DietPlan,
    Patient,
    Progresso,
    db,
)
from app.utils.tenant import patients_query_for_tenant, require_tenant, tenant_filter_enabled


def list_patients_enriched(
    *,
    search: str = "",
    filtro: str = "tutti",
    sort: str = "nome",
) -> list[dict[str, Any]]:
    now = datetime.now()
    oggi = date.today()

    base = patients_query_for_tenant() if tenant_filter_enabled() else Patient.query

    if search:
        like = f"%{search.strip()}%"
        full = Patient.nome + " " + Patient.cognome
        base = base.filter(
            or_(
                Patient.nome.ilike(like),
                Patient.cognome.ilike(like),
                full.ilike(like),
                Patient.telefono.ilike(like),
                Patient.email.ilike(like),
            )
        )

    if filtro in ("attivo", "provvisorio", "non_attivo"):
        base = base.filter(Patient.stato_cliente == filtro)

    patients = base.all()
    if not patients:
        return []

    ids = [p.id for p in patients]

    # Ultimo peso
    last_progress = (
        db.session.query(
            Progresso.patient_id,
            func.max(Progresso.data_check).label("last_check"),
        )
        .filter(Progresso.patient_id.in_(ids), Progresso.peso_settimanale.isnot(None))
        .group_by(Progresso.patient_id)
        .subquery()
    )
    peso_rows = (
        db.session.query(Progresso.patient_id, Progresso.peso_settimanale, Progresso.data_check)
        .join(
            last_progress,
            and_(
                Progresso.patient_id == last_progress.c.patient_id,
                Progresso.data_check == last_progress.c.last_check,
            ),
        )
        .filter(Progresso.peso_settimanale.isnot(None))
        .all()
    )
    peso_map = {r.patient_id: (float(r.peso_settimanale), r.data_check) for r in peso_rows}

    # Ultima visita (completata o qualsiasi passato)
    last_visit_q = (
        db.session.query(
            Appuntamento.patient_id,
            func.max(Appuntamento.data_appuntamento).label("last_visit"),
        )
        .filter(
            Appuntamento.patient_id.in_(ids),
            Appuntamento.data_appuntamento < now,
            Appuntamento.stato != "annullato",
        )
    )
    if tenant_filter_enabled():
        last_visit_q = last_visit_q.filter(Appuntamento.utente_id == require_tenant())
    last_visit_map = {r.patient_id: r.last_visit for r in last_visit_q.group_by(Appuntamento.patient_id)}

    # Prossimo appuntamento
    next_app_q = (
        db.session.query(
            Appuntamento.patient_id,
            func.min(Appuntamento.data_appuntamento).label("next_app"),
        )
        .filter(
            Appuntamento.patient_id.in_(ids),
            Appuntamento.data_appuntamento >= now,
            Appuntamento.stato.in_(("in_attesa", "confermato")),
        )
    )
    if tenant_filter_enabled():
        next_app_q = next_app_q.filter(Appuntamento.utente_id == require_tenant())
    next_app_map = {r.patient_id: r.next_app for r in next_app_q.group_by(Appuntamento.patient_id)}

    # Dieta attiva (published)
    diet_rows = (
        db.session.query(DietPlan.patient_id, DietPlan.title, DietPlan.id)
        .filter(DietPlan.patient_id.in_(ids), DietPlan.status == "published")
        .order_by(DietPlan.updated_at.desc())
        .all()
    )
    diet_map: dict[int, tuple] = {}
    for r in diet_rows:
        if r.patient_id not in diet_map:
            diet_map[r.patient_id] = (r.title, r.id)

    # Draft diets count
    draft_counts = dict(
        db.session.query(DietPlan.patient_id, func.count(DietPlan.id))
        .filter(DietPlan.patient_id.in_(ids), DietPlan.status == "draft")
        .group_by(DietPlan.patient_id)
        .all()
    )

    # Ultimo allenamento
    last_w = (
        db.session.query(
            Allenamento.patient_id,
            func.max(Allenamento.created_at).label("last_w"),
        )
        .filter(Allenamento.patient_id.in_(ids))
        .group_by(Allenamento.patient_id)
        .subquery()
    )
    w_rows = (
        db.session.query(Allenamento.patient_id, Allenamento.id, Allenamento.data_fine)
        .join(
            last_w,
            and_(
                Allenamento.patient_id == last_w.c.patient_id,
                Allenamento.created_at == last_w.c.last_w,
            ),
        )
        .all()
    )
    workout_map = {r.patient_id: (r.id, r.data_fine) for r in w_rows}

    rows: list[dict[str, Any]] = []
    for p in patients:
        peso_info = peso_map.get(p.id)
        peso = peso_info[0] if peso_info else None
        delta = None
        if peso is not None and p.peso_iniziale is not None:
            delta = round(peso - float(p.peso_iniziale), 1)

        next_app = next_app_map.get(p.id)
        last_visit = last_visit_map.get(p.id)
        diet = diet_map.get(p.id)
        workout = workout_map.get(p.id)
        drafts = int(draft_counts.get(p.id) or 0)

        alerts = []
        if drafts:
            alerts.append(f"{drafts} dieta in bozza" if drafts == 1 else f"{drafts} diete in bozza")
        if p.stato_cliente == "attivo" and not next_app:
            alerts.append("Senza appuntamento futuro")
        if workout and workout[1] and workout[1] >= oggi and (workout[1] - oggi).days <= 14:
            alerts.append("Allenamento in scadenza")

        eta = None
        if p.data_nascita:
            eta = oggi.year - p.data_nascita.year - (
                (oggi.month, oggi.day) < (p.data_nascita.month, p.data_nascita.day)
            )

        rows.append(
            {
                "patient": p,
                "eta": eta,
                "peso": peso,
                "delta_peso": delta,
                "ultima_visita": last_visit,
                "prossimo_appuntamento": next_app,
                "dieta_attiva": diet[0] if diet else None,
                "dieta_id": diet[1] if diet else None,
                "allenamento_attivo": bool(workout and workout[1] and workout[1] >= oggi),
                "allenamento_id": workout[0] if workout else None,
                "alerts": alerts,
                "has_pending": bool(alerts or drafts),
            }
        )

    if filtro == "senza_appuntamento":
        rows = [r for r in rows if r["patient"].stato_cliente == "attivo" and not r["prossimo_appuntamento"]]
    elif filtro == "con_attivita":
        rows = [r for r in rows if r["has_pending"]]

    def sort_key(r: dict):
        p = r["patient"]
        if sort == "ultima_visita":
            return (r["ultima_visita"] is None, r["ultima_visita"] or datetime.min)
        if sort == "prossimo_appuntamento":
            return (r["prossimo_appuntamento"] is None, r["prossimo_appuntamento"] or datetime.max)
        if sort == "creazione":
            return (p.data_creazione is None, -(p.data_creazione.timestamp() if p.data_creazione else 0))
        # nome default
        return ((p.cognome or "").lower(), (p.nome or "").lower())

    reverse = sort == "creazione"
    if sort == "ultima_visita":
        rows.sort(key=sort_key, reverse=True)
    else:
        rows.sort(key=sort_key, reverse=reverse)

    return rows
