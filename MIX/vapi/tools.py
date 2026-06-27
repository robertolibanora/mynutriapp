# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""Tool handler Vapi: check_availability / book_appointment / schedule_callback.

Logica:
  * `check_availability(date)`  → calendario → lista Slot, popola state.proposed_slots
  * `book_appointment(...)`     → validazione server-side (porta da tool_guard.py:
                                  slot fra proposti, nome/telefono, business hours)
                                  → calendar.create_event + crm.update_outcome
                                  + (opzionale) whatsapp.send_confirmation + slack
  * `schedule_callback(...)`    → validazione (orari, futuro, max 30gg)
                                  → crm.enqueue con scheduled_at
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from datetime import date, datetime, time as dtime, timedelta
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Mapping, Optional

from app.config import (
    BUSINESS_HOURS_END,
    BUSINESS_HOURS_START,
    BUSINESS_TIMEZONE,
    canonical_agent_key,
    get_business_timezone,
    get_closer_list,
    load_agent_config,
    resolve_dispatcher_key,
)
from app.agencies import (
    get_agency,
    get_agency_citta,
    get_agency_whatsapp_group_jid,
    out_of_target_closing_script,
    resolve_agency_slug_for_client,
)
from app.formatting import (
    agency_info,
    agency_info_by_slug,
    format_appointment_it,
    format_appointment_page,
    parse_appointment_start,
    public_base_url,
)
from crm import crud
from crm.base import CRMProvider
from integrations.base import (
    CalendarProvider,
    SlackNotifier,
    Slot,
    WhatsAppProvider,
)
from integrations.calendar.db import slot_from_db_row
from integrations.sheets.sync import sync_client_to_sheet

logger = logging.getLogger(__name__)

_SET_OUTCOME_TOOL_MAP: dict[str, str] = {
    "non_interessato": "NON_INTERESSATO",
    "non_in_target": "NON_IN_TARGET",
    "da_richiamare": "RICHIAMARE",
}

_CLOSER_DISPLAY_NAMES: dict[str, str] = {
    "andrea-metta": "Andrea Metta",
    "andrea-pochini": "Andrea Pochini",
}

MAX_CALLBACK_FUTURE_DAYS: int = 30
MIN_CALLBACK_FUTURE_SECONDS: int = 30
SHORT_CALLBACK_MAX_SECONDS: int = 3 * 3600
MAX_DATES_PROPOSE: int = 3
MAX_TIMES_PROPOSE: int = 5


def _has_callback_schedule_args(args: Mapping[str, Any]) -> bool:
    for key in (
        "delay_minutes",
        "minuti",
        "minutes",
        "delay_seconds",
        "secondi",
        "seconds",
        "callback_datetime",
        "data_ora",
        "callback_date",
        "callback_time",
        "data",
        "ora",
    ):
        raw = args.get(key)
        if raw is not None and str(raw).strip() != "":
            return True
    return False


@dataclass(slots=True)
class ProposedSlot:
    """Slot proposto al cliente da check_availability."""

    start_iso: str
    hour_minute: str
    label: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def matches(self, slot_datetime: str = "") -> bool:
        sd = (slot_datetime or "").strip()
        if not sd:
            return False
        target_candidates = _expand_iso_prefixes(self.start_iso)
        candidate_candidates = _expand_iso_prefixes(sd)
        for c in candidate_candidates:
            for t in target_candidates:
                if c.startswith(t) or t.startswith(c):
                    return True
        return False


@dataclass(slots=True)
class ToolSessionState:
    """Stato in-memory per la sessione (keyed per provider_call_id)."""

    proposed_slots: list[ProposedSlot] = field(default_factory=list)
    confirmed_slot: Optional[ProposedSlot] = None


def _expand_iso_prefixes(iso_like: str) -> tuple[str, ...]:
    raw = (iso_like or "").strip()
    if not raw:
        return tuple()
    no_z = raw[:-1] if raw.endswith("Z") else raw
    variants: set[str] = {no_z, no_z.replace("T", " "), no_z.replace(" ", "T")}
    truncated: set[str] = set()
    for v in variants:
        if len(v) >= 16:
            truncated.add(v[:16])
        if len(v) >= 19:
            truncated.add(v[:19])
    return tuple(variants | truncated)


def _slot_voice_label(ps: ProposedSlot) -> str:
    """Etichetta italiana per l'agente: giorno, mese e ora esatti dal calendario."""
    giorno, ora = format_appointment_it(ps.start_iso)
    if ora:
        return f"{giorno} alle ore {ora}"
    return ps.label or giorno or ps.start_iso


def _slot_tool_param(ps: ProposedSlot) -> str:
    return f"slot_datetime={ps.start_iso}"


def _date_voice_label(date_iso: str) -> str:
    giorno, _ = format_appointment_it(f"{date_iso}T12:00:00")
    return giorno


def _build_dates_availability_response(dates: list[str]) -> str:
    picked = dates[:MAX_DATES_PROPOSE]
    voice = "; ".join(_date_voice_label(d) for d in picked)
    tool_params = "; ".join(f"date={d}" for d in picked)
    return (
        "FASE DATE — Proponi SOLO a voce le etichette italiane qui sotto "
        "(giorno + numero + mese; VIETATO leggere date=, numeri ISO o l'anno in inglese). "
        "Chiedi quale giorno preferisce (NON proporre ancora orari): "
        f"{voice}. "
        f"Parametri tool (NON leggere a voce): {tool_params}. "
        "Dopo la scelta richiama check_availability con date=YYYY-MM-DD."
    )


def _build_times_availability_response(
    date_iso: str,
    proposed: list[ProposedSlot],
    *,
    extra: str = "",
) -> str:
    giorno = _date_voice_label(date_iso)
    picked = proposed[:MAX_TIMES_PROPOSE]
    voice = " oppure ".join(_slot_voice_label(ps) for ps in picked)
    tool_params = "; ".join(_slot_tool_param(ps) for ps in picked)
    suffix = f" {extra}".rstrip()
    return (
        f"FASE ORARI per {giorno} — Proponi SOLO a voce gli orari italiani qui sotto "
        f"(VIETATO leggere slot_datetime= o date in inglese). Chiedi quale preferisce: "
        f"{voice}. "
        f"Parametri tool (NON leggere a voce): {tool_params}"
        f"{suffix}"
    )


async def _load_slots_for_date_gloria(
    date_iso: str,
    *,
    agent_key: str,
    calendar: Optional[CalendarProvider],
) -> list[Slot]:
    ak = canonical_agent_key(agent_key)
    db_slots = crud.list_slot_for_date(
        date_iso,
        solo_liberi=True,
        agent_key=ak,
        limit=MAX_TIMES_PROPOSE,
    )
    if db_slots:
        return [slot_from_db_row(row) for row in db_slots]
    if calendar is not None:
        try:
            return await calendar.get_free_slots(date_iso)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "check_availability: calendar.get_free_slots fallito: %s", exc
            )
    return []


async def _load_available_dates_gloria(
    from_date_iso: str,
    *,
    agent_key: str,
    calendar: Optional[CalendarProvider],
) -> list[str]:
    ak = canonical_agent_key(agent_key)
    dates = crud.list_distinct_free_dates(
        from_date_iso, agent_key=ak, limit=MAX_DATES_PROPOSE
    )
    if dates:
        return dates

    if calendar is None:
        return []

    tz = get_business_timezone()
    try:
        start_d = date.fromisoformat(from_date_iso)
    except ValueError:
        return []

    found: list[str] = []
    cur = start_d
    for _ in range(21):
        d_iso = cur.isoformat()
        day_slots = await _load_slots_for_date_gloria(
            d_iso, agent_key=ak, calendar=calendar
        )
        if day_slots:
            found.append(d_iso)
        if len(found) >= MAX_DATES_PROPOSE:
            break
        cur = cur + timedelta(days=1)
    return found


def parse_callback_datetime(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    candidates = (
        raw,
        raw.replace("Z", "+00:00"),
        raw.replace(" ", "T"),
        raw.replace(" ", "T").replace("Z", "+00:00"),
    )
    for c in candidates:
        try:
            dt = datetime.fromisoformat(c)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=get_business_timezone())
        return dt.astimezone(get_business_timezone())
    return None


def is_within_business_hours(
    dt: datetime,
    *,
    start_hour: int = BUSINESS_HOURS_START,
    end_hour: int = BUSINESS_HOURS_END,
) -> bool:
    tz = get_business_timezone()
    dt_local = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
    start = dtime(hour=start_hour, minute=0)
    end = dtime(hour=end_hour, minute=0)
    return start <= dt_local.time() < end


def _proposed_from_slots(slots: list[Slot]) -> list[ProposedSlot]:
    out: list[ProposedSlot] = []
    for s in slots or []:
        if not s.start_iso:
            continue
        try:
            dt = datetime.fromisoformat(s.start_iso.replace("Z", "+00:00"))
            tz = get_business_timezone()
            dt_local = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
            start_iso_local = dt_local.strftime("%Y-%m-%dT%H:%M:%S")
            hhmm = dt_local.strftime("%H:%M")
        except ValueError:
            start_iso_local = s.start_iso
            hhmm = s.start_iso[11:16] if len(s.start_iso) >= 16 else ""
        slot_raw: dict[str, Any] = {
            "start_iso": s.start_iso,
            "end_iso": s.end_iso,
        }
        if s.ref is not None:
            slot_raw["ref"] = s.ref
        if s.slot_id is not None:
            slot_raw["slot_id"] = s.slot_id
        elif s.ref is not None:
            try:
                slot_raw["slot_id"] = int(s.ref)
            except ValueError:
                pass
        out.append(
            ProposedSlot(
                start_iso=start_iso_local,
                hour_minute=hhmm,
                label=s.label,
                raw={"slot": slot_raw},
            )
        )
    return out


