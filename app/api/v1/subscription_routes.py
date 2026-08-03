"""Abbonamento / uso piano del nutrizionista (session)."""

from __future__ import annotations

from flask import session

from app.api.v1.errors import api_error
from app.services.licensing_service import get_subscription_usage
from app.utils.tenant import current_utente_id


def register_subscription_routes(bp):
    @bp.get("/subscription")
    def subscription():
        if session.get("role") != "nutrizionista":
            return api_error(
                "Accesso riservato al nutrizionista",
                code="unauthorized",
                status=401,
            )
        user_id = current_utente_id()
        if not user_id:
            return api_error(
                "Accesso riservato al nutrizionista",
                code="unauthorized",
                status=401,
            )
        return get_subscription_usage(int(user_id)), 200
