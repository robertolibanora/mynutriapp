# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, time as dt_time
from zoneinfo import ZoneInfo

# Fascia operativa retry (default 9–18, sovrascrivibile via env)
BUSINESS_HOURS_START = int(os.getenv("BUSINESS_HOURS_START", "9"))
BUSINESS_HOURS_END = int(os.getenv("BUSINESS_HOURS_END", "18"))

CALL_START = dt_time(BUSINESS_HOURS_START, 0)
CALL_END = dt_time(BUSINESS_HOURS_END, 0)

# Limite chiamate/giorno: giorno primo contatto (iniziale + subito + altre 2 = 4)
# e giorni successivi (4). Configurabile via env.
_FIRST_DAY_MAX = int(os.getenv("RETRY_FIRST_DAY_MAX", "1"))
_SUBSEQUENT_DAY_MAX = int(os.getenv("RETRY_SUBSEQUENT_DAY_MAX", "1"))

# Richiami automatici entro questa soglia sono "immediati" (next_attempt_at NULL in coda)
_IMMEDIATE_RETRY_TOLERANCE_S = 120

# Richiamo concordato dall'agente (schedule_callback) se oltre questa soglia nel futuro
_PRECISE_CALLBACK_MIN_S = 120

# Minuti tra un lead e il successivo quando ripianificati sullo stesso giorno
_QUEUE_STAGGER_MIN = max(1, int(os.getenv("QUEUE_STAGGER_MINUTES", "20")))


def next_hour_datetime(now: datetime, tz: ZoneInfo) -> datetime:
    """Inizio dell'ora di calendario successiva (timezone locale). Es. 14:23 → 15:00."""
    local = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    return local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def _is_business_day(d: date) -> bool:
    """Lun–Ven."""
    return d.weekday() < 5


def _next_business_date(from_date: date) -> date:
    d = from_date + timedelta(days=1)
    while not _is_business_day(d):
        d += timedelta(days=1)
    return d


def next_business_open(from_dt: datetime, tz: ZoneInfo) -> datetime:
    """Prossimo istante in fascia operativa (Lun–Ven, BUSINESS_HOURS_START–END)."""
    local = from_dt.astimezone(tz) if from_dt.tzinfo else from_dt.replace(tzinfo=tz)
    if _is_business_day(local.date()):
        t = local.time().replace(tzinfo=None)
        if t < CALL_START:
            return datetime.combine(local.date(), CALL_START, tzinfo=tz)
        if t <= CALL_END:
            return local
    nd = _next_business_date(local.date())
    return datetime.combine(nd, CALL_START, tzinfo=tz)


def next_day_first_slot(
    tz: ZoneInfo,
    *,
    from_dt: datetime | None = None,
) -> datetime:
    """Apertura fascia operativa del prossimo giorno lavorativo."""
    local = (from_dt or datetime.now(tz)).astimezone(tz)
    nd = _next_business_date(local.date())
    return datetime.combine(nd, CALL_START, tzinfo=tz)


def is_first_outreach_day(client_id: int, tz: ZoneInfo) -> bool:
    """True se oggi è il giorno della prima chiamata outbound al lead."""
    from crm import crud

    first = crud.get_first_call_date(int(client_id))
    today = datetime.now(tz).date()
    if first is None:
        return True
    return first == today


def get_daily_call_limit(client_id: int, tz: ZoneInfo) -> int:
    """Max chiamate consentite oggi per il lead (giorno 1 vs giorni successivi)."""
    if is_first_outreach_day(client_id, tz):
        return max(1, _FIRST_DAY_MAX)
    return max(1, _SUBSEQUENT_DAY_MAX)


def can_call_today(
    client_id: int,
    tz: ZoneInfo,
    *,
    calls_today: int | None = None,
) -> bool:
    """True se il lead non ha ancora raggiunto il tetto giornaliero."""
    from crm import crud

    ct = calls_today if calls_today is not None else crud.count_calls_today(int(client_id))
    return ct < get_daily_call_limit(int(client_id), tz)


def is_immediate_retry(next_at: datetime, now: datetime) -> bool:
    """True se il richiamo va accodato subito (coda libera → dial)."""
    return (next_at - now).total_seconds() <= _IMMEDIATE_RETRY_TOLERANCE_S


