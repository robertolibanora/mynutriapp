# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""GoogleCalendar: freebusy → list[Slot] (label IT) + booking con Google Meet."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import business_hours_end_time, business_hours_start_time
from integrations.base import (
    CalendarProvider,
    IntegrationError,
    Slot,
)

logger = logging.getLogger(__name__)

_SLOT_MINUTES = 30
_WORK_DAY_START = business_hours_start_time()
_WORK_DAY_END = business_hours_end_time()
_MAX_SLOTS = 5
_SCOPES = ["https://www.googleapis.com/auth/calendar"]

_GIORNI_IT: tuple[str, ...] = (
    "Lunedì",
    "Martedì",
    "Mercoledì",
    "Giovedì",
    "Venerdì",
    "Sabato",
    "Domenica",
)


def _get_zoneinfo(name: str) -> ZoneInfo:
    n = (name or "").strip()
    if not n:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(n)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _parse_credentials(raw: str | dict[str, Any]) -> dict[str, Any]:
    """Accetta JSON inline, dict già parsato, oppure path a file su disco."""
    if isinstance(raw, dict):
        return raw
    s = (raw or "").strip()
    if not s:
        raise IntegrationError("GOOGLE_CREDENTIALS_JSON vuoto")
    if s.startswith("{"):
        return json.loads(s)
    with open(s, encoding="utf-8") as fh:
        return json.load(fh)


def _label_it(dt_local: datetime) -> str:
    """Formatta uno slot come 'Lunedì 26 alle 10:00' (giorno, giorno_mese, ora locale)."""
    giorno = _GIORNI_IT[dt_local.weekday()]
    return f"{giorno} {dt_local.day} alle {dt_local.strftime('%H:%M')}"


