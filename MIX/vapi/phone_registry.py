# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""Lookup numeri VAPI con cache breve."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from telephony.base import TelephonyError
from telephony.vapi.http import VAPI_TIMEOUT, vapi_sync_transport

logger = logging.getLogger(__name__)

VAPI_BASE_URL = "https://api.vapi.ai"
_CACHE_TTL_S = 300.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def fetch_phone_number(api_key: str, phone_number_id: str) -> dict[str, Any]:
    """GET /phone-number/{id} con cache breve."""
    pnid = (phone_number_id or "").strip()
    if not pnid:
        raise TelephonyError("phone_number_id vuoto")
    now = time.monotonic()
    cached = _cache.get(pnid)
    if cached and now - cached[0] < _CACHE_TTL_S:
        return dict(cached[1])

    headers = {"Authorization": f"Bearer {api_key.strip()}"}
    with httpx.Client(timeout=VAPI_TIMEOUT, transport=vapi_sync_transport()) as client:
        resp = client.get(f"{VAPI_BASE_URL}/phone-number/{pnid}", headers=headers)
    if resp.status_code >= 400:
        raise TelephonyError(
            f"Numero VAPI {pnid} non trovato (HTTP {resp.status_code})."
        )
    row = resp.json()
    _cache[pnid] = (now, row)
    return dict(row)


def resolve_phone_number_id(
    api_key: str,
    phone_number_id: str,
) -> tuple[str, dict[str, Any]]:
    """Restituisce (id, metadati) del numero VAPI configurato nel .env."""
    row = fetch_phone_number(api_key, phone_number_id)
    logger.debug(
        "Dial con numero %s (%s) provider=%s",
        phone_number_id,
        row.get("number"),
        row.get("provider"),
    )
    return phone_number_id, row


def invalidate_phone_cache() -> None:
    _cache.clear()
