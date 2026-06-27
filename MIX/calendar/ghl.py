# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""GoHighLevel Calendar — slot liberi e booking per closer (Sara)."""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import httpx

from app.config import get_business_timezone
from crm.phone import normalize_e164
from integrations.base import CalendarProvider, IntegrationError, Slot

logger = logging.getLogger(__name__)

_GHL_BASE = "https://services.leadconnectorhq.com"
_CAL_VERSION = "2021-04-15"
_CONTACT_VERSION = "2021-07-28"
_GHL_SCOPE_HINT = (
    "Abilita nel Private Integration GHL (Sub-Account): "
    "contacts.write, contacts.readonly, calendars/events.write, calendars.readonly."
)
_MAX_RANGE_DAYS = 31
_SEARCH_DAYS = 21
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


def _split_name(nome: str) -> tuple[str, str]:
    parts = [p for p in str(nome or "").strip().split() if p]
    if not parts:
        return ("Cliente", "")
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], " ".join(parts[1:]))


def _parse_free_slots_payload(
    data: Mapping[str, Any],
    *,
    tz: ZoneInfo,
    after: datetime,
) -> list[datetime]:
    """Estrae datetime slot dalla risposta GET .../free-slots."""
    out: list[datetime] = []
    if not isinstance(data, Mapping):
        return out

    root: Mapping[str, Any] = data
    if "slots" in data and isinstance(data["slots"], Mapping):
        root = data["slots"]

    for key, val in root.items():
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(key)):
            continue
        if isinstance(val, Mapping):
            times = val.get("slots") or []
        elif isinstance(val, list):
            times = val
        else:
            continue
        for raw in times:
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            local = dt.astimezone(tz)
            if local.weekday() >= 5:
                continue
            if local < after.astimezone(tz):
                continue
            out.append(local)
    out.sort()
    return out


