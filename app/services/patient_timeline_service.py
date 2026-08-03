"""Timeline unificata paziente: aggregazione in lettura (nessuna duplicazione)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.models.diario import Consultation
from app.models.models import (
    Allenamento,
    Appuntamento,
    Dieta,
    DietPlan,
    Documento,
    Patient,
    PatientNote,
    Progresso,
)
from app.utils.tenant import assert_patient_tenant


_TIPO_APP = {
    "allenamento_1to1": "Allenamento 1to1",
    "rinnovo_dieta": "Rinnovo dieta",
    "rinnovo_allenamento": "Rinnovo allenamento",
    "check": "Check",
    "altro": "Altro",
}


def _dt(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.combine(value, datetime.min.time())
    except Exception:  # noqa: BLE001
        return None


def get_patient_timeline(
    *,
    patient: Patient,
    page: int = 1,
    per_page: int = 30,
) -> dict[str, Any]:
    """Aggrega eventi da tabelle esistenti, ordinati DESC, paginati."""
    assert_patient_tenant(patient)
    patient_id = patient.id
    events: list[dict[str, Any]] = []

    created = _dt(patient.data_creazione)
    if created:
        events.append(
            {
                "at": created,
                "tipo": "paziente",
                "tipo_label": "Paziente",
                "title": "Paziente creato",
                "description": f"{patient.nome} {patient.cognome} aggiunto in anagrafica",
                "url": None,
            }
        )

    for a in Appuntamento.query.filter_by(patient_id=patient_id).all():
        at = _dt(a.data_appuntamento)
        if not at:
            continue
        events.append(
            {
                "at": at,
                "tipo": "appuntamento",
                "tipo_label": "Appuntamento",
                "title": _TIPO_APP.get(a.tipo, a.tipo or "Appuntamento"),
                "description": f"Stato: {a.stato}",
                "url": f"/admin/pazienti/{patient_id}?tab=appuntamenti",
            }
        )

    for plan in DietPlan.query.filter_by(patient_id=patient_id).all():
        at = _dt(plan.updated_at or plan.created_at)
        if not at:
            continue
        status_label = "Pubblicata" if plan.status == "published" else "Bozza"
        events.append(
            {
                "at": at,
                "tipo": "dieta",
                "tipo_label": "Dieta",
                "title": plan.title or "Piano alimentare",
                "description": status_label,
                "url": f"/admin/diet-plans/{plan.id}",
            }
        )

    for d in Dieta.query.filter_by(patient_id=patient_id).all():
        at = _dt(d.created_at) or _dt(d.data_inizio)
        if not at:
            continue
        events.append(
            {
                "at": at,
                "tipo": "dieta",
                "tipo_label": "Dieta PDF",
                "title": f"Dieta {d.data_inizio.strftime('%d/%m/%Y')} – {d.data_fine.strftime('%d/%m/%Y')}",
                "description": f"{d.kcal} kcal" if d.kcal else "Dieta PDF",
                "url": f"/admin/pazienti/{patient_id}?tab=diete",
            }
        )

    for w in Allenamento.query.filter_by(patient_id=patient_id).all():
        at = _dt(w.created_at) or _dt(w.data_inizio)
        if not at:
            continue
        events.append(
            {
                "at": at,
                "tipo": "allenamento",
                "tipo_label": "Allenamento",
                "title": f"Allenamento dal {w.data_inizio.strftime('%d/%m/%Y')}",
                "description": f"Fino al {w.data_fine.strftime('%d/%m/%Y')}",
                "url": f"/admin/pazienti/{patient_id}?tab=allenamenti",
            }
        )

    for p in Progresso.query.filter_by(patient_id=patient_id).all():
        at = _dt(p.data_check)
        if not at:
            continue
        peso = f" · {p.peso_settimanale} kg" if p.peso_settimanale else ""
        events.append(
            {
                "at": at,
                "tipo": "progresso",
                "tipo_label": "Progresso",
                "title": f"Check {p.tipo_check or ''}".strip(),
                "description": f"Registrato{peso}",
                "url": f"/progressi/admin/dettaglio/{p.id}",
            }
        )

    for doc in Documento.query.filter_by(patient_id=patient_id).all():
        at = _dt(doc.data_upload)
        if not at:
            continue
        events.append(
            {
                "at": at,
                "tipo": "documento",
                "tipo_label": "Documento",
                "title": doc.tipo or "Documento",
                "description": (doc.descrizione or "")[:120],
                "url": f"/admin/pazienti/{patient_id}?tab=documenti",
            }
        )

    for note in PatientNote.query.filter_by(patient_id=patient_id).all():
        at = _dt(note.created_at)
        if not at:
            continue
        events.append(
            {
                "at": at,
                "tipo": "nota",
                "tipo_label": "Nota",
                "title": "Nota aggiunta",
                "description": (note.body or "")[:140],
                "url": f"/admin/pazienti/{patient_id}?tab=note",
            }
        )

    for c in Consultation.query.filter_by(patient_id=patient_id).all():
        at = _dt(c.data_colloquio) or _dt(getattr(c, "created_at", None))
        if not at:
            continue
        stato = getattr(c, "stato", None)
        stato_val = stato.value if hasattr(stato, "value") else (stato or "")
        events.append(
            {
                "at": at,
                "tipo": "diario",
                "tipo_label": "Diario",
                "title": "Colloquio",
                "description": f"Stato: {stato_val}",
                "url": f"/admin/pazienti/{patient_id}?tab=diario",
            }
        )

    events.sort(key=lambda e: e["at"] or datetime.min, reverse=True)

    page = max(1, int(page or 1))
    per_page = min(100, max(1, int(per_page or 30)))
    total = len(events)
    start = (page - 1) * per_page
    chunk = events[start : start + per_page]

    for e in chunk:
        at = e["at"]
        e["at_label"] = at.strftime("%d/%m/%Y %H:%M") if at else ""
        e["at_iso"] = at.isoformat(sep=" ", timespec="minutes") if at else ""

    return {
        "events": chunk,
        "items": chunk,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
    }
