"""Lifecycle stato cliente (provvisorio → attivo / non_attivo)."""

from __future__ import annotations

import secrets
from typing import List, Optional

from werkzeug.security import generate_password_hash

from app.models.models import Appuntamento, Patient


STATI_CLIENTE = ("provvisorio", "attivo", "non_attivo")

LABEL_STATO_CLIENTE = {
    "provvisorio": "Provvisorio",
    "attivo": "Attivo",
    "non_attivo": "Non attivo",
}


def crea_paziente_provvisorio(
    nome: str,
    cognome: str,
    telefono: str,
    altezza_cm: Optional[int] = None,
    peso_iniziale=None,
) -> Patient:
    """Crea un paziente minimale da prenotazione pubblica (non può ancora accedere)."""
    return Patient(
        nome=nome.strip(),
        cognome=cognome.strip(),
        telefono=telefono.strip(),
        password_hash=generate_password_hash(secrets.token_urlsafe(32)),
        sesso=None,
        data_nascita=None,
        altezza_cm=altezza_cm,
        peso_iniziale=peso_iniziale,
        stato_cliente="provvisorio",
    )


def sync_stato_cliente_da_appuntamento(appuntamento: Appuntamento, nuovo_stato: str) -> None:
    """Allinea lo stato cliente quando l'appuntamento viene confermato o annullato.

    - Conferma → cliente attivo (se era provvisorio)
    - Annulla/rifiuta → cliente non attivo (solo se era ancora provvisorio)
    """
    paziente = appuntamento.patient
    if not paziente:
        return
    stato = getattr(paziente, "stato_cliente", None) or "attivo"
    if nuovo_stato == "confermato" and stato == "provvisorio":
        paziente.stato_cliente = "attivo"
    elif nuovo_stato == "annullato" and stato == "provvisorio":
        paziente.stato_cliente = "non_attivo"


def approva_paziente(paziente: Patient) -> Optional[Appuntamento]:
    """Approva un cliente provvisorio: diventa attivo e conferma l'appuntamento in attesa."""
    paziente.stato_cliente = "attivo"
    pending = (
        Appuntamento.query.filter_by(patient_id=paziente.id, stato="in_attesa")
        .order_by(Appuntamento.data_appuntamento.asc())
        .first()
    )
    if pending:
        pending.stato = "confermato"
    return pending


def rifiuta_paziente(paziente: Patient) -> List[Appuntamento]:
    """Rifiuta un cliente provvisorio: diventa non attivo e annulla gli appuntamenti in attesa."""
    paziente.stato_cliente = "non_attivo"
    pending = Appuntamento.query.filter_by(
        patient_id=paziente.id, stato="in_attesa"
    ).all()
    for app in pending:
        app.stato = "annullato"
    return pending
