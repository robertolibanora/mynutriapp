# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""Invio programmato del link Google Meet ~2 ore prima dell'appuntamento (Sara)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping, Optional

from app.config import canonical_agent_key
from app.formatting import format_appointment_page, public_base_url
from crm import crud
from integrations.base import WhatsAppProvider

logger = logging.getLogger(__name__)

_DEFAULT_POLL_S = 30
_OUTBOUND_AGENT_KEYS = frozenset({"sara"})


class MeetReminderScheduler:
    """Poll periodico: appuntamenti Sara con start_time - 2h <= now → WhatsApp Meet."""

    def __init__(
        self,
        *,
        whatsapps: Mapping[str, Optional[WhatsAppProvider]],
        interval_s: int = _DEFAULT_POLL_S,
    ) -> None:
        self._whatsapps = dict(whatsapps)
        self._interval_s = max(15, int(interval_s))
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> asyncio.Task[None]:
        self._task = asyncio.create_task(self._loop(), name="meet-reminder-scheduler")
        return self._task

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await self._tick()
                except Exception:  # noqa: BLE001
                    logger.exception("MeetReminderScheduler: errore tick")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self._interval_s)
                    return
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise

    async def _tick(self) -> None:
        due = await asyncio.to_thread(crud.list_appointments_due_meet_reminder)
        for row in due:
            if self._stop.is_set():
                return
            await self._send_one(row)

    async def _send_one(self, row: Mapping[str, Any]) -> None:
        appt_id = int(row["id"])
        agent_key = canonical_agent_key(str(row.get("agent_key") or "sara"))
        if agent_key not in _OUTBOUND_AGENT_KEYS:
            return

        whatsapp = self._whatsapps.get(agent_key) or self._whatsapps.get("sara")
        if whatsapp is None:
            logger.warning(
                "MeetReminderScheduler: WhatsApp non configurato agent=%s appt=%s",
                agent_key,
                appt_id,
            )
            return

        telefono = str(row.get("telefono") or "").strip()
        if not telefono:
            logger.warning(
                "MeetReminderScheduler: telefono mancante appt=%s client_id=%s",
                appt_id,
                row.get("client_id"),
            )
            return

        meet_url = str(row.get("meet_url") or "").strip()
        public_token = str(row.get("public_token") or "").strip()
        base = public_base_url()
        public_url = (
            f"{base.rstrip('/')}/appointment/{public_token}"
            if base and public_token
            else ""
        )
        link = meet_url or public_url
        if not link:
            logger.warning(
                "MeetReminderScheduler: nessun link Meet/public appt=%s — skip",
                appt_id,
            )
            return

        nome = str(row.get("nome") or "Cliente").strip() or "Cliente"
        when_label = format_appointment_page(str(row.get("start_time") or ""))

        send_meet = getattr(whatsapp, "send_meet_link_reminder", None)
        if callable(send_meet):
            result = await send_meet(
                to_number=telefono,
                nome=nome,
                when_label=when_label,
                meet_url=link,
            )
        else:
            text = (
                f"Ciao {nome}! Mancano circa 2 ore alla tua video riunione "
                f"con Evolution Media"
            )
            if when_label:
                text += f" ({when_label})"
            text += f".\nLink Google Meet: {link}"
            result = await whatsapp.send_message(to_number=telefono, text=text)

        if not isinstance(result, dict) or result.get("error"):
            logger.error(
                "MeetReminderScheduler: invio fallito appt=%s result=%r",
                appt_id,
                result,
            )
            return

        marked = await asyncio.to_thread(crud.mark_meet_whatsapp_sent, appt_id)
        if marked:
            logger.info(
                "MeetReminderScheduler: Meet inviato appt=%s client=%s when=%s",
                appt_id,
                row.get("client_id"),
                when_label,
            )


__all__ = ["MeetReminderScheduler"]
