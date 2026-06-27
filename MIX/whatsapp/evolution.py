# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""WhatsApp via Evolution API (sendText)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from crm.phone import normalize_e164_digits
from integrations.base import WhatsAppProvider

logger = logging.getLogger(__name__)

_SEND_TIMEOUT_S = 30.0


def _normalize_to_number(raw: str) -> str:
    """E.164 senza '+' (es. 393924843402)."""
    return normalize_e164_digits(raw)


class EvolutionWhatsApp(WhatsAppProvider):
    slug = "evolution_whatsapp"

    def __init__(self, api_url: str, api_key: str, instance: str) -> None:
        self._api_url = str(api_url or "").rstrip("/")
        self._api_key = str(api_key or "").strip()
        self._instance = str(instance or "").strip()
        if not self._api_url or not self._api_key or not self._instance:
            raise ValueError(
                "EvolutionWhatsApp: api_url, api_key e instance sono obbligatori"
            )

    async def _send_text(self, *, recipient: str, text: str, label: str) -> dict[str, Any]:
        dest = str(recipient or "").strip()
        if not dest:
            err = f"{label} vuoto"
            logger.error("EvolutionWhatsApp._send_text: %s", err)
            return {"error": err}

        url = f"{self._api_url}/message/sendText/{self._instance}"
        headers = {"apikey": self._api_key, "Content-Type": "application/json"}
        body = {"number": dest, "text": str(text or "")}

        try:
            async with httpx.AsyncClient(timeout=_SEND_TIMEOUT_S) as client:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.error(
                "EvolutionWhatsApp._send_text: errore di rete verso %s: %s",
                url,
                exc,
            )
            return {"error": str(exc)}

        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}

        if resp.status_code >= 400:
            logger.error(
                "EvolutionWhatsApp._send_text: HTTP %s instance=%s %s=%s body=%s",
                resp.status_code,
                self._instance,
                label,
                dest,
                data,
            )
            if isinstance(data, dict):
                data.setdefault("error", f"HTTP {resp.status_code}")
                return data
            return {"error": f"HTTP {resp.status_code}", "body": data}

        return data if isinstance(data, dict) else {"response": data}

    async def send_message(self, *, to_number: str, text: str) -> dict[str, Any]:
        number = _normalize_to_number(to_number)
        if not number:
            err = "numero destinatario vuoto o non valido"
            logger.error("EvolutionWhatsApp.send_message: %s", err)
            return {"error": err}
        return await self._send_text(recipient=number, text=text, label="number")

    async def send_group_message(self, *, group_jid: str, text: str) -> dict[str, Any]:
        """Invia testo a un gruppo WhatsApp (JID tipo 120363...@g.us)."""
        jid = str(group_jid or "").strip()
        if not jid:
            return {"error": "group_jid vuoto"}
        if "@" not in jid:
            jid = f"{jid}@g.us"
        return await self._send_text(recipient=jid, text=text, label="group_jid")

    async def notify_appointment_to_group(
        self,
        *,
        group_jid: str,
        agency_name: str,
        client_name: str,
        client_phone: str,
        slot_label: str,
        public_url: str | None = None,
        meet_link: str | None = None,
    ) -> dict[str, Any]:
        """Notifica al gruppo interno agenzia dopo conferma appuntamento."""
        lines = [
            "Nuovo appuntamento confermato!",
            f"Agenzia: {(agency_name or '').strip() or '—'}",
            f"Cliente: {(client_name or '').strip() or '—'}",
            f"Telefono: {(client_phone or '').strip() or '—'}",
            f"Quando: {(slot_label or '').strip() or '—'}",
        ]
        if public_url:
            lines.append(f"Dettagli: {public_url}")
        if meet_link:
            lines.append(f"Meet: {meet_link}")
        return await self.send_group_message(group_jid=group_jid, text="\n".join(lines))

    async def send_confirmation(
        self,
        *,
        to_number: str,
        nome: str = "",
        giorno: str = "",
        ora: str = "",
        public_url: str = "",
        agency_phone: str = "",
        agency_name: str = "",
        slot_label: str = "",
        agent_name: str = "il consulente",
        when_label: str = "",
        closer_url: str | None = None,
    ) -> dict[str, Any]:
        when = (when_label or "").strip()
        if not when and giorno:
            when = f"{giorno} alle {ora}" if ora else giorno
        display_name = (nome or "").strip() or "Cliente"

        if when:
            lines = [
                f"Ciao {display_name}!",
                "Il tuo appuntamento è confermato:",
                when,
            ]
            if public_url:
                lines.append(f"Dettagli: {public_url}")
            name = (agency_name or "").strip()
            if name:
                lines.append(name)
            if agency_phone:
                lines.append(f"Telefono: {agency_phone}")
            if closer_url:
                lines.append(f"Il tuo consulente: {closer_url}")
            text = "\n".join(lines)
        else:
            agent_it = agent_name
            if agent_name == "il titolare":
                agent_it = "il titolare dell'agenzia"
            text = (
                "Appuntamento confermato!\n"
                f"{slot_label or 'appuntamento confermato'}\n"
                f"Ti aspettiamo per la chiamata telefonica con {agent_it}.\n"
            )
            if public_url:
                text += f"Dettagli: {public_url}\n"
            text += "A presto!"
        return await self.send_message(to_number=to_number, text=text)

    async def send_sara_booking_confirmation(
        self,
        *,
        to_number: str,
        nome: str = "",
        when_label: str = "",
        public_url: str = "",
        closer_url: str | None = None,
        closer_nome: str = "",
    ) -> dict[str, Any]:
        """Conferma appuntamento Sara: senza link Meet (arriva 2h prima)."""
        display_name = (nome or "").strip() or "Cliente"
        when = (when_label or "").strip()
        consulente = (closer_nome or "").strip()
        lines = [
            f"Ciao {display_name}!",
            "Appuntamento fissato con Evolution Media.",
        ]
        if when:
            lines.append(f"Video riunione: {when}")
        else:
            lines.append("Video riunione confermata.")
        if consulente:
            lines.append(f"Consulente: {consulente}")
        lines.append(
            "Circa 2 ore prima ti invieremo qui su WhatsApp il link Google Meet."
        )
        if public_url:
            lines.append(f"Riepilogo: {public_url}")
        elif closer_url:
            lines.append(f"Info consulente: {closer_url}")
        lines.append("A presto!")
        return await self.send_message(to_number=to_number, text="\n".join(lines))

    async def send_meet_link_reminder(
        self,
        *,
        to_number: str,
        nome: str = "",
        when_label: str = "",
        meet_url: str = "",
    ) -> dict[str, Any]:
        """Link Google Meet ~2 ore prima della video riunione."""
        display_name = (nome or "").strip() or "Cliente"
        lines = [
            f"Ciao {display_name}!",
            "Mancano circa 2 ore alla tua video riunione con Evolution Media",
        ]
        if when_label:
            lines[-1] += f" ({when_label})"
        lines[-1] += "."
        if meet_url:
            lines.append(f"Link Google Meet: {meet_url}")
        lines.append("A tra poco!")
        return await self.send_message(to_number=to_number, text="\n".join(lines))
