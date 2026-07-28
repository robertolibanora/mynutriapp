"""Provisioning nutrizionista admin (tabella utente) per ownership diario."""

from __future__ import annotations

import logging
import os
import re

from app.models.diario import Utente
from app.models.models import db
from app.utils.helpers import normalize_phone

logger = logging.getLogger(__name__)


def _split_admin_name(admin_name: str) -> tuple[str, str]:
    parts = (admin_name or "Admin").strip().split(None, 1)
    nome = parts[0] if parts else "Admin"
    cognome = parts[1] if len(parts) > 1 else "Nutrizionista"
    return nome[:100], cognome[:100]


def _synthetic_email(phone: str) -> str:
    digits = re.sub(r"\D+", "", phone or "") or "admin"
    return f"admin+{digits}@mynutriapp.local"


def ensure_admin_utente(
    *,
    telefono: str | None = None,
    admin_name: str | None = None,
) -> int:
    """Garantisce un record ``utente`` per l'admin e ne ritorna l'id.

    Cerca per telefono (ADMIN_PHONE); se assente crea la riga.
    """
    phone = normalize_phone(telefono or os.getenv("ADMIN_PHONE", "") or "")
    name = (admin_name if admin_name is not None else os.getenv("ADMIN_NAME", "MyNutriApp")).strip()

    nutr = None
    if phone:
        nutr = Utente.query.filter_by(telefono=phone).first()
        if nutr is None:
            # match anche se in DB c'è formato diverso
            for candidate in Utente.query.filter(Utente.telefono.isnot(None)).all():
                if normalize_phone(candidate.telefono or "") == phone:
                    nutr = candidate
                    break

    if nutr is None:
        nutr = Utente.query.filter_by(attivo=True).order_by(Utente.id.asc()).first()

    if nutr is not None:
        if not nutr.attivo:
            nutr.attivo = True
            db.session.commit()
        return int(nutr.id)

    nome, cognome = _split_admin_name(name)
    email = _synthetic_email(phone)
    # evita collisioni email uniche
    if Utente.query.filter_by(email=email).first() is not None:
        email = f"admin+{Utente.query.count() + 1}@mynutriapp.local"

    nutr = Utente(
        nome=nome,
        cognome=cognome,
        email=email,
        telefono=phone or None,
        attivo=True,
    )
    db.session.add(nutr)
    db.session.commit()
    logger.info("Creato utente nutrizionista admin id=%s email=%s", nutr.id, email)
    return int(nutr.id)


def ensure_session_utente_id() -> int | None:
    """Se admin senza utente_id in sessione, lo provvede e lo salva. Altrimenti None."""
    from flask import session

    existing = session.get("utente_id")
    if existing:
        return int(existing)
    if session.get("role") != "admin":
        return None
    uid = ensure_admin_utente()
    session["utente_id"] = uid
    session.modified = True
    return uid
