# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""Calendario DB per disponibilità + specchio Google su booking."""
from __future__ import annotations

import logging
from typing import Any, Optional

from integrations.base import CalendarProvider, IntegrationError, Slot

logger = logging.getLogger(__name__)


class DBWithGoogleMirror(CalendarProvider):
    """
    Disponibilità solo da DB slot_disponibili (agent_key).
    Booking: scrive su DB E su Google Calendar come specchio (Meet link).
    Google non genera slot liberi: evita orari sintetici ogni 30 min.
    """

    slug = "db_with_google_mirror"

    def __init__(
        self,
        db_calendar: CalendarProvider,
        google_calendar: CalendarProvider | None,
        agent_key: str = "gloria",
    ) -> None:
        self.db = db_calendar
        self.google = google_calendar
        self.agent_key = str(agent_key or "gloria").strip().lower() or "gloria"

    async def get_free_slots(self, date_iso: str) -> list[Slot]:
        """Disponibilità solo da slot_disponibili — Google non genera slot liberi."""
        return await self.db.get_free_slots(date_iso)

    async def create_event(
        self,
        nome: str,
        telefono: str,
        email: Optional[str],
        slot: Slot,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if slot.slot_id is not None:
            result = await self.db.create_event(
                nome=nome,
                telefono=telefono,
                email=email,
                slot=slot,
                **kwargs,
            )
            if self.google is not None:
                try:
                    google_result = await self.google.create_event(
                        nome=nome,
                        telefono=telefono,
                        email=email,
                        slot=slot,
                        description=(
                            f"Prenotato via agente vocale ({self.agent_key})\n"
                            f"Tel: {telefono}"
                        ),
                        **kwargs,
                    )
                    gid = google_result.get("event_id")
                    if gid:
                        result["google_event_id"] = gid
                        result["event_id"] = gid
                    meet = google_result.get("meet_link")
                    if meet:
                        result["meet_link"] = meet
                    html = google_result.get("html_link")
                    if html:
                        result["html_link"] = html
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Google mirror fallito: %s — condividi il calendario Google "
                        "con il service account (permesso «Modifica eventi»)",
                        exc,
                    )
            return result

        if self.google is None:
            raise IntegrationError("slot senza id DB e Google Calendar non configurato")
        return await self.google.create_event(
            nome=nome,
            telefono=telefono,
            email=email,
            slot=slot,
            description=(
                f"Prenotato via agente vocale ({self.agent_key})\n"
                f"Tel: {telefono}"
            ),
            **kwargs,
        )