def _spill_past_business_close(candidate: datetime, tz: ZoneInfo) -> datetime:
    """Se oltre chiusura, sposta al giorno lavorativo successivo mantenendo l'offset."""
    local = candidate.astimezone(tz) if candidate.tzinfo else candidate.replace(tzinfo=tz)
    day_close = datetime.combine(local.date(), CALL_END, tzinfo=tz)
    if local <= day_close:
        return local
    overflow_min = max(
        _QUEUE_STAGGER_MIN,
        int((local - day_close).total_seconds() // 60) or _QUEUE_STAGGER_MIN,
    )
    nd = _next_business_date(local.date())
    return _spill_past_business_close(
        datetime.combine(nd, CALL_START, tzinfo=tz) + timedelta(minutes=overflow_min),
        tz,
    )


def stagger_scheduled_attempt(
    base_at: datetime,
    tz: ZoneInfo,
    *,
    agent_key: str,
    client_id: int | None = None,
    slot_index: int | None = None,
) -> datetime:
    """Sfasa l'orario: sequenziale dopo l'ultimo slot del giorno (evita collisioni in batch)."""
    from crm import crud

    local = base_at.astimezone(tz) if base_at.tzinfo else base_at.replace(tzinfo=tz)
    day = local.date()
    day_open = datetime.combine(day, CALL_START, tzinfo=tz)
    day_close = datetime.combine(day, CALL_END, tzinfo=tz)

    if slot_index is not None:
        window_min = max(1, int((day_close - day_open).total_seconds() // 60))
        offset_min = max(0, int(slot_index)) * _QUEUE_STAGGER_MIN
        extra_days = offset_min // window_min if window_min else 0
        minute_in_window = offset_min % window_min if window_min else 0

        target_date = day
        for _ in range(extra_days):
            target_date = _next_business_date(target_date)

        result = datetime.combine(target_date, CALL_START, tzinfo=tz) + timedelta(
            minutes=minute_in_window
        )
        return _spill_past_business_close(result, tz)

    latest = crud.latest_queue_next_attempt_on_day(
        agent_key,
        day,
        exclude_client_id=client_id,
    )
    if latest is not None:
        result = max(local, latest + timedelta(minutes=_QUEUE_STAGGER_MIN))
    else:
        result = max(local, day_open)
    return _spill_past_business_close(result, tz)


def finalize_queue_next_attempt(
    next_at: datetime | None,
    now: datetime,
    tz: ZoneInfo,
    *,
    agent_key: str | None = None,
    client_id: int | None = None,
    apply_stagger: bool = True,
) -> str | None:
    """Serializza next_attempt_at: NULL se immediato, altrimenti sfasato per agente."""
    if next_at is None:
        return None
    if is_immediate_retry(next_at, now):
        return None
    out = next_at
    if apply_stagger and agent_key:
        out = stagger_scheduled_attempt(
            out,
            tz,
            agent_key=agent_key,
            client_id=client_id,
        )
    return out.isoformat(sep=" ", timespec="seconds")


def next_attempt_at_to_queue_iso(
    next_at: datetime | None,
    now: datetime,
    tz: ZoneInfo | None = None,
    *,
    agent_key: str | None = None,
    client_id: int | None = None,
    apply_stagger: bool = True,
) -> str | None:
    """Compat: delega a finalize_queue_next_attempt."""
    if tz is None:
        from app.config import get_business_timezone

        tz = get_business_timezone()
    return finalize_queue_next_attempt(
        next_at,
        now,
        tz,
        agent_key=agent_key,
        client_id=client_id,
        apply_stagger=apply_stagger,
    )


def compute_next_attempt_at(
    tentativi: int,
    now: datetime,
    tz: ZoneInfo,
    max_attempts: int,
    *,
    client_id: int | None = None,
    calls_today: int | None = None,
) -> datetime | None:
    """
    Ritorna quando ripianificare il richiamo.
    None se esaurito il budget tentativi globali.
    Se in fascia e sotto il tetto giornaliero → now (richiamo appena la coda si libera).
    """
    max_a = max(1, int(max_attempts))
    if tentativi >= max_a:
        return None

    now_local = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)

    if client_id is not None and not can_call_today(
        int(client_id), tz, calls_today=calls_today
    ):
        return next_day_first_slot(tz, from_dt=now_local)

    if not is_business_hours_now(now_local, tz):
        return next_business_open(now_local, tz)

    # Dopo almeno un tentativo oggi, non richiamare subito: rispetta QUEUE_STAGGER_MINUTES.
    if client_id is not None:
        from crm import crud

        ct = (
            calls_today
            if calls_today is not None
            else crud.count_calls_today(int(client_id))
        )
        if ct > 0:
            candidate = now_local + timedelta(minutes=_QUEUE_STAGGER_MIN)
            day_close = datetime.combine(now_local.date(), CALL_END, tzinfo=tz)
            if candidate > day_close:
                return next_day_first_slot(tz, from_dt=now_local)
            return candidate

    return now_local


def compute_next_attempt_after_voicemail(
    tentativi: int,
    now: datetime,
    tz: ZoneInfo,
    max_attempts: int,
    *,
    client_id: int | None = None,
    calls_today: int | None = None,
) -> datetime | None:
    """
    Ripianifica dopo segreteria: stessa logica coda dinamica (no slot fissi).
    None se esaurito il budget tentativi.
    """
    return compute_next_attempt_at(
        tentativi,
        now,
        tz,
        max_attempts,
        client_id=client_id,
        calls_today=calls_today,
    )


def is_business_hours_now(now: datetime, tz: ZoneInfo) -> bool:
    """True se Lun–Ven e ora in fascia BUSINESS_HOURS_START–END."""
    local = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    if not _is_business_day(local.date()):
        return False
    current = local.time().replace(tzinfo=None)
    return CALL_START <= current <= CALL_END


def is_precise_callback_datetime(dt: datetime, tz: ZoneInfo) -> bool:
    """Richiamo esplicito (schedule_callback), non retry automatico in coda."""
    local = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
    now = datetime.now(tz)
    return (local - now).total_seconds() > _PRECISE_CALLBACK_MIN_S


def is_call_allowed_now(
    now: datetime,
    tz: ZoneInfo,
    *,
    client_id: int | None = None,
    calls_today: int | None = None,
) -> bool:
    """True se si può chiamare ora: fascia operativa + tetto giornaliero."""
    if not is_business_hours_now(now, tz):
        return False
    if client_id is not None:
        from crm import crud

        if crud.is_precise_callback_due(int(client_id)):
            return True
    if client_id is None:
        return True
    return can_call_today(int(client_id), tz, calls_today=calls_today)
