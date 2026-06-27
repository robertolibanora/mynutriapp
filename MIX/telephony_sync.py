"""Stato sincronizzazione metriche telefoniche (fornitore esterno) — cache breve."""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import httpx

from telephony.vapi.http import vapi_sync_transport

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 120
_PROBE_TIMEOUT = httpx.Timeout(connect=3.0, read=4.0, write=3.0, pool=3.0)

_NOTICE_DELAYED: dict[str, Any] = {
    "active": True,
    "title": "Statistiche in sincronizzazione",
    "message": (
        "Minuti e costi mostrano le chiamate già registrate. "
        "I totali si aggiornano da soli appena il provider telefonico "
        "è di nuovo raggiungibile — non devi fare nulla."
    ),
}
_NOTICE_OK: dict[str, Any] = {"active": False}

_cache: tuple[float, dict[str, Any]] | None = None
_probe_lock = threading.Lock()
_probe_running = False


def delayed_sync_notice() -> dict[str, Any]:
    return dict(_NOTICE_DELAYED)


def _probe_telephony_metrics_api() -> bool:
    """True se il fornitore telefonico risponde (probe leggero)."""
    api_key = (os.getenv("VAPI_API_KEY") or "").strip()
    if not api_key:
        return True

    try:
        with httpx.Client(transport=vapi_sync_transport(), timeout=_PROBE_TIMEOUT) as client:
            resp = client.get(
                "https://api.vapi.ai/call",
                params={"limit": 1},
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code == 200:
            return True
        logger.info(
            "telephony_sync: probe HTTP %s (fornitore non pronto)",
            resp.status_code,
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.info("telephony_sync: probe fallito (%s)", exc)
        return False


def _refresh_cache_async() -> None:
    global _probe_running

    with _probe_lock:
        if _probe_running:
            return
        _probe_running = True

    def run() -> None:
        global _cache, _probe_running
        try:
            notice = _NOTICE_OK if _probe_telephony_metrics_api() else dict(_NOTICE_DELAYED)
            _cache = (time.time(), notice)
        finally:
            with _probe_lock:
                _probe_running = False

    threading.Thread(target=run, daemon=True, name="telephony-sync-probe").start()


def get_telephony_sync_notice() -> dict[str, Any]:
    """Ritorna subito cache/stale; il probe gira in background se scaduto."""
    global _cache
    now = time.time()
    if _cache is not None and now - _cache[0] < _CACHE_TTL_S:
        return dict(_cache[1])

    if _cache is not None:
        _refresh_cache_async()
        return dict(_cache[1])

    _cache = (now, dict(_NOTICE_OK))
    _refresh_cache_async()
    return dict(_NOTICE_OK)


def mark_telephony_sync_down() -> None:
    """Segna il fornitore come non raggiungibile (cache banner ~2 min)."""
    global _cache
    _cache = (time.time(), dict(_NOTICE_DELAYED))