class GoogleCalendar(CalendarProvider):
    """Calendario Google con generazione Meet link a ogni evento."""

    slug = "google_calendar"

    def __init__(
        self,
        credentials: dict[str, Any] | str,
        calendar_id: str,
        timezone_name: str = "Europe/Rome",
    ) -> None:
        if not calendar_id:
            raise IntegrationError("calendar_id vuoto (env GOOGLE_CALENDAR_ID)")
        creds_dict = _parse_credentials(credentials)
        creds = Credentials.from_service_account_info(creds_dict, scopes=_SCOPES)
        self._service = build(
            "calendar", "v3", credentials=creds, cache_discovery=False
        )
        self._calendar_id = calendar_id
        self._tz_name = timezone_name or "Europe/Rome"

    # ----- helpers ----------------------------------------------------

    def _local_tzinfo(self) -> tzinfo:
        return _get_zoneinfo(self._tz_name)

    def _day_window_utc(self, date_iso: str) -> tuple[str, str]:
        d = datetime.strptime(date_iso, "%Y-%m-%d").date()
        tz = self._local_tzinfo()
        start = datetime.combine(d, _WORK_DAY_START, tzinfo=tz).astimezone(timezone.utc)
        end = datetime.combine(d, _WORK_DAY_END, tzinfo=tz).astimezone(timezone.utc)
        return (
            start.isoformat().replace("+00:00", "Z"),
            end.isoformat().replace("+00:00", "Z"),
        )

    def _candidate_slots(self, date_iso: str) -> list[datetime]:
        d = datetime.strptime(date_iso, "%Y-%m-%d").date()
        tz = self._local_tzinfo()
        out: list[datetime] = []
        cur = datetime.combine(d, _WORK_DAY_START, tzinfo=tz)
        end = datetime.combine(d, _WORK_DAY_END, tzinfo=tz)
        while cur + timedelta(minutes=_SLOT_MINUTES) <= end:
            out.append(cur)
            cur = cur + timedelta(minutes=_SLOT_MINUTES)
        return out

    # ----- API pubblica -----------------------------------------------

    def health_check(self) -> bool:
        try:
            self._service.calendars().get(calendarId=self._calendar_id).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("google calendar health_check fallito: %s", exc)
            return False
        return self.verify_write_access()

    def verify_write_access(self) -> bool:
        """Verifica che il service account possa creare eventi (non solo leggerli)."""
        try:
            from datetime import timedelta

            tz = self._local_tzinfo()
            start = datetime.now(tz).replace(hour=3, minute=0, second=0, microsecond=0)
            if start.date() < datetime.now(tz).date():
                start = start + timedelta(days=1)
            end = start + timedelta(minutes=15)
            body = {
                "summary": "AgentMetrics write test (ignora)",
                "start": {"dateTime": start.isoformat(), "timeZone": self._tz_name},
                "end": {"dateTime": end.isoformat(), "timeZone": self._tz_name},
            }
            event = (
                self._service.events()
                .insert(calendarId=self._calendar_id, body=body)
                .execute()
            )
            eid = event.get("id")
            if eid:
                self._service.events().delete(
                    calendarId=self._calendar_id, eventId=eid
                ).execute()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "google calendar verify_write_access fallito: %s "
                "(condividi il calendario con il service account come Editor)",
                exc,
            )
            return False

    async def get_free_slots(self, date_iso: str) -> list[Slot]:
        """Slot liberi nella data (max 3), come Slot con label IT e ISO UTC."""
        return await asyncio.to_thread(self._get_free_slots_sync, date_iso)

    def _get_free_slots_sync(self, date_iso: str) -> list[Slot]:
        time_min, time_max = self._day_window_utc(date_iso)
        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "timeZone": self._tz_name,
            "items": [{"id": self._calendar_id}],
        }
        try:
            resp = self._service.freebusy().query(body=body).execute()
            busy = resp["calendars"][self._calendar_id].get("busy", [])
        except HttpError as exc:
            logger.error("google freebusy errore: %s", exc)
            return []
        busy_ranges: list[tuple[datetime, datetime]] = []
        for b in busy:
            try:
                bs = datetime.fromisoformat(b["start"].replace("Z", "+00:00"))
                be = datetime.fromisoformat(b["end"].replace("Z", "+00:00"))
                busy_ranges.append((bs, be))
            except Exception:  # noqa: BLE001
                continue
        tz_local = self._local_tzinfo()
        out: list[Slot] = []
        for slot_start in self._candidate_slots(date_iso):
            slot_end = slot_start + timedelta(minutes=_SLOT_MINUTES)
            slot_start_utc = slot_start.astimezone(timezone.utc)
            slot_end_utc = slot_end.astimezone(timezone.utc)
            conflict = any(
                slot_start_utc < be and bs < slot_end_utc for bs, be in busy_ranges
            )
            if conflict:
                continue
            out.append(
                Slot(
                    start_iso=slot_start_utc.isoformat().replace("+00:00", "Z"),
                    end_iso=slot_end_utc.isoformat().replace("+00:00", "Z"),
                    label=_label_it(slot_start.astimezone(tz_local)),
                )
            )
            if len(out) >= _MAX_SLOTS:
                break
        return out

    async def create_event(
        self,
        nome: str,
        telefono: str,
        email: Optional[str],
        slot: Slot,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Crea un evento con Google Meet a partire da Slot; ritorna metadati."""
        return await asyncio.to_thread(
            self._create_event_sync, nome, telefono, email, slot, kwargs
        )

    def _meet_not_supported(self, exc: HttpError) -> bool:
        if exc.resp.status != 400:
            return False
        msg = str(exc).lower()
        return "invalid conference type" in msg or "conference" in msg

    def _insert_event(self, body: dict[str, Any], *, with_meet: bool) -> dict[str, Any]:
        payload = dict(body)
        if with_meet:
            payload["conferenceData"] = {
                "createRequest": {
                    "requestId": uuid.uuid4().hex,
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }
            return (
                self._service.events()
                .insert(
                    calendarId=self._calendar_id,
                    body=payload,
                    conferenceDataVersion=1,
                    sendUpdates="none",
                )
                .execute()
            )
        return (
            self._service.events()
            .insert(
                calendarId=self._calendar_id,
                body=payload,
                sendUpdates="none",
            )
            .execute()
        )

    def _create_event_sync(
        self,
        nome: str,
        telefono: str,
        email: Optional[str],
        slot: Slot,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        start = datetime.fromisoformat(slot.start_iso.replace("Z", "+00:00"))
        if slot.end_iso:
            end = datetime.fromisoformat(slot.end_iso.replace("Z", "+00:00"))
        else:
            end = start + timedelta(minutes=_SLOT_MINUTES)
        summary = extra.get("summary") or f"Appuntamento {nome}"
        description = extra.get("description") or (
            f"Cliente: {nome}\nTelefono: {telefono}\n"
            f"Email: {email or '-'}"
        )
        # Service account: niente attendees né sendUpdates — Google rifiuta gli inviti
        # senza Domain-Wide Delegation; email e telefono restano in description.
        body: dict[str, Any] = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start.isoformat(), "timeZone": self._tz_name},
            "end": {"dateTime": end.isoformat(), "timeZone": self._tz_name},
        }
        try:
            event = self._insert_event(body, with_meet=True)
        except HttpError as exc:
            if not self._meet_not_supported(exc):
                logger.error("google insert event errore: %s", exc)
                raise
            logger.info(
                "google calendar senza Meet (calendario non supporta conferenceData): %s",
                self._calendar_id,
            )
            event = self._insert_event(body, with_meet=False)
        meet_link = ""
        for entry in (event.get("conferenceData", {}).get("entryPoints") or []):
            if entry.get("entryPointType") == "video":
                meet_link = entry.get("uri", "")
                break
        return {
            "event_id": event.get("id", ""),
            "meet_link": meet_link,
            "html_link": event.get("htmlLink", ""),
            "slot_dt": slot.start_iso,
        }

    async def delete_event(self, event_id: str) -> bool:
        """Elimina un evento Google Calendar (idempotente se già assente)."""
        return await asyncio.to_thread(self._delete_event_sync, event_id)

    def _delete_event_sync(self, event_id: str) -> bool:
        eid = str(event_id or "").strip()
        if not eid:
            return False
        try:
            self._service.events().delete(
                calendarId=self._calendar_id,
                eventId=eid,
            ).execute()
            return True
        except HttpError as exc:
            if exc.resp.status == 404:
                return True
            logger.warning("google delete event errore id=%s: %s", eid, exc)
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning("google delete event fallito id=%s: %s", eid, exc)
            return False