@dataclass(slots=True)
class GuardResult:
    ok: bool
    message: str
    code: str = ""
    target_slot: Optional[ProposedSlot] = None


def validate_book_appointment(
    args: Mapping[str, Any],
    *,
    state: ToolSessionState,
    requires_email: bool = False,
) -> GuardResult:
    if not state.proposed_slots:
        return GuardResult(
            ok=False,
            code="no_proposals",
            message=(
                "Non posso prenotare: nessuno slot e' stato proposto in "
                "questa chiamata. Chiama prima `check_availability`."
            ),
        )

    slot_dt_arg = str(args.get("slot_datetime", "")).strip()
    if not slot_dt_arg:
        return GuardResult(
            ok=False,
            code="missing_slot_datetime",
            message=(
                "Non posso prenotare: 'slot_datetime' mancante. "
                "Passa lo slot esatto fra quelli proposti."
            ),
        )

    target: Optional[ProposedSlot] = None
    for s in state.proposed_slots:
        if s.matches(slot_datetime=slot_dt_arg):
            target = s
            break
    if target is None:
        return GuardResult(
            ok=False,
            code="slot_not_in_proposals",
            message=(
                "Non posso prenotare: lo slot indicato non e' fra quelli "
                "proposti in questa chiamata. Riproponi e fatti confermare."
            ),
        )

    nome = str(args.get("nome", "")).strip()
    if not nome:
        return GuardResult(
            ok=False,
            code="missing_nome",
            message="Non posso prenotare: nome cliente mancante.",
            target_slot=target,
        )
    telefono = str(args.get("telefono", "")).strip()
    if not telefono:
        return GuardResult(
            ok=False,
            code="missing_telefono",
            message="Non posso prenotare: numero di telefono mancante.",
            target_slot=target,
        )

    if requires_email:
        email = str(args.get("email", "")).strip()
        if not email or "@" not in email:
            return GuardResult(
                ok=False,
                code="missing_email",
                message="Non posso prenotare: email mancante o non valida.",
                target_slot=target,
            )

    state.confirmed_slot = target
    return GuardResult(ok=True, code="ok", message="ok", target_slot=target)


def resolve_callback_datetime(
    args: Mapping[str, Any],
    *,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    tz = get_business_timezone()
    now_rome = (now or datetime.now(tz)).astimezone(tz)

    for key in ("delay_minutes", "minuti", "minutes"):
        raw = args.get(key)
        if raw is not None and str(raw).strip() != "":
            try:
                mins = int(float(str(raw).strip()))
            except (TypeError, ValueError):
                return None
            if mins < 1:
                mins = 1
            return now_rome + timedelta(minutes=mins)

    for key in ("delay_seconds", "secondi", "seconds"):
        raw = args.get(key)
        if raw is not None and str(raw).strip() != "":
            try:
                secs = int(float(str(raw).strip()))
            except (TypeError, ValueError):
                return None
            if secs < MIN_CALLBACK_FUTURE_SECONDS:
                secs = MIN_CALLBACK_FUTURE_SECONDS
            return now_rome + timedelta(seconds=secs)

    date_s = str(
        args.get("callback_date") or args.get("data") or ""
    ).strip()
    time_s = str(args.get("callback_time") or args.get("ora") or "").strip()
    if date_s and time_s:
        combined = f"{date_s}T{time_s}"
        if ":" not in time_s:
            combined = f"{date_s}T{time_s}:00"
        parsed = parse_callback_datetime(combined)
        if parsed is not None:
            return parsed

    cb_dt_str = str(
        args.get("callback_datetime") or args.get("data_ora") or ""
    ).strip()
    if not cb_dt_str:
        return None
    return parse_callback_datetime(cb_dt_str)


def validate_schedule_callback(
    args: Mapping[str, Any],
    *,
    business_start: int = BUSINESS_HOURS_START,
    business_end: int = BUSINESS_HOURS_END,
    now: Optional[datetime] = None,
) -> GuardResult:
    tz = get_business_timezone()
    now_rome = (now or datetime.now(tz)).astimezone(tz)
    cb_dt = resolve_callback_datetime(args, now=now_rome)
    if cb_dt is None:
        return GuardResult(
            ok=False,
            code="unparseable_datetime",
            message=(
                "Orario non ancora indicato: NON restare in silenzio. "
                "Chiedi a voce al cliente a che ora richiamare, poi richiama "
                "schedule_callback con delay_minutes o data_ora ISO."
            ),
        )

    delta = (cb_dt - now_rome).total_seconds()
    if delta < MIN_CALLBACK_FUTURE_SECONDS:
        return GuardResult(
            ok=False,
            code="not_in_future",
            message="L'orario indicato e' nel passato o troppo vicino.",
        )
    if cb_dt > now_rome + timedelta(days=MAX_CALLBACK_FUTURE_DAYS):
        return GuardResult(
            ok=False,
            code="too_far_in_future",
            message=(
                f"L'orario indicato e' oltre {MAX_CALLBACK_FUTURE_DAYS} giorni: "
                "probabilmente ho capito male."
            ),
        )
    if (
        delta > SHORT_CALLBACK_MAX_SECONDS
        and not is_within_business_hours(
            cb_dt, start_hour=business_start, end_hour=business_end
        )
    ):
        return GuardResult(
            ok=False,
            code="off_business_hours",
            message=(
                f"L'orario richiesto ({cb_dt.strftime('%H:%M')}) e' fuori "
                f"dagli orari operativi ({business_start:02d}:00-"
                f"{business_end:02d}:00 {BUSINESS_TIMEZONE})."
            ),
        )
    return GuardResult(
        ok=True,
        code="ok",
        message=cb_dt.isoformat(timespec="seconds"),
    )


async def schedule_agreed_callback_if_any(
    *,
    client_id: int,
    agent_key: str,
    transcript: str,
    today_date: str,
    get_dispatchers: Callable[[], Any] | None = None,
    source: str = "transcript",
) -> datetime | None:
    """Programma richiamo concordato se in transcript/summary c'è giorno+ora espliciti."""
    from telephony.vapi.callback_extraction import resolve_agreed_callback_datetime

    if crud.is_precise_callback_pending(int(client_id)):
        return None

    tz = get_business_timezone()
    when = await resolve_agreed_callback_datetime(transcript, today_date, tz)
    if when is None:
        return None

    guard = validate_schedule_callback(
        {"data_ora": when.isoformat(timespec="seconds")},
        now=datetime.now(tz),
    )
    if not guard.ok:
        logger.info(
            "schedule_agreed_callback: skip client_id=%s source=%s code=%s",
            client_id,
            source,
            guard.code,
        )
        return None

    scheduled_at = parse_callback_datetime(guard.message)
    if scheduled_at is None:
        return None

    qid = crud.schedule_precise_callback(int(client_id), agent_key, scheduled_at)
    if not qid:
        return None

    client = crud.get_client(int(client_id)) or {}
    if get_dispatchers is not None:
        _schedule_dispatcher_retry(
            get_dispatchers=get_dispatchers,
            agent_key=agent_key,
            client_id=int(client_id),
            telefono=str(client.get("telefono") or ""),
            nome=str(client.get("nome") or ""),
            when=scheduled_at,
        )

    logger.info(
        "schedule_agreed_callback: client_id=%s agent=%s at=%s source=%s queue_id=%s",
        client_id,
        agent_key,
        scheduled_at.isoformat(timespec="seconds"),
        source,
        qid,
    )
    return scheduled_at


ToolHandler = Callable[[Mapping[str, Any]], Awaitable[str]]

_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _slot_ref_from_proposed(target: ProposedSlot) -> Optional[str]:
    ref = target.raw.get("slot", {}).get("ref")
    if ref:
        return str(ref).strip() or None
    slot_id = target.raw.get("slot", {}).get("slot_id")
    if slot_id is not None:
        return str(slot_id)
    return None


def _resolve_booking_phone(
    args: Mapping[str, Any],
    client: Any,
    *,
    phone_field: str = "telefono",
    event: Mapping[str, Any] | None = None,
) -> str:
    phone = str(args.get("telefono") or getattr(client, "phone", "") or "").strip()
    if phone:
        return phone
    if event:
        meta = dict(event.get("metadata") or {})
        for key in ("customer_phone", "telefono", "phone"):
            ph = str(meta.get(key) or "").strip()
            if ph:
                return ph
    client_id = getattr(client, "id", None)
    if client_id is None:
        return ""
    raw = crud.get_client(int(client_id)) or {}
    return str(raw.get(phone_field) or raw.get("telefono") or "").strip()


def _whatsapp_delivery_ok(result: Any) -> bool:
    """True se Evolution (o provider) non ha segnalato errore nell'invio."""
    if result is None:
        return False
    if not isinstance(result, dict):
        return True
    if result.get("error"):
        return False
    err_msg = str(result.get("message") or "").strip().lower()
    if err_msg and any(
        x in err_msg for x in ("error", "fail", "invalid", "not found")
    ):
        return False
    return True


def _schedule_dispatcher_retry(
    *,
    get_dispatchers: Callable[[], Any],
    agent_key: str,
    client_id: int,
    telefono: str,
    nome: str,
    when: datetime,
) -> None:
    """Accoda nel dispatcher al momento scelto (non solo al poll ogni 30s)."""
    tz = get_business_timezone()
    when_local = when.astimezone(tz) if when.tzinfo else when.replace(tzinfo=tz)
    delay_s = max(0.0, (when_local - datetime.now(tz)).total_seconds())
    max_wake_s = float(MAX_CALLBACK_FUTURE_DAYS * 86400)
    if delay_s > max_wake_s:
        logger.info(
            "schedule_callback: wake asyncio skip client_id=%s delay=%.0fs (>max)",
            client_id,
            delay_s,
        )
        return

    qid = crud.get_pending_queue_id(client_id)
    payload: dict[str, Any] = {
        "client_id": client_id,
        "id": client_id,
        "telefono": telefono,
        "nome": nome,
        "precise_callback": True,
    }
    if qid is not None:
        payload["queue_id"] = qid

    async def _wake() -> None:
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        try:
            dispatchers = get_dispatchers() or {}
            lookup_key = resolve_dispatcher_key(agent_key, dispatchers)
            disp = (
                dispatchers.get(lookup_key)
                if isinstance(dispatchers, dict)
                else dispatchers
            )
            if disp is not None:
                await disp.enqueue(payload)
                logger.info(
                    "schedule_callback: dispatcher accodato client_id=%s tra %.0fs",
                    client_id,
                    delay_s,
                )
        except Exception:  # noqa: BLE001
            logger.exception(
                "schedule_callback: dispatcher wake fallito client_id=%s",
                client_id,
            )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_wake(), name=f"callback-wake-{client_id}")
    except RuntimeError:
        logger.warning(
            "schedule_callback: nessun event loop per wake client_id=%s",
            client_id,
        )


