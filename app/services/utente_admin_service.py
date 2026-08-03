"""CRUD nutrizionisti (tenant) per super admin."""

from __future__ import annotations

from dataclasses import dataclass

from werkzeug.security import generate_password_hash

from app.billing.plans import VALID_PLANS, normalize_plan
from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import db
from app.services.utente_service import find_utente_by_phone
from app.utils.helpers import normalize_phone


class UtenteAdminError(ValueError):
    pass


@dataclass(frozen=True)
class NutrizionistaCreate:
    nome: str
    cognome: str
    telefono: str
    email: str
    password: str
    attivo: bool = True
    plan: str = "starter"


def list_nutrizionisti() -> list[Utente]:
    return (
        Utente.query.filter_by(ruolo=UtenteRuolo.NUTRIZIONISTA.value)
        .order_by(Utente.creato_il.desc())
        .all()
    )


def create_nutrizionista(data: NutrizionistaCreate, *, creato_da: int) -> Utente:
    nome = (data.nome or "").strip()
    cognome = (data.cognome or "").strip()
    email = (data.email or "").strip().lower()
    telefono = normalize_phone(data.telefono or "")
    password = data.password or ""

    if not nome or not cognome:
        raise UtenteAdminError("Nome e cognome obbligatori")
    if not email or "@" not in email:
        raise UtenteAdminError("Email non valida")
    if len(telefono) < 9:
        raise UtenteAdminError("Telefono non valido")
    if len(password) < 8:
        raise UtenteAdminError("Password minimo 8 caratteri")

    if Utente.query.filter_by(email=email).first():
        raise UtenteAdminError("Email già in uso")
    if find_utente_by_phone(telefono):
        raise UtenteAdminError("Telefono già in uso")

    plan_raw = (data.plan or "").strip().lower()
    if plan_raw and plan_raw not in VALID_PLANS:
        raise UtenteAdminError("Piano non valido")
    plan = normalize_plan(data.plan)

    row = Utente(
        nome=nome[:100],
        cognome=cognome[:100],
        email=email[:255],
        telefono=telefono,
        ruolo=UtenteRuolo.NUTRIZIONISTA.value,
        password_hash=generate_password_hash(password),
        creato_da=creato_da,
        attivo=bool(data.attivo),
        plan=plan,
        subscription_status="none",
    )
    db.session.add(row)
    db.session.commit()
    return row


def set_nutrizionista_plan(utente_id: int, plan: str) -> Utente:
    """Imposta piano (es. Enterprise offline da super-admin)."""
    row = Utente.query.filter_by(
        id=utente_id, ruolo=UtenteRuolo.NUTRIZIONISTA.value
    ).first()
    if row is None:
        raise UtenteAdminError("Utente non trovato")
    key = (plan or "").strip().lower()
    if key not in VALID_PLANS:
        raise UtenteAdminError("Piano non valido")
    row.plan = key
    db.session.commit()
    return row


def toggle_nutrizionista(utente_id: int) -> Utente:
    row = Utente.query.filter_by(
        id=utente_id, ruolo=UtenteRuolo.NUTRIZIONISTA.value
    ).first()
    if row is None:
        raise UtenteAdminError("Utente non trovato")
    row.attivo = not bool(row.attivo)
    db.session.commit()
    return row
