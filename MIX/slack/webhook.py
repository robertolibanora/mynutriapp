# ─────────────────────────────────────────────────────────
# SHARED PIECE — se correggi qui, propaga a tutte le istanze AgentMetrics
# ─────────────────────────────────────────────────────────
"""Slack Incoming Webhook per notifiche appuntamento."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from integrations.base import SlackNotifier

logger = logging.getLogger(__name__)


class SlackWebhookNotifier(SlackNotifier):
    slug = "slack_webhook"

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = (webhook_url or "").strip()
        if not self.webhook_url:
            raise ValueError("SLACK_WEBHOOK_URL vuoto")

    async def notify_appointment(
        self,
        *,
        agent_key: str,
        client_name: str,
        client_phone: str,
        slot_label: str,
        meet_link: str | None = None,
        call_id: str | None = None,
        public_url: str | None = None,
    ) -> dict[str, Any]:
        agent_label = (
            "Gloria — Immobiliare"
            if agent_key == "gloria"
            else "Sara — Evolution Media"
        )
        lines = [
            "*Nuovo appuntamento confermato!*",
            f"*Agente:* {agent_label}",
            f"*Cliente:* {client_name}",
            f"*Telefono:* {client_phone}",
            f"*Quando:* {slot_label}",
        ]
        if public_url:
            lines.append(f"*Pagina appuntamento:* {public_url}")
        if meet_link:
            lines.append(f"*Meet:* {meet_link}")
        if call_id:
            lines.append(f"*Call ID:* `{call_id}`")

        payload = {"text": "\n".join(lines)}

        async with httpx.AsyncClient() as client:
            r = await client.post(
                self.webhook_url,
                json=payload,
                timeout=10.0,
            )
        return {"ok": r.status_code == 200, "status": r.status_code, "payload": payload}