def _extract_date_iso(args: Mapping[str, Any]) -> Optional[str]:
    for key in ("date", "data", "date_iso", "giorno"):
        v = str(args.get(key) or "").strip()
        if v:
            m = _DATE_RE.search(v)
            if m:
                return m.group(1)
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00")).date().isoformat()
            except ValueError:
                continue
    return None


def _default_closer_slug() -> str:
    slug = (os.getenv("DEFAULT_CLOSER_SARA") or "andrea-metta").strip().lower()
    return slug if slug in _CLOSER_DISPLAY_NAMES else "andrea-metta"


def _closer_display_name(slug: str) -> str:
    s = (slug or "").strip().lower()
    return _CLOSER_DISPLAY_NAMES.get(s, slug.replace("-", " ").title())


def _proposed_from_round_robin_slot(slot: Mapping[str, Any]) -> ProposedSlot:
    inizio = slot.get("inizio")
    if isinstance(inizio, datetime):
        tz = get_business_timezone()
        dt_local = inizio.astimezone(tz) if inizio.tzinfo else inizio.replace(tzinfo=tz)
        start_iso = dt_local.strftime("%Y-%m-%dT%H:%M:%S")
        hhmm = dt_local.strftime("%H:%M")
        giorno, ora = format_appointment_it(start_iso)
        label = f"{giorno} alle ore {ora}" if ora else giorno
    else:
        start_iso = str(inizio or "")
        hhmm = start_iso[11:16] if len(start_iso) >= 16 else ""
        label = start_iso
    closer_key = str(slot.get("closer_key") or "").strip().lower()
    closer_nome = str(slot.get("closer_nome") or "").strip()
    slot_id = slot.get("slot_id")
    slot_raw: dict[str, Any] = {
        "start_iso": start_iso,
        "end_iso": "",
        "closer_key": closer_key,
        "closer_nome": closer_nome,
    }
    if slot_id is not None:
        slot_raw["slot_id"] = int(slot_id)
        slot_raw["ref"] = str(slot_id)
    ghl_cal = str(slot.get("ghl_calendar_id") or "").strip()
    if ghl_cal:
        slot_raw["ghl_calendar_id"] = ghl_cal
        if not slot_raw.get("ref"):
            slot_raw["ref"] = f"{ghl_cal}:{start_iso}"
    if slot.get("fine"):
        fine = slot.get("fine")
        if isinstance(fine, datetime):
            tz = get_business_timezone()
            fine_local = fine.astimezone(tz) if fine.tzinfo else fine.replace(tzinfo=tz)
            slot_raw["end_iso"] = fine_local.strftime("%Y-%m-%dT%H:%M:%S")
    return ProposedSlot(
        start_iso=start_iso,
        hour_minute=hhmm,
        label=label,
        raw={"slot": slot_raw, "closer_key": closer_key, "closer_nome": closer_nome},
    )


def _closer_from_proposed(target: ProposedSlot) -> tuple[str, str]:
    closer_key = str(
        target.raw.get("closer_key")
        or target.raw.get("slot", {}).get("closer_key")
        or ""
    ).strip().lower()
    closer_nome = str(
        target.raw.get("closer_nome")
        or target.raw.get("slot", {}).get("closer_nome")
        or ""
    ).strip()
    if closer_key and not closer_nome:
        closer_nome = _closer_display_name(closer_key)
    return closer_key, closer_nome


