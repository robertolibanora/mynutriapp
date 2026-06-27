# ─────────────────────────────────────────────────────────
# SHARED PIECE — iniezione pitch Sara via VAPI controlUrl (monologo continuo)
# ─────────────────────────────────────────────────────────
"""Bridge pitch finale Sara: TTS forzato via controlUrl quando il LLM si spezza."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field

import httpx

from telephony.vapi.http import vapi_async_transport

logger = logging.getLogger(__name__)

_PITCH_TRIGGER = re.compile(
    r"esclusiva del nominativo|l['']esclusiva del nominativo|due esclusive",
    re.IGNORECASE,
)
_STALL_TRIGGER = re.compile(r"profilandolo per voi", re.IGNORECASE)
_DATES_SPOKEN = re.compile(r"ti andrebbe di riprendere|appuntamento con un nostro consulente", re.IGNORECASE)

_REGISTRY: dict[str, "SaraPitchBridge"] = {}
_SCHEDULED: set[str] = set()


@dataclass
class SaraPitchBridge:
    call_id: str
    control_url: str
    pitch_final_block: str
    slots_tail: str
    injected: bool = False
    dates_spoken: bool = False
    _inject_task: asyncio.Task[None] | None = field(default=None, repr=False)


def slots_tail_from_block(pitch_final_block: str) -> str:
    """Parte finale del blocco pitch per recovery su stall (da 'profilandolo per voi' in poi)."""
    low = pitch_final_block.lower()
    for marker in ("ti andrebbe di riprendere", "profilandolo per voi"):
        idx = low.find(marker)
        if idx >= 0:
            return pitch_final_block[idx:].strip()
    return pitch_final_block.strip()


def register_sara_pitch_bridge(
    call_id: str,
    control_url: str,
    pitch_final_block: str,
) -> None:
    cid = str(call_id or "").strip()
    url = str(control_url or "").strip()
    block = str(pitch_final_block or "").strip()
    if not cid or not url or not block:
        return
    _REGISTRY[cid] = SaraPitchBridge(
        call_id=cid,
        control_url=url,
        pitch_final_block=block,
        slots_tail=slots_tail_from_block(block),
    )
    logger.info(
        "pitch_bridge: registrato call_id=%s len=%s",
        cid,
        len(block),
    )


def unregister_sara_pitch_bridge(call_id: str) -> None:
    cid = str(call_id or "").strip()
    bridge = _REGISTRY.pop(cid, None)
    _SCHEDULED.discard(cid)
    if bridge and bridge._inject_task and not bridge._inject_task.done():
        bridge._inject_task.cancel()


async def fetch_control_url(
    api_key: str,
    call_id: str,
    *,
    base_url: str = "https://api.vapi.ai",
    attempts: int = 12,
) -> str:
    """Recupera monitor.controlUrl dopo il dial (può comparire con ritardo)."""
    cid = str(call_id or "").strip()
    if not cid:
        return ""
    headers = {"Authorization": f"Bearer {api_key.strip()}"}
    for _ in range(max(1, attempts)):
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                transport=vapi_async_transport(),
            ) as client:
                resp = await client.get(f"{base_url.rstrip('/')}/call/{cid}", headers=headers)
            if resp.status_code >= 400:
                await asyncio.sleep(0.5)
                continue
            data = resp.json()
            url = str((data.get("monitor") or {}).get("controlUrl") or "").strip()
            if url:
                return url
        except httpx.HTTPError as exc:
            logger.debug("pitch_bridge: GET call %s: %s", cid, exc)
        await asyncio.sleep(0.5)
    return ""


async def _control_post(control_url: str, payload: dict) -> bool:
    url = str(control_url or "").strip()
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        return resp.status_code < 400
    except httpx.HTTPError as exc:
        logger.warning("pitch_bridge: control post errore: %s", exc)
        return False


async def _control_say(control_url: str, content: str) -> bool:
    """Muta il LLM, inietta il testo via TTS, poi aggiunge il testo alla
    cronologia conversazione così il LLM sa di averlo già detto."""
    text = str(content or "").strip()
    if not text:
        return False
    # Muta LLM prima dell'iniezione per evitare sovrapposizioni
    await _control_post(control_url, {"type": "control", "control": "mute-assistant"})
    ok = False
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                str(control_url or "").strip(),
                json={
                    "type": "say",
                    "content": text,
                    "endCallAfterSpoken": False,
                },
                headers={"Content-Type": "application/json"},
            )
        ok = resp.status_code < 400
        if not ok:
            logger.warning(
                "pitch_bridge: control say status=%s body=%s",
                resp.status_code,
                resp.text[:200],
            )
    except httpx.HTTPError as exc:
        logger.warning("pitch_bridge: control say errore: %s", exc)
    # Aggiunge il testo alla cronologia così il LLM va diretto a FASE 3
    if ok:
        await _control_post(control_url, {
            "type": "add-message",
            "message": {
                "role": "assistant",
                "content": text,
            },
        })
    await _control_post(control_url, {"type": "control", "control": "unmute-assistant"})
    return ok


async def _inject_after_delay(bridge: SaraPitchBridge, *, delay_s: float, content: str) -> None:
    try:
        await asyncio.sleep(max(0.0, delay_s))
        if bridge.injected:
            return
        ok = await _control_say(bridge.control_url, content)
        if ok:
            bridge.injected = True
            logger.info(
                "pitch_bridge: say iniettato call_id=%s chars=%s",
                bridge.call_id,
                len(content),
            )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("pitch_bridge: inject fallito call_id=%s: %s", bridge.call_id, exc)
    finally:
        _SCHEDULED.discard(bridge.call_id)


def _schedule_inject(
    bridge: SaraPitchBridge,
    *,
    delay_s: float,
    content: str,
) -> None:
    if bridge.injected or bridge.call_id in _SCHEDULED:
        return
    _SCHEDULED.add(bridge.call_id)
    if bridge._inject_task and not bridge._inject_task.done():
        bridge._inject_task.cancel()
    bridge._inject_task = asyncio.create_task(
        _inject_after_delay(bridge, delay_s=delay_s, content=content),
        name=f"sara-pitch-inject-{bridge.call_id}",
    )


def on_sara_assistant_transcript(call_id: str, text: str) -> None:
    """Chiamato su transcript assistant final — avvia say del pitch se serve."""
    cid = str(call_id or "").strip()
    utterance = str(text or "").strip()
    if not cid or not utterance:
        return
    bridge = _REGISTRY.get(cid)
    if not bridge or bridge.injected:
        return
    if _DATES_SPOKEN.search(utterance):
        bridge.dates_spoken = True
        return
    if bridge.dates_spoken:
        return

    if _STALL_TRIGGER.search(utterance) and not _DATES_SPOKEN.search(utterance):
        # Stall: Sara si è fermata a "profilandolo per voi" → inietta la coda.
        _schedule_inject(bridge, delay_s=0.2, content=bridge.slots_tail)
        return

    if _PITCH_TRIGGER.search(utterance):
        # Dopo "esclusiva del nominativo/due esclusive" → inietta tutto il blocco
        # con delay breve (0.2s) così il TTS parte prima che il LLM generi audio.
        _schedule_inject(bridge, delay_s=0.2, content=bridge.pitch_final_block)