class GHLCalendar(CalendarProvider):
    """
    Un calendario GHL per closer. Round-robin: primo slot libero nel calendario
    del primo closer disponibile (ordine CLOSER_LIST_SARA).

    Env: GHL_TOKEN_SARA (Private Integration), GHL_LOCATION_ID_SARA,
    GHL_CALENDAR_ID_ANDREA_METTA, GHL_CALENDAR_ID_ANDREA_POCHINI
    (fallback GHL_CALENDAR_ID_SARA).
    """

    slug = "ghl"

    def __init__(
        self,
        api_key: str,
        calendar_ids: dict[str, str],
        location_id: str = "",
        timezone_name: str = "Europe/Rome",
        *,
        default_duration_min: int = 30,
        default_buffer_min: int = 10,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.location_id = (location_id or "").strip()
        self.calendar_ids = {
            str(k).strip().lower(): str(v).strip()
            for k, v in (calendar_ids or {}).items()
            if str(k).strip() and str(v).strip()
        }
        if not self.api_key:
            raise IntegrationError("GHL_TOKEN mancante (Private Integration)")
        if not self.location_id:
            raise IntegrationError("GHL_LOCATION_ID mancante")
        if not self.calendar_ids:
            raise IntegrationError("Nessun GHL_CALENDAR_ID per closer configurato")
        self._tz_name = timezone_name or "Europe/Rome"
        self._duration_min = max(15, int(default_duration_min or 30))
        self._buffer_min = max(0, int(default_buffer_min or 0))
        self._slot_spacing_min = self._duration_min + self._buffer_min

    def _tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self._tz_name)
        except Exception:  # noqa: BLE001
            return ZoneInfo("Europe/Rome")

    def calendar_id_for(self, closer_key: str) -> str | None:
        return self.calendar_ids.get(str(closer_key or "").strip().lower())

    def _headers(self, *, contacts: bool = False) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Version": _CONTACT_VERSION if contacts else _CAL_VERSION,
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        contacts: bool = False,
    ) -> Any:
        url = f"{_GHL_BASE}{path}"
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.request(
                method,
                url,
                headers=self._headers(contacts=contacts),
                params=params,
                json=json_body,
            )
        if resp.status_code >= 400:
            body = (resp.text or "")[:500]
            logger.warning("GHL %s %s → %s %s", method, path, resp.status_code, body)
            if resp.status_code == 401 and "not authorized for this scope" in body.lower():
                area = "contatti" if "/contacts" in path else "calendario"
                raise IntegrationError(
                    f"GHL token senza permessi per {area} (401). {_GHL_SCOPE_HINT}"
                )
            raise IntegrationError(f"GHL API errore {resp.status_code}: {body}")
        if not resp.content:
            return {}
        try:
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            raise IntegrationError(f"GHL risposta non JSON: {exc}") from exc

    async def fetch_free_slots(
        self,
        calendar_id: str,
        *,
        start_local: datetime,
        end_local: datetime,
    ) -> list[datetime]:
        tz = self._tz()
        # GHL free-slots richiede epoch in millisecondi (non secondi).
        start_ms = int(start_local.astimezone(tz).timestamp() * 1000)
        end_ms = int(end_local.astimezone(tz).timestamp() * 1000)
        data = await self._request(
            "GET",
            f"/calendars/{calendar_id}/free-slots",
            params={
                "startDate": start_ms,
                "endDate": end_ms,
                "timezone": self._tz_name,
            },
        )
        return _parse_free_slots_payload(
            data if isinstance(data, Mapping) else {},
            tz=tz,
            after=start_local,
        )

    def _pick_spaced_slot_times(
        self,
        times: list[datetime],
        *,
        limit: int,
    ) -> list[datetime]:
        """Propone slot con pausa minima tra un appuntamento e l'altro (durata + buffer)."""
        lim = max(1, min(int(limit or 1), 8))
        spacing = timedelta(minutes=self._slot_spacing_min)
        picked: list[datetime] = []
        for slot_dt in times:
            if picked and slot_dt < picked[-1] + spacing:
                continue
            picked.append(slot_dt)
            if len(picked) >= lim:
                break
        return picked

    @staticmethod
    def _default_open_hours() -> list[dict[str, Any]]:
        """Lun–Ven 9:00–19:00 (GHL: daysOfTheWeek 1=Mon … 5=Fri)."""
        hours = [
            {
                "openHour": 9,
                "openMinute": 0,
                "closeHour": 19,
                "closeMinute": 0,
            }
        ]
        return [
            {"daysOfTheWeek": [day], "hours": hours}
            for day in range(1, 6)
        ]

    async def ensure_slot_timing(self, calendar_id: str) -> bool:
        """Allinea durata (30 min), buffer (10 min), intervallo e orari su GHL."""
        cal_id = str(calendar_id or "").strip()
        if not cal_id:
            return False
        payload: dict[str, Any] = {
            "slotDuration": self._duration_min,
            "slotDurationUnit": "mins",
            "slotBuffer": self._buffer_min,
            "slotBufferUnit": "mins",
            "slotInterval": self._slot_spacing_min,
            "slotIntervalUnit": "mins",
            "openHours": self._default_open_hours(),
        }
        try:
            await self._request(
                "PUT",
                f"/calendars/{cal_id}",
                json_body=payload,
            )
            logger.info(
                "GHL calendar timing ok id=%s duration=%sm buffer=%sm interval=%sm",
                cal_id,
                self._duration_min,
                self._buffer_min,
                self._slot_spacing_min,
            )
            return True
        except IntegrationError as exc:
            logger.warning("GHL ensure_slot_timing fallito id=%s: %s", cal_id, exc)
            return False

    async def ensure_all_calendars_slot_timing(self) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for cal_id in dict.fromkeys(self.calendar_ids.values()):
            if cal_id:
                out[cal_id] = await self.ensure_slot_timing(cal_id)
        return out

    async def find_round_robin_available_dates(
        self,
        closers: list[dict[str, str]],
        from_dt: datetime,
        *,
        max_dates: int = 3,
    ) -> list[dict[str, Any]]:
        """Date con slot GHL (round-robin tra i closer), max N giorni distinti."""
        tz = self._tz()
        if from_dt.tzinfo is None:
            from_local = from_dt.replace(tzinfo=tz)
        else:
            from_local = from_dt.astimezone(tz)

        range_start = from_local
        range_end = from_local + timedelta(days=_SEARCH_DAYS)
        max_end = from_local + timedelta(days=_MAX_RANGE_DAYS)
        if range_end > max_end:
            range_end = max_end

        by_closer: dict[str, list[datetime]] = {}
        closer_meta: dict[str, dict[str, str]] = {}
        for closer in closers or []:
            ck = str(closer.get("key") or "").strip().lower()
            nome = str(closer.get("nome") or "").strip()
            cal_id = self.calendar_id_for(ck)
            if not ck or not cal_id:
                continue
            closer_meta[ck] = {"key": ck, "nome": nome}
            try:
                by_closer[ck] = await self.fetch_free_slots(
                    cal_id,
                    start_local=range_start,
                    end_local=range_end,
                )
            except IntegrationError as exc:
                logger.warning("GHL free-slots closer=%s: %s", ck, exc)
                by_closer[ck] = []

        pointers = {ck: 0 for ck in by_closer}
        seen_dates: set[str] = set()
        out: list[dict[str, Any]] = []
        lim = max(1, min(int(max_dates or 3), 7))

        while len(out) < lim:
            added = False
            for closer in closers or []:
                ck = str(closer.get("key") or "").strip().lower()
                slots = by_closer.get(ck) or []
                while pointers.get(ck, 0) < len(slots):
                    slot_dt = slots[pointers[ck]]
                    pointers[ck] += 1
                    d_iso = slot_dt.date().isoformat()
                    if d_iso in seen_dates:
                        continue
                    seen_dates.add(d_iso)
                    meta = closer_meta.get(ck) or {}
                    out.append(
                        {
                            "date_iso": d_iso,
                            "closer_key": ck,
                            "closer_nome": meta.get("nome")
                            or ck.replace("-", " ").title(),
                        }
                    )
                    added = True
                    break
                if len(out) >= lim:
                    break
            if not added:
                break
        return out

    async def find_round_robin_slots_for_date(
        self,
        closers: list[dict[str, str]],
        date_iso: str,
        *,
        from_dt: datetime | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Slot GHL per una data: primo closer con disponibilità (round-robin)."""
        tz = self._tz()
        try:
            d = date.fromisoformat(str(date_iso)[:10])
        except ValueError:
            return []

        start = datetime.combine(d, time(0, 0), tzinfo=tz)
        end = start + timedelta(days=1)
        if from_dt is not None:
            if from_dt.tzinfo is None:
                from_local = from_dt.replace(tzinfo=tz)
            else:
                from_local = from_dt.astimezone(tz)
            if from_local.date() == d and from_local > start:
                start = from_local

        lim = max(1, min(int(limit or 5), 8))
        for closer in closers or []:
            ck = str(closer.get("key") or "").strip().lower()
            nome = str(closer.get("nome") or "").strip()
            cal_id = self.calendar_id_for(ck)
            if not ck or not cal_id:
                continue
            try:
                times = await self.fetch_free_slots(
                    cal_id, start_local=start, end_local=end
                )
            except IntegrationError as exc:
                logger.warning("GHL free-slots closer=%s: %s", ck, exc)
                continue
            if not times:
                continue
            out: list[dict[str, Any]] = []
            for slot_dt in self._pick_spaced_slot_times(times, limit=lim):
                end_dt = slot_dt + timedelta(minutes=self._duration_min)
                out.append(
                    {
                        "closer_key": ck,
                        "closer_nome": nome or ck.replace("-", " ").title(),
                        "inizio": slot_dt,
                        "fine": end_dt,
                        "ghl_calendar_id": cal_id,
                    }
                )
            return out
        return []

    async def find_round_robin_slot(
        self,
        closers: list[dict[str, str]],
        from_dt: datetime,
        *,
        prefer_date: date | None = None,
    ) -> dict[str, Any] | None:
        """
        Primo slot GHL libero, per ordine closer.
        Returns: closer_key, closer_nome, inizio, fine, ghl_calendar_id (no slot_id DB).
        """
        tz = self._tz()
        if from_dt.tzinfo is None:
            from_local = from_dt.replace(tzinfo=tz)
        else:
            from_local = from_dt.astimezone(tz)

        date_min = prefer_date or from_local.date()
        if date_min < from_local.date():
            date_min = from_local.date()
        range_start = datetime.combine(date_min, time(0, 0), tzinfo=tz)
        if range_start < from_local:
            range_start = from_local
        range_end = range_start + timedelta(days=_SEARCH_DAYS)
        max_end = from_local + timedelta(days=_MAX_RANGE_DAYS)
        if range_end > max_end:
            range_end = max_end

        for closer in closers or []:
            ck = str(closer.get("key") or "").strip().lower()
            nome = str(closer.get("nome") or "").strip()
            cal_id = self.calendar_id_for(ck)
            if not cal_id:
                logger.warning("GHL: calendar id mancante per closer=%s", ck)
                continue
            try:
                slots = await self.fetch_free_slots(
                    cal_id,
                    start_local=range_start,
                    end_local=range_end,
                )
            except IntegrationError as exc:
                logger.warning("GHL free-slots closer=%s: %s", ck, exc)
                continue
            if not slots:
                continue
            start_dt = slots[0]
            end_dt = start_dt + timedelta(minutes=self._duration_min)
            return {
                "closer_key": ck,
                "closer_nome": nome or ck.replace("-", " ").title(),
                "inizio": start_dt,
                "fine": end_dt,
                "ghl_calendar_id": cal_id,
            }
        return None

    async def get_free_slots(self, date_iso: str) -> list[Slot]:
        """Primo closer in lista — slot per una data (interfaccia CalendarProvider)."""
        tz = self._tz()
        try:
            d = date.fromisoformat(str(date_iso)[:10])
        except ValueError as exc:
            raise IntegrationError(f"data non valida: {date_iso}") from exc
        start = datetime.combine(d, time(0, 0), tzinfo=tz)
        end = start + timedelta(days=1)
        for ck, cal_id in self.calendar_ids.items():
            try:
                times = await self.fetch_free_slots(
                    cal_id, start_local=start, end_local=end
                )
            except IntegrationError:
                continue
            slots: list[Slot] = []
            for dt in self._pick_spaced_slot_times(times, limit=5):
                end_dt = dt + timedelta(minutes=self._duration_min)
                start_utc = dt.astimezone(timezone.utc)
                end_utc = end_dt.astimezone(timezone.utc)
                slots.append(
                    Slot(
                        start_iso=start_utc.isoformat().replace("+00:00", "Z"),
                        end_iso=end_utc.isoformat().replace("+00:00", "Z"),
                        label=_label_it(dt),
                        ref=f"{cal_id}:{dt.isoformat()}",
                    )
                )
            if slots:
                return slots
        return []

    async def _upsert_contact(
        self,
        *,
        nome: str,
        telefono: str,
        email: str | None,
    ) -> str:
        first, last = _split_name(nome)
        phone = normalize_e164(telefono) or str(telefono or "").strip()
        body: dict[str, Any] = {
            "locationId": self.location_id,
            "firstName": first,
            "lastName": last or first,
            "phone": phone,
            "source": "AgentMetrics Sara",
        }
        if email and str(email).strip():
            body["email"] = str(email).strip()
        data = await self._request(
            "POST",
            "/contacts/upsert",
            json_body=body,
            contacts=True,
        )
        contact = data.get("contact") if isinstance(data, Mapping) else None
        if isinstance(contact, Mapping):
            cid = str(contact.get("id") or "").strip()
            if cid:
                return cid
        cid = str(data.get("id") or "").strip() if isinstance(data, Mapping) else ""
        if cid:
            return cid
        raise IntegrationError("GHL upsert contact senza id")

    async def create_event(
        self,
        nome: str,
        telefono: str,
        email: str | None,
        slot: Slot,
        **kwargs: Any,
    ) -> dict[str, Any]:
        closer_key = str(kwargs.get("closer_key") or "").strip().lower()
        cal_id = (
            str(kwargs.get("ghl_calendar_id") or "").strip()
            or self.calendar_id_for(closer_key)
        )
        if not cal_id:
            raise IntegrationError(
                f"calendar GHL non configurato per closer={closer_key or '?'}"
            )

        tz = self._tz()
        start_raw = str(slot.start_iso or "").strip()
        try:
            start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise IntegrationError(f"slot_datetime non valido: {start_raw}") from exc
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=tz)
        else:
            start_dt = start_dt.astimezone(tz)

        end_dt = start_dt + timedelta(minutes=self._duration_min)

        contact_id = await self._upsert_contact(
            nome=nome, telefono=telefono, email=email
        )
        title = f"Video riunione Evolution — {nome}".strip()[:200]
        payload: dict[str, Any] = {
            "calendarId": cal_id,
            "locationId": self.location_id,
            "contactId": contact_id,
            "startTime": start_dt.isoformat(),
            "endTime": end_dt.isoformat(),
            "title": title,
            "appointmentStatus": "confirmed",
        }
        assigned_user = str(kwargs.get("assigned_user_id") or "").strip()
        if assigned_user:
            payload["assignedUserId"] = assigned_user
        data = await self._request(
            "POST",
            "/calendars/events/appointments",
            json_body=payload,
        )
        event_id = ""
        if isinstance(data, Mapping):
            event_id = str(
                data.get("id") or data.get("eventId") or data.get("appointmentId") or ""
            ).strip()
        logger.info(
            "GHL book ok calendar=%s closer=%s event_id=%s start=%s",
            cal_id,
            closer_key,
            event_id,
            start_dt.isoformat(),
        )
        return {
            "event_id": event_id,
            "ghl_event_id": event_id,
            "ghl_calendar_id": cal_id,
            "contact_id": contact_id,
            "slot_dt": start_dt.isoformat(),
            "closer_key": closer_key,
        }

    async def cancel_event(self, event_id: str) -> bool:
        """Annulla un appuntamento GHL (idempotente se già assente)."""
        eid = str(event_id or "").strip()
        if not eid:
            return False
        try:
            await self._request("DELETE", f"/calendars/events/{eid}")
            return True
        except IntegrationError as exc:
            msg = str(exc).lower()
            if "404" in msg or "not found" in msg:
                return True
            logger.warning("GHL cancel event fallito id=%s: %s", eid, exc)
            return False


def ghl_duration_minutes_sara() -> int:
    raw = (os.getenv("GHL_APPOINTMENT_DURATION_MIN_SARA") or "30").strip()
    try:
        return max(15, int(raw))
    except ValueError:
        return 30


def ghl_buffer_minutes_sara() -> int:
    raw = (os.getenv("GHL_APPOINTMENT_BUFFER_MIN_SARA") or "10").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 10
