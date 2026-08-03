"""Ricerca globale pazienti tenant-scoped (header admin)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_

from app.models.models import Appuntamento, Patient, db
from app.services.paziente_service import LABEL_STATO_CLIENTE
from app.utils.tenant import patients_query_for_tenant, require_tenant, tenant_filter_enabled


def search_patients(q: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """Cerca pazienti per nome, cognome, telefono, email. Max ``limit`` risultati."""
    query_text = (q or "").strip()
    if len(query_text) < 2:
        return []

    limit = max(1, min(int(limit or 8), 20))
    now = datetime.now()

    base = patients_query_for_tenant() if tenant_filter_enabled() else Patient.query
    like = f"%{query_text}%"
    full_name = Patient.nome + " " + Patient.cognome

    rows = (
        base.filter(
            or_(
                Patient.nome.ilike(like),
                Patient.cognome.ilike(like),
                full_name.ilike(like),
                Patient.telefono.ilike(like),
                Patient.email.ilike(like),
            )
        )
        .order_by(Patient.cognome.asc(), Patient.nome.asc())
        .limit(limit)
        .all()
    )

    if not rows:
        return []

    patient_ids = [p.id for p in rows]
    app_q = db.session.query(
        Appuntamento.patient_id, func.min(Appuntamento.data_appuntamento)
    ).filter(
        Appuntamento.patient_id.in_(patient_ids),
        Appuntamento.data_appuntamento >= now,
        Appuntamento.stato.in_(("in_attesa", "confermato")),
    )
    if tenant_filter_enabled():
        app_q = app_q.filter(Appuntamento.utente_id == require_tenant())

    next_apps = {
        int(pid): dt for pid, dt in app_q.group_by(Appuntamento.patient_id).all()
    }

    results = []
    for p in rows:
        stato = p.stato_cliente or "attivo"
        next_dt = next_apps.get(p.id)
        results.append(
            {
                "id": p.id,
                "nome": p.nome,
                "cognome": p.cognome,
                "nome_completo": f"{p.nome} {p.cognome}",
                "stato": stato,
                "stato_label": LABEL_STATO_CLIENTE.get(stato, stato),
                "telefono": p.telefono or "",
                "email": p.email or "",
                "prossimo_appuntamento": (
                    next_dt.isoformat(sep=" ", timespec="minutes") if next_dt else None
                ),
                "prossimo_appuntamento_label": (
                    next_dt.strftime("%d/%m/%Y %H:%M") if next_dt else None
                ),
                "url": f"/admin/pazienti/{p.id}",
            }
        )
    return results
