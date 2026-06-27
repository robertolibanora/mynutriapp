# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""Calendario da tabella slot_disponibili (dashboard / CRM)."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping, Optional

from app.config import get_business_timezone
from crm import crud
from integrations.base import CalendarProvider, IntegrationError, Slot

logger = logging.getLogger(__name__)

_MAX_SLOTS = 5

_GIORNI_IT: tuple[str, ...] = (
    "Lunedì",
    "Martedì",
    "Mercoledì",
    "Giovedì",
    "Venerdì",
    "Sabato",
    "Domenica",
)


def _label_it(dt_local: datetime) -> str:
    giorno = _GIORNI_IT[dt_local.weekday()]
    return f"{giorno} {dt_local.day} alle {dt_local.strftime('%H:%M')}"


def _parse_ora(ora: Any) -> time:
    if isinstance(ora, time):
        return ora
    s = str(ora or "").strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    raise IntegrationError(f"ora slot non valida: {ora!r}")


def _parse_data(data: Any) -> date:
    if isinstance(data, date) and not isinstance(data, datetime):
        return data
    s = str(data or "").strip()[:10]
    return date.fromisoformat(s)


def _row_to_slot(row: dict[str, Any]) -> Slot:
    tz = get_business_timezone()
    d = _parse_data(row["data"])
    t = _parse_ora(row["ora"])
    durata = int(row.get("durata_minuti") or 60)
    start_local = datetime.combine(d, t, tzinfo=tz)
    end_local = start_local + timedelta(minutes=durata)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return Slot(
        start_iso=start_utc.isoformat().replace("+00:00", "Z"),
        end_iso=end_utc.isoformat().replace("+00:00", "Z"),
        label=_label_it(start_local),
        ref=str(row["id"]),
        slot_id=int(row["id"]),
    )


def slot_from_db_row(row: Mapping[str, Any]) -> Slot:
    """Converte una riga slot_disponibili in Slot (ISO UTC + slot_id)."""
    return _row_to_slot(dict(row))


class DatabaseCalendar(CalendarProvider):
    """Slot liberi da `slot_disponibili`; al booking marca `occupato`."""

    slug = "db"

    def __init__(self, agent_key: str = "gloria") -> None:
        self._agent_key = str(agent_key or "gloria").strip().lower() or "gloria"

    def health_check(self) -> bool:
        try:
            crud.list_slot(solo_liberi=True)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("db calendar health_check fallito: %s", exc)
            return False

    async def get_free_slots(self, date_iso: str) -> list[Slot]:
        return await asyncio.to_thread(self._get_free_slots_sync, date_iso)

    def _get_free_slots_sync(self, date_iso: str) -> list[Slot]:
        rows = crud.list_slot_for_date(
            date_iso, solo_liberi=True, agent_key=self._agent_key, limit=_MAX_SLOTS
        )
        out: list[Slot] = []
        for row in rows:
            try:
                out.append(_row_to_slot(row))
            except (IntegrationError, ValueError, KeyError) as exc:
                logger.warning("slot DB ignorato id=%s: %s", row.get("id"), exc)
        return out[:_MAX_SLOTS]

    async def create_event(
        self,
        nome: str,
        telefono: str,
        email: Optional[str],
        slot: Slot,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._create_event_sync, nome, telefono, email, slot, kwargs
        )

    def _create_event_sync(
        self,
        nome: str,
        telefono: str,
        email: Optional[str],
        slot: Slot,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        ref = (slot.ref or "").strip()
        if not ref:
            raise IntegrationError("slot DB senza ref (id mancante)")
        try:
            slot_id = int(ref)
        except ValueError as exc:
            raise IntegrationError(f"ref slot non numerico: {ref!r}") from exc

        row = crud.get_slot(slot_id)
        if row is None:
            raise IntegrationError(f"slot id={slot_id} non trovato")
        if row.get("occupato"):
            raise IntegrationError(f"slot id={slot_id} già occupato")

        note_parts = [f"Cliente: {nome}", f"Tel: {telefono}"]
        if email:
            note_parts.append(f"Email: {email}")
        if extra.get("note"):
            note_parts.append(str(extra["note"]))
        note = "\n".join(note_parts)
        existing_note = (row.get("note") or "").strip()
        if existing_note:
            note = f"{existing_note}\n---\n{note}"

        # Claim atomico: previene la doppia prenotazione dello stesso slot da parte
        # di due richieste concorrenti (la UPDATE applica WHERE occupato = FALSE).
        if not crud.claim_slot_if_free(slot_id, note=note):
            raise IntegrationError(f"slot id={slot_id} già occupato (doppia prenotazione evitata)")

        return {
            "event_id": str(slot_id),
            "meet_link": "",
            "html_link": "",
            "slot_dt": slot.start_iso,
        }
