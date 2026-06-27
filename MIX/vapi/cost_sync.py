"""Durata e costi chiamata: webhook VAPI + GET /call/:id (costo finale)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Mapping

from app.billing import estimate_call_cost, load_billing_rates
from crm import crud

logger = logging.getLogger(__name__)

# Riferimenti forti ai task di billing in background: l'event loop tiene solo
# weak ref, quindi senza questo set il task potrebbe essere GC-ato prima di
# completare la sincronizzazione costo/durata da Vapi.
_BG_TASKS: set[asyncio.Task[None]] = set()


def _on_billing_task_done(task: "asyncio.Task[None]") -> None:
    _BG_TASKS.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("billing sync task terminato con errore: %s", exc)


def _coerce_int(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        n = int(float(val))
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


def _coerce_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_iso_ts(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    text = str(val).strip()
    if not text:
        return None
    try:
        if "T" not in text and " " in text:
            text = text.replace(" ", "T", 1)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _duration_from_timestamps(start: Any, end: Any) -> int | None:
    st = _parse_iso_ts(start)
    et = _parse_iso_ts(end)
    if not st or not et:
        return None
    sec = int(round((et - st).total_seconds()))
    return sec if sec >= 0 else None


def _dig_cost_usd(*sources: Mapping[str, Any]) -> float | None:
    for src in sources:
        for key in ("cost", "totalCost", "total_cost"):
            v = _coerce_float(src.get(key))
            if v is not None and v >= 0:
                return v
    return None


def extract_end_of_call_metrics(event: Mapping[str, Any]) -> dict[str, Any]:
    """Estrae durata e costo VAPI (USD) dal payload normalizzato + raw."""
    raw = dict(event.get("raw") or {})
    message = dict(raw.get("message") or {})
    call = dict(message.get("call") or event.get("call") or {})
    artifact = dict(message.get("artifact") or event.get("artifact") or {})

    started_at = message.get("startedAt") or call.get("startedAt")
    ended_at = message.get("endedAt") or call.get("endedAt")
    duration_from_ts = _duration_from_timestamps(started_at, ended_at)

    duration_candidates: list[int | None] = [
        _coerce_int(event.get("duration_seconds")),
        _coerce_int(message.get("durationSeconds")),
        _coerce_int(message.get("duration_seconds")),
        _coerce_int(message.get("duration")),
        _coerce_int(call.get("durationSeconds")),
        _coerce_int(call.get("duration")),
    ]
    duration_seconds: int | None = None
    for cand in duration_candidates:
        if cand is not None and cand > 0:
            duration_seconds = cand
            break
    if duration_seconds is None and duration_from_ts is not None and duration_from_ts > 0:
        duration_seconds = duration_from_ts
    if duration_seconds is None:
        for cand in duration_candidates:
            if cand is not None:
                duration_seconds = cand
                break

    vapi_cost_usd = _dig_cost_usd(message, call, artifact)

    return {
        "duration_seconds": duration_seconds,
        "vapi_cost_usd": vapi_cost_usd,
        "ended_at": message.get("endedAt") or call.get("endedAt"),
    }


async def fetch_call_metrics_from_api(provider: Any, call_id: str) -> dict[str, Any]:
    """GET /call/:id — durata e costo aggiornati dopo fine chiamata."""
    if not call_id or not hasattr(provider, "fetch_call_record"):
        return {}
    try:
        return await provider.fetch_call_record(call_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_call_record fallito call_id=%s: %s", call_id, exc)
        return {}


def apply_call_billing(
    call_sid: str,
    *,
    duration_seconds: int | None,
    vapi_cost_usd: float | None = None,
) -> float | None:
    """Persiste durata e cost_estimate (EUR, tariffa .env) sul record chiamata."""
    cs = (call_sid or "").strip()
    if not cs:
        return None
    rates = load_billing_rates()
    call_row = crud.get_call_by_sid_raw(cs)
    cost_eur = estimate_call_cost(
        duration_seconds,
        rates,
        row=call_row,
    )
    crud.update_call_billing(
        cs,
        duration_seconds=duration_seconds,
        cost_estimate=cost_eur,
        vapi_cost_usd=vapi_cost_usd,
    )
    if vapi_cost_usd is not None and vapi_cost_usd >= 0:
        try:
            crud.add_call_event(
                cs,
                "vapi_cost",
                {"cost_usd": round(float(vapi_cost_usd), 6)},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("vapi_cost event fallito call_id=%s: %s", cs, exc)
    return cost_eur


async def sync_call_billing_after_end(
    provider: Any,
    call_sid: str,
    *,
    initial_duration: int | None = None,
    initial_vapi_cost: float | None = None,
) -> None:
    """Attende la finalizzazione VAPI e aggiorna durata/costo sul DB."""
    await asyncio.sleep(2.0)
    api_metrics = await fetch_call_metrics_from_api(provider, call_sid)
    duration = api_metrics.get("duration_seconds")
    if duration is None or duration <= 0:
        duration = initial_duration
    vapi_cost = api_metrics.get("vapi_cost_usd")
    if vapi_cost is None:
        vapi_cost = initial_vapi_cost
    apply_call_billing(
        call_sid,
        duration_seconds=duration,
        vapi_cost_usd=vapi_cost,
    )
    logger.info(
        "billing sync call_id=%s duration_s=%s cost_eur=%s vapi_usd=%s",
        call_sid,
        duration,
        estimate_call_cost(duration),
        vapi_cost,
    )


def schedule_billing_sync(
    provider: Any,
    call_sid: str,
    *,
    initial_duration: int | None = None,
    initial_vapi_cost: float | None = None,
) -> None:
    """Task in background: non blocca il webhook."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(
        sync_call_billing_after_end(
            provider,
            call_sid,
            initial_duration=initial_duration,
            initial_vapi_cost=initial_vapi_cost,
        ),
        name=f"billing-sync-{call_sid[:8]}",
    )
    _BG_TASKS.add(task)
    task.add_done_callback(_on_billing_task_done)
