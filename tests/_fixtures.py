"""Helper comuni per test SQLite multi-tenant."""

from __future__ import annotations

from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import db


def make_nutrizionista(
    *,
    email: str = "test-nutri@ex.com",
    nome: str = "Nutri",
    cognome: str = "Test",
) -> Utente:
    existing = Utente.query.filter_by(email=email).first()
    if existing is not None:
        return existing
    row = Utente(
        nome=nome,
        cognome=cognome,
        email=email,
        ruolo=UtenteRuolo.NUTRIZIONISTA.value,
        attivo=True,
        plan="enterprise",
    )
    db.session.add(row)
    db.session.flush()
    return row
