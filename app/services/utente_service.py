"""Provisioning e lookup utenti (super_admin / nutrizionista)."""

from __future__ import annotations

import logging
import os
import re

from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import db
from app.utils.helpers import normalize_phone

logger = logging.getLogger(__name__)


def _split_admin_name(admin_name: str) -> tuple[str, str]:
    parts = (admin_name or "Admin").strip().split(None, 1)
    nome = parts[0] if parts else "Admin"
    cognome = parts[1] if len(parts) > 1 else "Nutrizionista"
    return nome[:100], cognome[:100]


def _synthetic_email(phone: str, prefix: str = "admin") -> str:
    digits = re.sub(r"\D+", "", phone or "") or prefix
    return f"{prefix}+{digits}@mynutriapp.local"


def find_utente_by_phone(telefono: str) -> Utente | None:
    phone = normalize_phone(telefono or "")
    if not phone:
        return None
    row = Utente.query.filter_by(telefono=phone).first()
    if row:
        return row
    for candidate in Utente.query.filter(Utente.telefono.isnot(None)).all():
        if normalize_phone(candidate.telefono or "") == phone:
            return candidate
    return None


def ensure_super_admin() -> int:
    """Garantisce un unico super_admin da ADMIN_* in .env. Ritorna id."""
    from app.utils.db_schema import ensure_multi_tenant_schema, finalize_multi_tenant_constraints

    ensure_multi_tenant_schema()

    phone = normalize_phone(os.getenv("ADMIN_PHONE", "") or "")
    password_hash = os.getenv("ADMIN_PASSWORD_HASH") or ""
    name = (os.getenv("ADMIN_NAME") or "Super Admin").strip()

    if not phone or not password_hash:
        raise RuntimeError("ADMIN_PHONE e ADMIN_PASSWORD_HASH obbligatori per seed super_admin")

    existing = (
        Utente.query.filter_by(ruolo=UtenteRuolo.SUPER_ADMIN.value).order_by(Utente.id.asc()).first()
    )
    if existing is None:
        existing = find_utente_by_phone(phone)

    nome, cognome = _split_admin_name(name)
    email = _synthetic_email(phone, prefix="superadmin")

    if existing is None:
        # evita collisione email
        if Utente.query.filter_by(email=email).first() is not None:
            email = f"superadmin+{Utente.query.count() + 1}@mynutriapp.local"
        existing = Utente(
            nome=nome,
            cognome=cognome,
            email=email,
            telefono=phone,
            ruolo=UtenteRuolo.SUPER_ADMIN.value,
            password_hash=password_hash,
            attivo=True,
        )
        db.session.add(existing)
        db.session.commit()
        logger.info("Creato super_admin id=%s telefono=%s", existing.id, phone)
    else:
        existing.ruolo = UtenteRuolo.SUPER_ADMIN.value
        existing.password_hash = password_hash
        existing.attivo = True
        if phone and not existing.telefono:
            existing.telefono = phone
        if nome:
            existing.nome = nome
        if cognome:
            existing.cognome = cognome
        db.session.commit()
        logger.info("Aggiornato super_admin id=%s", existing.id)

    # Tenant legacy per pazienti orfani (non assegnare pazienti al super_admin)
    tenant_id = _ensure_legacy_tenant(existing.id)
    finalize_multi_tenant_constraints(tenant_id or existing.id)
    return int(existing.id)


def _ensure_legacy_tenant(super_admin_id: int) -> int | None:
    """Se esistono pazienti senza nutrizionista, crea un nutrizionista legacy e ritorna id."""
    from app.models.models import Patient

    orphans = Patient.query.filter(Patient.nutrizionista_id.is_(None)).count()
    # anche se colonna già NOT NULL ma vogliamo un tenant dedicato
    has_patients = Patient.query.count() > 0
    if not orphans and not has_patients:
        return None

    legacy = (
        Utente.query.filter_by(
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            email="legacy@mynutriapp.local",
        ).first()
    )
    if legacy is None:
        # riusa primo nutrizionista se già creato dalla UI
        legacy = (
            Utente.query.filter_by(ruolo=UtenteRuolo.NUTRIZIONISTA.value)
            .order_by(Utente.id.asc())
            .first()
        )
    if legacy is None:
        legacy = Utente(
            nome="Staging",
            cognome="Tenant",
            email="legacy@mynutriapp.local",
            telefono=None,
            ruolo=UtenteRuolo.NUTRIZIONISTA.value,
            password_hash=os.getenv("ADMIN_PASSWORD_HASH") or "!",
            creato_da=super_admin_id,
            attivo=True,
        )
        db.session.add(legacy)
        db.session.commit()
        logger.info("Creato nutrizionista legacy id=%s per backfill pazienti", legacy.id)
    return int(legacy.id)


def ensure_admin_utente(
    *,
    telefono: str | None = None,
    admin_name: str | None = None,
) -> int:
    """Compat: ritorna id super_admin (niente fallback al primo utente attivo)."""
    return ensure_super_admin()


def ensure_session_utente_id() -> int | None:
    """Se admin/super senza utente_id in sessione, lo provvede e lo salva."""
    from flask import session

    existing = session.get("utente_id")
    if existing:
        return int(existing)
    if session.get("role") not in ("admin", "super_admin", "nutrizionista"):
        return None
    if session.get("role") == "super_admin":
        uid = ensure_super_admin()
    else:
        uid = session.get("utente_id")
        if not uid:
            return None
        return int(uid)
    session["utente_id"] = uid
    session.modified = True
    return uid
