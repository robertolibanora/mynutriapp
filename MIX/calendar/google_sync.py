"""Backfill appuntamenti CRM → Google Calendar."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from integrations.base import Slot
from integrations.calendar.db import slot_from_db_row

logger = logging.getLogger(__name__)

_GOOGLE_EVENT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{8,}")


def is_google_event_synced(external_event_id: str | None) -> bool:
    """True se external_event_id sembra un id evento Google (non solo slot DB)."""
    raw = str(external_event_id or "").strip()
    if not raw:
        return False
    if raw.isdigit():
        return False
    return bool(_GOOGLE_EVENT_ID_RE.match(raw))


def _slot_from_appointment(appt: Mapping[str, Any]) -> Slot | None:
    from crm import crud

    ext = str(appt.get("external_event_id") or "").strip()
    if ext.isdigit():
        row = crud.get_slot(int(ext))
        if row:
            return slot_from_db_row(row)

    start = appt.get("start_time")
    end = appt.get("end_time")
    if not start:
        return None
    if isinstance(start, datetime):
        start_dt = start
        if start_dt.tzinfo is None:
            from crm.timezone import ROME_TZ

            start_dt = start_dt.replace(tzinfo=ROME_TZ)
    else:
        from crm.timezone import ROME_TZ

        start_dt = datetime.fromisoformat(str(start).replace(" ", "T"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=ROME_TZ)

    if isinstance(end, datetime):
        end_dt = end
        if end_dt.tzinfo is None:
            from crm.timezone import ROME_TZ

            end_dt = end_dt.replace(tzinfo=ROME_TZ)
    elif end:
        end_dt = datetime.fromisoformat(str(end).replace(" ", "T"))
        if end_dt.tzinfo is None:
            from crm.timezone import ROME_TZ

            end_dt = end_dt.replace(tzinfo=ROME_TZ)
    else:
        end_dt = start_dt + timedelta(minutes=60)

    start_utc = start_dt.astimezone(timezone.utc)
    end_utc = end_dt.astimezone(timezone.utc)
    ref = ext if ext.isdigit() else ""
    slot_id = int(ext) if ext.isdigit() else None
    return Slot(
        start_iso=start_utc.isoformat().replace("+00:00", "Z"),
        end_iso=end_utc.isoformat().replace("+00:00", "Z"),
        label=start_dt.strftime("%d/%m/%Y %H:%M"),
        ref=ref or None,
        slot_id=slot_id,
    )


async def sync_appointment_to_google(
    appt: Mapping[str, Any],
    *,
    agent_key: str,
    google_calendar: Any,
) -> dict[str, Any]:
    """Crea evento Google per un appuntamento CRM e aggiorna il record."""
    from crm import crud

    appt_id = int(appt["id"])
    client_id = int(appt["client_id"])
    client = crud.get_client(client_id) or {}
    slot = _slot_from_appointment(appt)
    if slot is None:
        raise ValueError(f"appuntamento #{appt_id}: impossibile ricostruire lo slot")

    nome = str(client.get("nome") or appt.get("cliente_nome") or "Cliente").strip()
    telefono = str(client.get("telefono") or appt.get("cliente_telefono") or "").strip()
    email = str(client.get("email") or "").strip() or None

    result = await google_calendar.create_event(
        nome=nome,
        telefono=telefono,
        email=email,
        slot=slot,
        client_id=client_id,
        description=(
            f"Appuntamento sincronizzato da CRM\n"
            f"Cliente: {nome}\nTel: {telefono}"
        ),
    )
    gid = str(result.get("event_id") or result.get("google_event_id") or "").strip()
    meet = str(result.get("meet_link") or "").strip() or None
    html = str(result.get("html_link") or "").strip() or None

    patch: dict[str, Any] = {}
    if gid:
        patch["external_event_id"] = gid
    if meet:
        patch["meet_url"] = meet
    if patch:
        crud.update_appointment(appt_id, **patch)

    logger.info(
        "google sync OK appt_id=%s client_id=%s event_id=%s",
        appt_id,
        client_id,
        gid[:24] if gid else "",
    )
    return {
        "appointment_id": appt_id,
        "event_id": gid,
        "meet_link": meet,
        "html_link": html,
    }


async def sync_pending_appointments(
    agent_key: str = "gloria",
    *,
    appointment_ids: list[int] | None = None,
) -> tuple[int, int, list[str]]:
    """Sincronizza appuntamenti confermati non ancora su Google Calendar."""
    from crm import crud
    from integrations.factory import build_calendar

    cal = build_calendar(agent_key)
    google = getattr(cal, "google", None)
    if google is None:
        raise RuntimeError("Google Calendar non configurato per questo agente")

    pending: list[dict[str, Any]] = []
    for appt in crud.list_appointments():
        if str(appt.get("status") or "") != "confirmed":
            continue
        ak = str(appt.get("agente") or appt.get("agent_key") or "").strip().lower()
        if ak and ak != agent_key.strip().lower():
            continue
        aid = int(appt["id"])
        if appointment_ids and aid not in appointment_ids:
            continue
        if is_google_event_synced(appt.get("external_event_id")):
            continue
        pending.append(appt)

    ok = 0
    errors: list[str] = []
    for appt in pending:
        aid = int(appt["id"])
        try:
            await sync_appointment_to_google(appt, agent_key=agent_key, google_calendar=google)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            msg = f"appuntamento #{aid}: {exc}"
            errors.append(msg)
            logger.warning("google sync fallito %s", msg)

    return ok, len(pending), errors