async def _handle_check_availability_sara(
    args: Mapping[str, Any],
    state: ToolSessionState,
    agent_key: str,
    calendar: Optional[CalendarProvider] = None,
) -> str:
    """Disponibilità GHL: prima le date, poi gli orari per il giorno scelto."""
    from integrations.calendar.ghl import GHLCalendar

    ak = canonical_agent_key(agent_key)
    closers = get_closer_list(ak)
    if not closers:
        return "Configurazione closer mancante: impossibile verificare disponibilità."

    if not isinstance(calendar, GHLCalendar):
        return (
            "Calendario GoHighLevel non configurato: impossibile verificare disponibilità."
        )

    tz = get_business_timezone()
    now = datetime.now(tz)
    date_iso = _extract_date_iso(args)

    try:
        if not date_iso:
            available_dates = await calendar.find_round_robin_available_dates(
                closers, now, max_dates=MAX_DATES_PROPOSE
            )
            if not available_dates:
                logger.info("check_availability: nessuna data GHL agent=%s", ak)
                return (
                    "Non ho slot disponibili nei prossimi giorni. "
                    "Di' al cliente: «Non ho slot disponibili nei prossimi giorni, "
                    "la richiamo io appena si libera qualcosa». "
                    "Poi chiama set_outcome con outcome=da_richiamare IN SILENZIO."
                )
            state.proposed_slots = []
            parts = [
                (
                    f"{_date_voice_label(item['date_iso'])} "
                    f"(date={item['date_iso']})"
                )
                for item in available_dates
            ]
            logger.info(
                "check_availability: date GHL agent=%s n=%s",
                ak,
                len(available_dates),
            )
            return (
                "FASE DATE — Proponi questi giorni per la video riunione e chiedi "
                "quale preferisce (NON proporre ancora orari): "
                + "; ".join(parts)
                + ". Dopo la scelta richiama check_availability con date=YYYY-MM-DD."
            )

        day_slots = await calendar.find_round_robin_slots_for_date(
            closers,
            date_iso,
            from_dt=now,
            limit=MAX_TIMES_PROPOSE,
        )
        if not day_slots:
            logger.info(
                "check_availability: nessuno slot GHL agent=%s date=%s",
                ak,
                date_iso,
            )
            return (
                f"Nessuno slot libero il {date_iso}. "
                "Chiedi un altro giorno e richiama check_availability senza date "
                "oppure con un'altra date=YYYY-MM-DD."
            )

        proposed = [_proposed_from_round_robin_slot(s) for s in day_slots]
        state.proposed_slots = proposed
        logger.info(
            "check_availability: orari GHL agent=%s date=%s n=%s closer=%s",
            ak,
            date_iso,
            len(proposed),
            day_slots[0].get("closer_key"),
        )
        return _build_times_availability_response(
            date_iso,
            proposed,
            extra=(
                "Video riunione Google Meet con un consulente Evolution Media. "
                "NON comunicare nomi di closer al cliente."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("check_availability GHL fallito: %s", exc)
        return "Errore nel recuperare la disponibilità da GoHighLevel."


async def prefetch_sara_available_days(
    agent_key: str = "sara",
) -> tuple[str, str]:
    """Precarica giorni GHL per variableValues (evita stall post-pitch su tool)."""
    from integrations.calendar.ghl import GHLCalendar
    from integrations.factory import build_calendar

    ak = canonical_agent_key(agent_key)
    closers = get_closer_list(ak)
    if not closers:
        return "", ""
    calendar = build_calendar(ak)
    if not isinstance(calendar, GHLCalendar):
        return "", ""
    tz = get_business_timezone()
    now = datetime.now(tz)
    try:
        available_dates = await calendar.find_round_robin_available_dates(
            closers, now, max_dates=MAX_DATES_PROPOSE
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("prefetch_sara_available_days fallito agent=%s: %s", ak, exc)
        return "", ""
    if not available_dates:
        return "", ""
    voice_parts = [
        _date_voice_label(item["date_iso"]) for item in available_dates
    ]
    iso_parts = [f"date={item['date_iso']}" for item in available_dates]
    voice = ", ".join(voice_parts)
    tool_hint = "; ".join(iso_parts)
    logger.info(
        "prefetch_sara_available_days agent=%s n=%s voice=%s",
        ak,
        len(available_dates),
        voice,
    )
    return voice, tool_hint


def _cancel_confirm_truthy(args: Mapping[str, Any]) -> bool:
    raw = args.get("conferma")
    if raw is None:
        raw = args.get("confermato")
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {
        "sì",
        "si",
        "true",
        "1",
        "yes",
        "confermo",
        "conferma",
    }


def _pick_appointment_for_cancel(
    appts: list[dict[str, Any]],
    args: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    if not appts:
        return None, "Non risulta alcun appuntamento futuro da annullare."

    appt_id_raw = args.get("appointment_id")
    if appt_id_raw is not None and str(appt_id_raw).strip() != "":
        try:
            target_id = int(appt_id_raw)
        except (TypeError, ValueError):
            return None, "appointment_id non valido."
        for appt in appts:
            if int(appt.get("id") or 0) == target_id:
                return appt, ""
        return None, "Nessun appuntamento futuro con quell'ID per questo cliente."

    slot_dt = str(
        args.get("slot_datetime") or args.get("data_ora") or ""
    ).strip()
    if slot_dt:
        prefixes = _expand_iso_prefixes(slot_dt)
        for appt in appts:
            start_local = crud._appointment_start_local(appt)
            if start_local is None:
                continue
            start_iso = start_local.strftime("%Y-%m-%dT%H:%M:%S")
            start_candidates = _expand_iso_prefixes(start_iso)
            if any(
                c.startswith(t) or t.startswith(c)
                for c in prefixes
                for t in start_candidates
            ):
                return appt, ""

    if len(appts) == 1:
        return appts[0], ""

    parts: list[str] = []
    for appt in appts:
        giorno, ora = format_appointment_it(appt.get("start_time"))
        label = f"{giorno} alle ore {ora}" if ora else giorno
        parts.append(f"{label} (appointment_id={appt.get('id')})")
    return (
        None,
        "Più appuntamenti futuri — chiedi quale annullare, poi richiama "
        "cancel_appointment con appointment_id: "
        + "; ".join(parts),
    )


async def _free_upcoming_appointments_for_client(
    client_id: int,
    calendar: Optional[CalendarProvider],
    *,
    agent_key: str,
) -> list[int]:
    """Annulla appuntamenti futuri del cliente e libera slot/calendario precedenti."""
    appts = crud.list_upcoming_appointments_for_client(client_id, limit=10)
    if not appts:
        return []

    cancelled_ids: list[int] = []
    for appt in appts:
        appt_id = int(appt.get("id") or 0)
        if not appt_id:
            continue
        await _delete_external_calendar_event(appt, calendar, agent_key=agent_key)
        if crud.delete_appointment(appt_id):
            cancelled_ids.append(appt_id)

    if cancelled_ids:
        logger.info(
            "appuntamenti liberati prima di nuovo booking client_id=%s ids=%s agent=%s",
            client_id,
            cancelled_ids,
            agent_key,
        )
    return cancelled_ids


async def _delete_external_calendar_event(
    appt: Mapping[str, Any],
    calendar: Optional[CalendarProvider],
    *,
    agent_key: str,
) -> None:
    from integrations.calendar.db_with_mirror import DBWithGoogleMirror
    from integrations.calendar.ghl import GHLCalendar
    from integrations.calendar.google import GoogleCalendar
    from integrations.calendar.google_sync import is_google_event_synced

    ext = str(appt.get("external_event_id") or "").strip()
    if not ext:
        return

    ak = canonical_agent_key(agent_key)
    if ak == "sara" and isinstance(calendar, GHLCalendar):
        try:
            await calendar.cancel_event(ext)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cancel_appointment: GHL cancel fallito: %s", exc)
        return

    if not is_google_event_synced(ext):
        return

    google: GoogleCalendar | None = None
    if isinstance(calendar, DBWithGoogleMirror):
        google = calendar.google if isinstance(calendar.google, GoogleCalendar) else None
    elif isinstance(calendar, GoogleCalendar):
        google = calendar

    if google is None:
        return
    try:
        await google.delete_event(ext)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cancel_appointment: Google delete fallito: %s", exc)


async def _handle_cancel_appointment(
    args: Mapping[str, Any],
    state: ToolSessionState,
    provider_call_id: str,
    calendar: Optional[CalendarProvider],
    *,
    agent_key: str,
) -> str:
    row_call = crud.get_call_by_sid_raw(provider_call_id)
    client_id: int | None = (
        int(row_call["client_id"])
        if row_call and row_call.get("client_id") is not None
        else None
    )

    if client_id is None:
        telefono_arg = str(args.get("telefono") or "").strip()
        if telefono_arg:
            raw_phone = crud.get_client_by_phone_for_agent(telefono_arg, agent_key)
            if raw_phone and raw_phone.get("id") is not None:
                client_id = int(raw_phone["id"])

    if client_id is None:
        return (
            "Non riesco a identificare il cliente di questa chiamata. "
            "Passa telefono={{customer_phone}} se disponibile."
        )

    try:
        crud.assert_client_agent_scope(
            client_id, agent_key, context="cancel_appointment"
        )
    except ValueError as exc:
        return str(exc)

    appts = crud.list_upcoming_appointments_for_client(client_id)
    target, pick_msg = _pick_appointment_for_cancel(appts, args)
    if target is None:
        return pick_msg

    giorno, ora = format_appointment_it(target.get("start_time"))
    when_label = f"{giorno} alle ore {ora}" if ora else giorno

    if not _cancel_confirm_truthy(args):
        return (
            f"Prima di annullare chiedi conferma esplicita per: {when_label}. "
            "Poi richiama cancel_appointment con conferma=true "
            f"(appointment_id={target.get('id')})."
        )

    appt_id = int(target["id"])
    await _delete_external_calendar_event(target, calendar, agent_key=agent_key)

    if not crud.delete_appointment(appt_id):
        return "Errore tecnico nell'annullamento dell'appuntamento."

    state.proposed_slots = []
    state.confirmed_slot = None

    logger.info(
        "cancel_appointment: ok appt_id=%s client_id=%s agent=%s",
        appt_id,
        client_id,
        agent_key,
    )
    return (
        f"Appuntamento annullato: {when_label}. "
        "Lo slot precedente è di nuovo disponibile in agenda. "
        "Comunica al cliente che l'appuntamento è stato eliminato."
    )


def build_tool_handler(
    *,
    crm: CRMProvider,
    calendars: dict[str, Optional[CalendarProvider]],
    whatsapps: dict[str, Optional[WhatsAppProvider]] | None = None,
    slack: Optional[SlackNotifier] = None,
    slacks: dict[str, Optional[SlackNotifier]] | None = None,
    sheet_writers: dict[str, Optional[Any]] | None = None,
    get_dispatchers: Callable[[], Any] | None = None,
) -> ToolHandler:
    whatsapps = whatsapps or {}
    slacks_map = slacks or {}
    sheet_writers_map = sheet_writers or {}
    sessions: dict[str, ToolSessionState] = {}

    def _slack_for(ak: str) -> Optional[SlackNotifier]:
        key = canonical_agent_key(ak)
        if slacks_map.get(key) is not None:
            return slacks_map.get(key)
        return slack

    async def _reject_out_of_target(
        client_id: int,
        provider_call_id: str,
        agent_key: str,
        *,
        row_call: Mapping[str, Any] | None = None,
    ) -> str:
        agency_slug = resolve_agency_slug_for_client(
            client_id=client_id,
            agent_key=agent_key,
        )
        crud.apply_zone_target_status(client_id, call_sid=provider_call_id)
        try:
            crud.cancel_outbound_queue_for_client(client_id, status="cancelled")
        except Exception as exc:  # noqa: BLE001
            logger.warning("reject_out_of_target: cancel queue fallito: %s", exc)
        rc = row_call or crud.get_call_by_sid(provider_call_id)
        await sync_client_to_sheet(
            sheet_writers_map,
            agent_key,
            client_id,
            call_row=rc,
        )
        return out_of_target_closing_script(agency_slug)

    def _state_for(call_id: str) -> ToolSessionState:
        st = sessions.get(call_id)
        if st is None:
            st = ToolSessionState()
            sessions[call_id] = st
        return st

    def _integrations_for_event(
        event: Mapping[str, Any],
    ) -> tuple[str, Optional[CalendarProvider], Optional[WhatsAppProvider]]:
        metadata = dict(event.get("metadata") or {})
        agent_key = canonical_agent_key(
            str(metadata.get("agent_key") or "gloria").strip().lower() or "gloria"
        )
        provider_call_id = str(event.get("provider_call_id") or "").strip()
        if provider_call_id:
            call_row = crud.get_call_by_sid(provider_call_id)
            if call_row and call_row.get("agent_key"):
                agent_key = canonical_agent_key(str(call_row["agent_key"]))
        calendar = calendars.get(agent_key)
        # Mai incrociare calendari Gloria/Sara: provider e credenziali distinti.
        if calendar is None and agent_key not in ("gloria", "sara"):
            calendar = calendars.get("gloria")
        whatsapp = whatsapps.get(agent_key)
        if whatsapp is None and agent_key != "sara":
            whatsapp = whatsapps.get("gloria")
        return agent_key, calendar, whatsapp

    async def _enqueue_precise_callback(
        args: Mapping[str, Any],
        provider_call_id: str,
        agent_key: str,
        *,
        record_outcome: bool = True,
    ) -> str:
        guard = validate_schedule_callback(args)
        if not guard.ok:
            return guard.message

        client = crm.get_client_by_call(provider_call_id)
        if client is None or client.id is None:
            return "Non riesco a identificare il cliente di questa chiamata."

        note_call = str(args.get("note_call") or "").strip()
        if note_call:
            try:
                crud.update_client(int(client.id), note_call=note_call)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "schedule_callback: note_call fallito: %s", exc
                )

        scheduled_at = parse_callback_datetime(guard.message)
        if scheduled_at is None:
            return "Errore nel calcolo dell'orario di richiamo."

        try:
            crud.schedule_precise_callback(
                int(client.id),
                agent_key,
                scheduled_at,
                note_call=note_call or None,
            )
            if record_outcome:
                cb_iso = scheduled_at.isoformat(timespec="seconds")
                crm.update_outcome(
                    provider_call_id,
                    outcome="RICHIAMARE",
                    extra={"next_attempt_at": cb_iso},
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("enqueue_precise_callback fallito: %s", exc)
            return "Errore tecnico nel programmare la richiamata."

        if get_dispatchers is not None:
            _schedule_dispatcher_retry(
                get_dispatchers=get_dispatchers,
                agent_key=agent_key,
                client_id=int(client.id),
                telefono=str(getattr(client, "phone", None) or ""),
                nome=str(getattr(client, "name", None) or ""),
                when=scheduled_at,
            )

        if record_outcome:
            try:
                await sync_client_to_sheet(
                    sheet_writers_map,
                    agent_key,
                    int(client.id),
                    call_row=crud.get_call_by_sid(provider_call_id),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "schedule_callback: sheet sync fallito client_id=%s: %s",
                    client.id,
                    exc,
                )

        giorno, ora = format_appointment_it(scheduled_at.isoformat())
        when_label = f"{giorno} alle {ora}" if ora else giorno
        return f"Richiamo pianificato per {when_label}."

    async def _handle_check_availability(
        args: Mapping[str, Any],
        state: ToolSessionState,
        calendar: Optional[CalendarProvider],
        agent_key: str,
    ) -> str:
        ak = canonical_agent_key(agent_key)
        if ak == "sara":
            return await _handle_check_availability_sara(
                args, state, agent_key, calendar
            )

        tz = get_business_timezone()
        now = datetime.now(tz)
        from_date = now.strftime("%Y-%m-%d")
        date_iso = _extract_date_iso(args)

        if not date_iso:
            dates = await _load_available_dates_gloria(
                from_date, agent_key=ak, calendar=calendar
            )
            if not dates:
                logger.info(
                    "check_availability: nessuna data Gloria agent=%s", ak
                )
                return (
                    "Non ho slot disponibili nei prossimi giorni. "
                    "Di' al cliente che la richiamerete appena si libera un posto "
                    "oppure usa schedule_callback se indica un momento per il richiamo."
                )
            state.proposed_slots = []
            logger.info(
                "check_availability: date Gloria agent=%s n=%s",
                ak,
                len(dates),
            )
            return _build_dates_availability_response(dates)

        slots = await _load_slots_for_date_gloria(
            date_iso, agent_key=ak, calendar=calendar
        )
        if not slots:
            other_dates = await _load_available_dates_gloria(
                from_date, agent_key=ak, calendar=calendar
            )
            other_dates = [d for d in other_dates if d != date_iso]
            logger.info(
                "check_availability: nessuno slot Gloria date=%s agent=%s",
                date_iso,
                ak,
            )
            if other_dates:
                return (
                    f"Nessuno slot libero il {_date_voice_label(date_iso)}. "
                    + _build_dates_availability_response(other_dates)
                )
            return (
                f"Nessuno slot libero il {date_iso}. "
                "Chiedi un altro giorno e richiama check_availability senza date "
                "oppure con un'altra date=YYYY-MM-DD."
            )

        proposed = _proposed_from_slots(slots)
        state.proposed_slots = proposed
        logger.info(
            "check_availability: orari Gloria date=%s agent=%s n=%s",
            date_iso,
            ak,
            len(proposed),
        )
        return _build_times_availability_response(date_iso, proposed)

    async def _handle_book_appointment(
        args: Mapping[str, Any],
        state: ToolSessionState,
        provider_call_id: str,
        calendar: Optional[CalendarProvider],
        whatsapp: Optional[WhatsAppProvider],
        *,
        agent_key: str,
        slack_notifier: Optional[SlackNotifier] = None,
        event: Mapping[str, Any] | None = None,
    ) -> str:
        requires_email = agent_key == "sara"

        client = crm.get_client_by_call(provider_call_id)

        if client is None or client.id is None:
            telefono_arg = str(args.get("telefono") or "").strip()
            if telefono_arg:
                raw_phone = crud.get_client_by_phone_for_agent(
                    telefono_arg,
                    agent_key,
                )
                if raw_phone:
                    client = SimpleNamespace(
                        id=int(raw_phone["id"]),
                        name=str(raw_phone.get("nome") or ""),
                        phone=str(raw_phone.get("telefono") or telefono_arg),
                    )

        agent_cfg = load_agent_config().get(agent_key) or {}
        phone_field = str(agent_cfg.get("whatsapp_number_field") or "telefono")
        args_effective = dict(args)
        resolved_phone = _resolve_booking_phone(
            args_effective,
            client,
            phone_field=phone_field,
            event=event,
        )
        if resolved_phone and not str(args_effective.get("telefono") or "").strip():
            args_effective["telefono"] = resolved_phone

        guard = validate_book_appointment(
            args_effective, state=state, requires_email=requires_email
        )
        if not guard.ok:
            return guard.message

        if canonical_agent_key(agent_key) != "sara" and client is not None and client.id is not None:
            if crud.is_location_out_of_target_for_client(int(client.id)):
                return await _reject_out_of_target(
                    int(client.id),
                    provider_call_id,
                    agent_key,
                    row_call=crud.get_call_by_sid(provider_call_id),
                )

        target = guard.target_slot
        assert target is not None

        slot_meta_pre = dict(target.raw.get("slot") or {})
        slot_id_pre = slot_meta_pre.get("slot_id")
        if canonical_agent_key(agent_key) != "sara" and slot_id_pre is None:
            return (
                "Non posso prenotare: lo slot non corrisponde a un orario configurato "
                "in agenda. Chiama check_availability e proponi solo slot dal sistema."
            )

        if client is not None and client.id is not None:
            row_pre = crud.get_client(int(client.id)) or {}
            if requires_email:
                missing_pre = crud.missing_sara_qualification_fields(row_pre)
            elif canonical_agent_key(agent_key) == "gloria":
                missing_pre = crud.missing_gloria_qualification_fields(row_pre)
            else:
                missing_pre = []
            if missing_pre:
                return (
                    "Non posso prenotare: dati mancanti in anagrafica. "
                    f"Usa save_profile per: {', '.join(missing_pre)}. "
                    "Poi richiama book_appointment."
                )

        email_arg = str(args_effective.get("email") or "").strip() or None

        if client is None or client.id is None:
            nome_arg = str(args_effective.get("nome") or "").strip() or "(sconosciuto)"
            telefono_arg = str(args_effective.get("telefono") or "").strip()
            if not telefono_arg:
                return "Non posso prenotare: numero di telefono mancante."
            try:
                new_cid = crud.create_client(
                    nome=nome_arg,
                    telefono=telefono_arg,
                    email=email_arg,
                    agent_key=agent_key,
                    source="vapi_inbound",
                    stato="appuntamento_fissato",
                )
                raw = crud.get_client(new_cid)
                client = SimpleNamespace(
                    id=new_cid,
                    name=(raw or {}).get("nome", nome_arg),
                    phone=(raw or {}).get("telefono", telefono_arg),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("book_appointment: create_client fallito: %s", exc)
                return "Errore tecnico nel registrare il cliente."

        if email_arg and client.id is not None:
            try:
                crud.update_client(int(client.id), email=email_arg)
            except Exception as exc:  # noqa: BLE001
                logger.warning("book_appointment: update email fallito: %s", exc)

        if client.id is not None:
            await _free_upcoming_appointments_for_client(
                int(client.id),
                calendar,
                agent_key=agent_key,
            )
            state.proposed_slots = []
            state.confirmed_slot = None

        slot_meta = dict(target.raw.get("slot") or {})
        slot_ref = _slot_ref_from_proposed(target)
        slot_id_raw = slot_meta.get("slot_id")
        slot_obj = Slot(
            start_iso=slot_meta.get("start_iso") or target.start_iso,
            end_iso=slot_meta.get("end_iso") or "",
            label=target.label,
            ref=slot_ref,
            slot_id=int(slot_id_raw) if slot_id_raw is not None else None,
        )
        row_call = crud.get_call_by_sid(provider_call_id)
        call_pk = int(row_call["id"]) if row_call and row_call.get("id") is not None else None

        agency_slug = ""
        if client.id is not None:
            agency_slug = resolve_agency_slug_for_client(
                client_id=int(client.id),
                agent_key=agent_key,
            )
        agency = (
            agency_info_by_slug(agency_slug)
            if agency_slug
            else agency_info(agent_key)
        )
        titolare_agenzia = str(agency.get("titolare") or "").strip()
        is_gloria = canonical_agent_key(agent_key) != "sara"
        gloria_assignee = titolare_agenzia if is_gloria and titolare_agenzia else ""

        start_time = str(
            args_effective.get("slot_datetime") or target.start_iso
        ).strip()
        event_result: dict[str, Any] = {}
        appt_info: dict[str, Any] | None = None
        used_db_slot = False

        if (
            slot_obj.slot_id is not None
            and canonical_agent_key(agent_key) != "sara"
        ):
            closer_key, closer_nome = _closer_from_proposed(target)
            try:
                result_slot = crud.book_slot_for_client(
                    slot_id=slot_obj.slot_id,
                    client_id=int(client.id),
                    call_id=call_pk,
                    assigned_to=gloria_assignee or closer_nome or agent_key,
                    closer_key=closer_key or None,
                    note=f"Prenotato via agente vocale {agent_key}",
                )
                if result_slot:
                    used_db_slot = True
                    appt_info = dict(result_slot)
            except Exception as exc:  # noqa: BLE001
                logger.warning("book_slot_for_client fallito: %s", exc)

        if calendar is not None:
            try:
                if used_db_slot:
                    from integrations.calendar.db_with_mirror import DBWithGoogleMirror

                    if (
                        isinstance(calendar, DBWithGoogleMirror)
                        and calendar.google is not None
                    ):
                        event_result = await calendar.google.create_event(
                            nome=str(args_effective.get("nome") or client.name or ""),
                            telefono=str(args_effective.get("telefono") or ""),
                            email=str(args_effective.get("email") or "") or None,
                            slot=slot_obj,
                            client_id=int(client.id),
                            call_id=call_pk,
                            slot_id=slot_obj.slot_id,
                            agent_key=agent_key,
                        )
                    else:
                        event_result = {
                            "event_id": str(slot_obj.slot_id),
                            "slot_dt": slot_obj.start_iso,
                        }
                else:
                    closer_key_ev, _ = _closer_from_proposed(target)
                    ghl_cal_id = str(slot_meta.get("ghl_calendar_id") or "").strip()
                    event_result = await calendar.create_event(
                        nome=str(args_effective.get("nome") or client.name or ""),
                        telefono=str(args_effective.get("telefono") or ""),
                        email=str(args_effective.get("email") or "") or None,
                        slot=slot_obj,
                        client_id=int(client.id),
                        call_id=call_pk,
                        slot_id=slot_obj.slot_id,
                        agent_key=agent_key,
                        closer_key=closer_key_ev or None,
                        ghl_calendar_id=ghl_cal_id or None,
                    )
            except Exception as exc:  # noqa: BLE001
                if not used_db_slot:
                    logger.exception("book_appointment: create_event fallito: %s", exc)
                    err = str(exc).lower()
                    if "senza permessi" in err or "not authorized for this scope" in err:
                        return (
                            "Errore configurazione GoHighLevel: il token non ha permesso "
                            "di creare contatti/appuntamenti. L'appuntamento NON è stato "
                            "fissato su GHL. Verifica gli scope del Private Integration."
                        )
                    return "Errore tecnico nel creare l'evento sul calendario."
                logger.warning(
                    "book_appointment: sync calendario dopo book_slot fallito: %s", exc
                )
        elif not used_db_slot:
            return "Calendario non configurato: non posso prenotare l'appuntamento."

        if appt_info is None and client.id is not None:
            closer_key_appt, _ = _closer_from_proposed(target)
            try:
                appt_info = crud.create_appointment(
                    int(client.id),
                    start_time=start_time,
                    call_id=call_pk,
                    end_time=slot_obj.end_iso or None,
                    provider=agent_key,
                    external_event_id=str(
                        event_result.get("google_event_id")
                        or event_result.get("event_id")
                        or ""
                    ),
                    meet_url=event_result.get("meet_link") or None,
                    assigned_to=gloria_assignee or closer_key_appt or agent_key,
                    closer_key=closer_key_appt or None,
                    note=f"Prenotato via agente vocale {agent_key}",
                    status="confirmed",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("create_appointment fallito: %s", exc)

        if appt_info and appt_info.get("id") and event_result:
            from integrations.calendar.google_sync import is_google_event_synced

            appt_patch: dict[str, Any] = {}
            gid = str(
                event_result.get("google_event_id")
                or event_result.get("event_id")
                or ""
            ).strip()
            meet_link = str(event_result.get("meet_link") or "").strip()
            if gid and is_google_event_synced(gid):
                appt_patch["external_event_id"] = gid
            if meet_link:
                appt_patch["meet_url"] = meet_link
            if appt_patch:
                try:
                    crud.update_appointment(int(appt_info["id"]), **appt_patch)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "update_appointment google sync fallito: %s", exc
                    )

        public_token = str((appt_info or {}).get("public_token") or "").strip()
        public_base = public_base_url()
        public_url = (
            f"{public_base}/appointment/{public_token}"
            if public_base and public_token
            else ""
        )
        appt_start = (appt_info or {}).get("start_time") or start_time
        slot_page_label = format_appointment_page(appt_start)
        giorno_label, ora_label = format_appointment_it(appt_start)
        meet_link = str(
            event_result.get("meet_link")
            or (appt_info or {}).get("meet_url")
            or ""
        ).strip()
        client_name = (
            (client.name if client else None) or str(args_effective.get("nome") or "")
        )
        client_phone = _resolve_booking_phone(
            args_effective,
            client,
            phone_field=phone_field,
            event=event,
        )
        slot_notify_label = slot_page_label or (slot_obj.label or target.start_iso)

        if slack_notifier is not None:
            try:
                await slack_notifier.notify_appointment(
                    agent_key=agent_key,
                    client_name=client_name,
                    client_phone=client_phone,
                    slot_label=slot_notify_label,
                    meet_link=meet_link or None,
                    call_id=provider_call_id,
                    public_url=public_url or None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Slack notify fallito (non bloccante): %s", exc)

        group_jid = get_agency_whatsapp_group_jid(agency_slug) if agency_slug else ""
        notify_group = getattr(whatsapp, "notify_appointment_to_group", None)
        if group_jid and whatsapp is not None and callable(notify_group):
            try:
                group_result = await notify_group(
                    group_jid=group_jid,
                    agency_name=agency["name"],
                    client_name=client_name,
                    client_phone=client_phone,
                    slot_label=slot_notify_label,
                    public_url=public_url or None,
                    meet_link=meet_link or None,
                )
                if not _whatsapp_delivery_ok(group_result):
                    logger.warning(
                        "book_appointment: WhatsApp gruppo fallito agency=%s jid=%s err=%s",
                        agency_slug,
                        group_jid,
                        (group_result or {}).get("error")
                        if isinstance(group_result, dict)
                        else group_result,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "book_appointment: WhatsApp gruppo eccezione agency=%s: %s",
                    agency_slug,
                    exc,
                )
        elif agency_slug and not group_jid:
            logger.info(
                "book_appointment: nessun WA_GROUP_JID per agency=%s, skip gruppo",
                agency_slug,
            )

        try:
            crm.update_outcome(
                provider_call_id,
                outcome="APPUNTAMENTO",
                extra={
                    "slot_dt": event_result.get("slot_dt") or start_time,
                    "event_id": event_result.get("event_id"),
                    "meet_link": meet_link or None,
                    "html_link": event_result.get("html_link"),
                    "public_url": public_url or None,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("book_appointment: crm.update_outcome fallito: %s", exc)

        if client.id is not None:
            try:
                crud.cancel_outbound_queue_for_client(int(client.id))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "book_appointment: cancel_outbound_queue fallito: %s", exc
                )

        if client.id is not None:
            sheet_extra: dict[str, Any] = {}
            dt_appt = parse_appointment_start(
                appt_start or target.start_iso or start_time
            )
            if dt_appt is not None:
                sheet_extra["data_appuntamento"] = dt_appt.strftime("%Y-%m-%d")
                sheet_extra["ora_appuntamento"] = dt_appt.strftime("%H:%M")
                sheet_extra["esito_chiamata"] = "Appuntamento"
            if canonical_agent_key(agent_key) == "sara":
                closer_slug, closer_nome = _closer_from_proposed(target)
                if not closer_slug:
                    closer_slug = _default_closer_slug()
                    closer_nome = _closer_display_name(closer_slug)
                sheet_extra["closer_assegnato"] = closer_nome
                try:
                    crud.update_client(int(client.id), closer_nome=closer_nome)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("book_appointment: closer_nome fallito: %s", exc)
            await sync_client_to_sheet(
                sheet_writers_map,
                agent_key,
                int(client.id),
                extra_updates=sheet_extra,
                call_row=row_call,
            )

        try:
            _OUTBOUND_PROFILE_KEYS = {
                "citta",
                "nome_agenzia",
                "collaboratori_num",
                "obiettivo_vendite",
                "note_call",
                "closer_nome",
            }
            _IMMO_PROFILE_KEYS = {
                "tipologia_immobile",
                "metratura",
                "zona",
                "urgenza_vendita",
                "agenzia_precedente",
                "motivo_no_vendita",
                "note_pre_visita",
                "via",
            }
            row_now = (
                (crud.get_client(int(client.id)) or {}) if client.id else {}
            )
            allowed = (
                _OUTBOUND_PROFILE_KEYS | _IMMO_PROFILE_KEYS
                if canonical_agent_key(agent_key) != "sara"
                else _OUTBOUND_PROFILE_KEYS
            )
            profile_updates: dict[str, Any] = {}
            for k in allowed:
                raw = args_effective.get(k)
                if raw is None or (isinstance(raw, str) and not raw.strip()):
                    raw = (row_now or {}).get(k)
                if k == "collaboratori_num":
                    if raw is None or (
                        isinstance(raw, str) and not str(raw).strip()
                    ):
                        continue
                    profile_updates[k] = str(raw).strip()
                    continue
                if str(raw or "").strip():
                    profile_updates[k] = str(raw).strip()
            if email_arg and client.id:
                profile_updates.setdefault("email", email_arg)
            if (
                profile_updates
                and client.id
                and canonical_agent_key(agent_key) == "gloria"
                and "via" in profile_updates
            ):
                from crm.address_validation import resolve_gloria_via_for_save

                row_via = row_now or {}
                city_hint = str(
                    args_effective.get("citta")
                    or row_via.get("citta")
                    or get_agency_citta(get_agency(agency_slug))
                    or ""
                ).strip()
                resolved_via = await resolve_gloria_via_for_save(
                    str(profile_updates["via"]),
                    zona=profile_updates.get("zona") or row_via.get("zona"),
                    citta=city_hint or None,
                    existing_via=row_via.get("via"),
                )
                if resolved_via:
                    profile_updates["via"] = resolved_via
                else:
                    profile_updates.pop("via", None)
            if profile_updates and client.id:
                crud.update_client(int(client.id), **profile_updates)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "book_appointment: update profilo fallito (non bloccante): %s", exc
            )

        wa_sent = False
        wa_error = ""
        closer_url = ""
        is_outbound = canonical_agent_key(agent_key) == "sara"
        closer_slug_wa = ""
        closer_nome_wa = ""
        if is_outbound:
            closer_slug_wa, closer_nome_wa = _closer_from_proposed(target)
            if not closer_slug_wa:
                closer_slug_wa = _default_closer_slug()
                closer_nome_wa = _closer_display_name(closer_slug_wa)
            base = public_base_url()
            if base:
                closer_url = f"{base.rstrip('/')}/closer/{closer_slug_wa}"

        if is_outbound and client.id is not None:
            try:
                crud.update_client(
                    int(client.id),
                    stato="appuntamento_fissato",
                    closer_nome=closer_nome_wa or None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "book_appointment: stato appuntamento_fissato fallito: %s", exc
                )

        async def _send_wa_confirmation() -> Any:
            nome_wa = str(
                args_effective.get("nome") or client_name or "Cliente"
            ).strip()
            if is_outbound and hasattr(
                whatsapp, "send_sara_booking_confirmation"
            ):
                return await whatsapp.send_sara_booking_confirmation(
                    to_number=client_phone,
                    nome=nome_wa,
                    when_label=slot_page_label,
                    public_url=public_url,
                    closer_url=closer_url or None,
                    closer_nome=closer_nome_wa,
                )
            return await whatsapp.send_confirmation(
                to_number=client_phone,
                nome=nome_wa,
                giorno=giorno_label,
                ora=ora_label,
                when_label=slot_page_label,
                public_url=public_url,
                agency_phone=agency["phone"],
                agency_name=agency["name"],
                agent_name=titolare_agenzia or "il titolare",
                closer_url=closer_url or None,
            )

        if whatsapp is not None and client_phone:
            result = await _send_wa_confirmation()
            if _whatsapp_delivery_ok(result):
                wa_sent = True
            else:
                wa_error = str(
                    (result or {}).get("error")
                    if isinstance(result, dict)
                    else "invio fallito"
                )
                logger.error(
                    "book_appointment: WhatsApp fallito call=%s err=%s",
                    provider_call_id,
                    wa_error,
                )
                result2 = await _send_wa_confirmation()
                if _whatsapp_delivery_ok(result2):
                    wa_sent = True
                    wa_error = ""
        elif whatsapp is not None:
            wa_error = "numero cliente mancante"
            logger.warning(
                "book_appointment: telefono mancante, skip WhatsApp call=%s",
                provider_call_id,
            )
        elif is_outbound:
            wa_error = "WhatsApp non configurato (verifica WHATSAPP_ENABLED_SARA)"
            logger.error(
                "book_appointment: WhatsApp assente per Sara call=%s",
                provider_call_id,
            )

        confirm_label = slot_page_label or format_appointment_page(target.start_iso)
        if wa_sent:
            if is_outbound:
                return (
                    f"Confermato: {confirm_label}. "
                    "WhatsApp inviato: messaggio «Appuntamento fissato» con data/ora. "
                    "Comunica al cliente di controllare WhatsApp ora; "
                    "il link Google Meet arriverà circa 2 ore prima."
                )
            return (
                f"Confermato: {confirm_label}. "
                "WhatsApp inviato al cliente con orario e link pagina dettagli."
            )
        if is_outbound:
            base_msg = (
                f"Confermato in agenda: {confirm_label}. "
                f"ATTENZIONE: WhatsApp NON inviato ({wa_error or 'errore sconosciuto'}). "
                "Ripeti a voce data, ora e che riceverà il link Meet 2 ore prima. "
            )
            if public_url:
                base_msg += f"Link dettagli: {public_url}"
            return base_msg
        if public_url:
            return f"Confermato: {confirm_label}. Link dettagli: {public_url}"
        return f"Confermato: {confirm_label}"

    async def _handle_schedule_callback(
        args: Mapping[str, Any],
        provider_call_id: str,
        agent_key: str,
    ) -> str:
        logger.info(
            "schedule_callback: richiesta call=%s agent=%s args_keys=%s",
            (provider_call_id or "")[:18],
            agent_key,
            sorted(args.keys()),
        )
        return await _enqueue_precise_callback(
            args, provider_call_id, agent_key, record_outcome=True
        )

    async def _handle_save_profile(
        args: Mapping[str, Any],
        provider_call_id: str,
        *,
        agent_key: str,
    ) -> str:
        profile_data: dict[str, Any] = {}
        client_cols: dict[str, Any] = {}
        ak_save = canonical_agent_key(agent_key)
        args_effective = dict(args)
        row_call = crud.get_call_by_sid(provider_call_id)
        if not row_call or not row_call.get("client_id"):
            return "ok"
        client_id = int(row_call["client_id"])
        if ak_save == "gloria":
            citta_arg = str(args_effective.get("citta") or "").strip()
            if citta_arg:
                zona_arg = str(args_effective.get("zona") or "").strip()
                client_row_pre = crud.get_client(client_id) or {}
                existing_zona = zona_arg or str(client_row_pre.get("zona") or "").strip()
                if not existing_zona:
                    args_effective["zona"] = citta_arg
                elif citta_arg.lower() not in crud._normalize_zone_text(existing_zona):
                    args_effective["zona"] = f"{existing_zona} - {citta_arg}"
        allowed_profile = crud._profile_field_names_for_agent(ak_save)
        for k, v in args_effective.items():
            if k in ("nome", "cognome") and str(v or "").strip():
                client_cols[k] = str(v).strip()
                continue
            if k not in allowed_profile:
                continue
            if k == "collaboratori_num":
                if str(v or "").strip() != "":
                    profile_data[k] = str(v).strip()
                continue
            if str(v or "").strip():
                profile_data[k] = str(v).strip()
        email_val = str(args_effective.get("email") or "").strip()
        if email_val and "@" in email_val:
            client_cols["email"] = email_val
        if not profile_data and not client_cols:
            return "ok"
        try:
            crud.assert_client_agent_scope(
                client_id, ak_save, context="save_profile"
            )
        except ValueError as exc:
            return str(exc)
        ak = ak_save
        if ak == "sara":
            profile_data.pop("via", None)
        if "via" in profile_data and ak == "gloria":
            from crm.address_validation import validate_via_in_zona

            client_row = crud.get_client(client_id) or {}
            zona = profile_data.get("zona") or client_row.get("zona")
            agency_slug = resolve_agency_slug_for_client(
                client_id=client_id,
                agent_key=ak,
            )
            agency_city = get_agency_citta(get_agency(agency_slug))
            citta = str(
                args_effective.get("citta")
                or client_row.get("citta")
                or agency_city
                or ""
            ).strip()
            check = await validate_via_in_zona(
                profile_data["via"],
                str(zona or "") or None,
                citta=citta or None,
            )
            if not check.valid:
                return check.message
            if check.normalized_via:
                profile_data["via"] = check.normalized_via
        if "note_pre_visita" in profile_data:
            new_note = str(profile_data.pop("note_pre_visita") or "").strip()
            if new_note:
                crud.append_note_pre_visita(
                    client_id,
                    new_note,
                    call_sid=provider_call_id,
                    esito_label="Profilo",
                )
        saved_labels: list[str] = []
        try:
            if profile_data:
                crud.update_client(client_id, **profile_data)
                saved_labels.extend(profile_data.keys())
            if client_cols:
                crud.update_client(client_id, **client_cols)
                saved_labels.extend(client_cols.keys())
            logger.info(
                "save_profile: aggiornato client_id=%s campi=%s",
                client_id,
                saved_labels,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("save_profile: update_client fallito: %s", exc)
            return "Errore nel salvataggio dati."

        if ak == "gloria" and (
            "zona" in profile_data or str(args_effective.get("citta") or "").strip()
        ):
            if crud.is_location_out_of_target_for_client(client_id):
                return await _reject_out_of_target(
                    client_id,
                    provider_call_id,
                    agent_key,
                    row_call=row_call,
                )

        if ak == "sara":
            row = crud.get_client(client_id) or {}
            missing = crud.missing_sara_qualification_fields(row)
            saved_it = ", ".join(saved_labels) if saved_labels else "nessun campo"
            identity_ok = bool(str(row.get("nome_agenzia") or "").strip())
            if "nome_agenzia" in saved_labels or identity_ok:
                identity_hint = (
                    " Identità confermata — passa SUBITO a FASE 2 (riconnessione). "
                    "NON ripetere domande su nome o agenzia."
                )
            else:
                identity_hint = ""
            if missing:
                return (
                    f"Salvato: {saved_it}.{identity_hint} "
                    f"Ancora da raccogliere e save_profile: "
                    f"{', '.join(missing)}."
                )
            return (
                f"Salvato: {saved_it}.{identity_hint} "
                "Profilo completo: puoi procedere con book_appointment."
            )
        if ak == "gloria":
            row = crud.get_client(client_id) or {}
            missing = crud.missing_gloria_qualification_fields(row)
            saved_it = ", ".join(saved_labels) if saved_labels else "nessun campo"
            if missing:
                msg = (
                    f"Salvato: {saved_it}. "
                    f"Qualifica INCOMPLETA — fai la prossima domanda mancante: "
                    f"{missing[0]}."
                )
                if len(missing) > 1:
                    msg += f" Restano anche: {', '.join(missing[1:])}."
                return msg
            return (
                f"Salvato: {saved_it}. "
                "Qualifica COMPLETA: puoi procedere con FASE 3 (proposta) "
                "e poi check_availability / book_appointment."
            )
        return "ok"

    async def _handle_set_outcome(
        args: Mapping[str, Any],
        provider_call_id: str,
        *,
        agent_key: str,
    ) -> str:
        ak = canonical_agent_key(agent_key)
        if ak not in ("sara", "gloria"):
            return "Tool set_outcome non disponibile per questo agente."

        raw_outcome = (
            str(args.get("outcome") or "")
            .strip()
            .lower()
            .replace(" ", "_")
        )
        if raw_outcome in ("nonintarget",):
            raw_outcome = "non_in_target"
        if ak == "gloria" and raw_outcome not in ("non_interessato", "non_in_target"):
            return (
                "Per Gloria usa solo non_interessato o non_in_target "
                "(per richiami usa schedule_callback)."
            )
        if raw_outcome not in _SET_OUTCOME_TOOL_MAP:
            return (
                "outcome non valido: usa non_interessato, non_in_target o da_richiamare."
            )

        row_call = crud.get_call_by_sid(provider_call_id)
        if not row_call or row_call.get("client_id") is None:
            return "Non riesco a identificare il cliente di questa chiamata."

        client_id = int(row_call["client_id"])
        note_call = str(args.get("note_call") or "").strip() or None
        recording_url = str(row_call.get("recording_url") or "").strip() or None
        tag = _SET_OUTCOME_TOOL_MAP[raw_outcome]

        try:
            crud.update_esito_chiamata(provider_call_id, tag, note_call)
        except Exception as exc:  # noqa: BLE001
            logger.exception("set_outcome: update_esito_chiamata fallito: %s", exc)
            return "Errore tecnico nel registrare l'esito."

        if raw_outcome in ("non_interessato", "non_in_target"):
            try:
                crud.cancel_outbound_queue_for_client(client_id, status="cancelled")
            except Exception as exc:  # noqa: BLE001
                logger.warning("set_outcome: cancel_outbound_queue fallito: %s", exc)

        if note_call:
            try:
                crud.update_client(client_id, note_call=note_call)
            except Exception as exc:  # noqa: BLE001
                logger.warning("set_outcome: note_call fallito: %s", exc)

        if recording_url:
            try:
                crud.update_call_status(
                    provider_call_id, recording_url=recording_url
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("set_outcome: recording_url fallito: %s", exc)

        if raw_outcome == "da_richiamare":
            if _has_callback_schedule_args(args):
                cb_result = await _enqueue_precise_callback(
                    args,
                    provider_call_id,
                    agent_key,
                    record_outcome=False,
                )
                if not cb_result.startswith("Richiamo pianificato"):
                    return cb_result
            else:
                try:
                    crud.schedule_retry_after_no_answer(client_id, ak)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("set_outcome: schedule_retry fallito: %s", exc)

        await sync_client_to_sheet(
            sheet_writers_map,
            agent_key,
            client_id,
            extra_updates={"note_call": note_call} if note_call else None,
            call_row=row_call,
        )

        labels = {
            "non_interessato": "non interessato",
            "non_in_target": "non in target",
            "da_richiamare": "da richiamare",
        }
        if ak == "gloria" and raw_outcome == "non_in_target":
            agency_slug = resolve_agency_slug_for_client(
                client_id=client_id,
                agent_key=agent_key,
            )
            return (
                f"{out_of_target_closing_script(agency_slug)} "
                f"Esito registrato: {labels.get(raw_outcome, raw_outcome)}."
            )
        return f"Esito registrato: {labels.get(raw_outcome, raw_outcome)}."

    async def _handle_prospect_not_on_line(
        args: Mapping[str, Any],
        provider_call_id: str,
        *,
        agent_key: str,
    ) -> str:
        ak = canonical_agent_key(agent_key)
        if ak != "sara":
            return "Tool non disponibile per questo agente."

        row_call = crud.get_call_by_sid(provider_call_id)
        if not row_call or row_call.get("client_id") is None:
            return (
                "Pronuncia SUBITO a voce: \"Capisco, scusi il disturbo — "
                "a che ora sarà disponibile il titolare?\" "
                "Poi attendi l'orario e usa schedule_callback."
            )

        client_id = int(row_call["client_id"])
        client_row = crud.get_client(client_id) or {}
        nome_raw = str(client_row.get("nome") or "il titolare").strip()
        nome = nome_raw.split()[0] if nome_raw else "il titolare"
        note = str(args.get("note") or "").strip()
        note_text = note or "Interlocutore non è il titolare"
        try:
            crud.update_client(client_id, note_call=note_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("prospect_not_on_line: note_call fallito: %s", exc)

        return (
            f"PRONUNCIA SUBITO A VOCE (obbligatorio, zero silenzio): "
            f"\"Capisco, scusi il disturbo — a che ora {nome} sarà disponibile?\" "
            f"Poi attendi l'orario. NON chiamare schedule_callback in questo turno."
        )

    async def handle(event: Mapping[str, Any]) -> str:
        provider_call_id = str(event.get("provider_call_id") or "").strip()
        tool_name = str(event.get("tool_name") or "").strip()
        args: Mapping[str, Any] = event.get("args") or {}
        agent_key, calendar, whatsapp = _integrations_for_event(event)

        if not tool_name:
            return "Tool name mancante."

        state = _state_for(provider_call_id)

        if tool_name == "check_availability":
            return await _handle_check_availability(args, state, calendar, agent_key)

        if tool_name == "book_appointment":
            return await _handle_book_appointment(
                args,
                state,
                provider_call_id,
                calendar,
                whatsapp,
                agent_key=agent_key,
                slack_notifier=_slack_for(agent_key),
                event=event,
            )

        if tool_name == "cancel_appointment":
            return await _handle_cancel_appointment(
                args,
                state,
                provider_call_id,
                calendar,
                agent_key=agent_key,
            )

        if tool_name == "schedule_callback":
            return await _handle_schedule_callback(args, provider_call_id, agent_key)

        if tool_name == "save_profile":
            return await _handle_save_profile(args, provider_call_id, agent_key=agent_key)

        if tool_name == "prospect_not_on_line":
            return await _handle_prospect_not_on_line(
                args, provider_call_id, agent_key=agent_key
            )

        if tool_name == "set_outcome":
            return await _handle_set_outcome(
                args, provider_call_id, agent_key=agent_key
            )

        logger.warning("Tool sconosciuto: %s", tool_name)
        return f"Tool '{tool_name}' non supportato."

    return handle
