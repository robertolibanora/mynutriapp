"""Progressi paziente: lista, dettaglio, create, foto."""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.config.config import Config
from app.models.models import (
    ComposizioneCorporea,
    MisureAntropometriche,
    Progresso,
    db,
)


def list_for_patient(patient_id: int) -> list[Progresso]:
    return (
        Progresso.query.filter_by(patient_id=patient_id)
        .order_by(Progresso.data_check.desc())
        .all()
    )


def get_latest_for_patient(patient_id: int) -> Optional[Progresso]:
    return (
        Progresso.query.filter_by(patient_id=patient_id)
        .order_by(Progresso.data_check.desc())
        .first()
    )


def get_for_patient(progress_id: int, patient_id: int) -> Optional[Progresso]:
    progresso = Progresso.query.filter_by(id=progress_id).first()
    if progresso is None or progresso.patient_id != patient_id:
        return None
    return progresso


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_dt(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep="T", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _iso_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def resolve_photo_path(progresso: Progresso) -> Optional[str]:
    """Risolve path filesystem della foto; None se assente o non trovata."""
    if not progresso.foto_path:
        return None
    raw = progresso.foto_path
    candidates = []
    if os.path.isabs(raw):
        candidates.append(raw)
    else:
        candidates.append(os.path.join(str(Config.BASE_DIR), raw))
        candidates.append(os.path.join(str(Config.BASE_DIR), "static", raw))
        if not raw.startswith("static" + os.sep) and not raw.startswith("static/"):
            candidates.append(os.path.join(str(Config.BASE_DIR), "static", raw))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def serialize_misure(misure: Optional[MisureAntropometriche]) -> Optional[dict[str, Any]]:
    if misure is None:
        return None
    return {
        "data_misurazione": _iso_date(misure.data_misurazione),
        "circonferenza_braccio": _num(misure.circonferenza_braccio),
        "circonferenza_spalle": _num(misure.circonferenza_spalle),
        "circonferenza_torace": _num(misure.circonferenza_torace),
        "circonferenza_vita": _num(misure.circonferenza_vita),
        "circonferenza_fianchi": _num(misure.circonferenza_fianchi),
        "circonferenza_coscia": _num(misure.circonferenza_coscia),
        "circonferenza_polpaccio": _num(misure.circonferenza_polpaccio),
        "plica_addominale": _num(misure.plica_addominale),
        "plica_tricipitale": _num(misure.plica_tricipitale),
        "plica_soprailiaca": _num(misure.plica_soprailiaca),
        "plica_sottoscapolare": _num(misure.plica_sottoscapolare),
        "plica_cutanea_coscia": _num(misure.plica_cutanea_coscia),
        "note": misure.note,
    }


def serialize_composizione(
    composizione: Optional[ComposizioneCorporea],
) -> Optional[dict[str, Any]]:
    if composizione is None:
        return None
    return {
        "data_misurazione": _iso_date(composizione.data_misurazione),
        "grasso_corporeo": _num(composizione.grasso_corporeo),
        "massa_muscolare": _num(composizione.massa_muscolare),
        "grasso_viscerale": _num(composizione.grasso_viscerale),
        "tbw": _num(composizione.tbw),
        "tasso_metabolico_basale": composizione.tasso_metabolico_basale,
        "eta_metabolica": composizione.eta_metabolica,
        "punteggio_postura": composizione.punteggio_postura,
        "massa_ossea": _num(composizione.massa_ossea),
        "bmi": _num(composizione.bmi),
        "note": composizione.note,
    }


def serialize_summary(progresso: Progresso) -> dict[str, Any]:
    return {
        "id": progresso.id,
        "data_check": _iso_date(progresso.data_check),
        "tipo_check": progresso.tipo_check,
        "peso_settimanale": _num(progresso.peso_settimanale),
        "frequenza_allenamenti": progresso.frequenza_allenamenti,
        "aderenza": progresso.aderenza,
        "check_richiesta": bool(progresso.check_richiesta)
        if progresso.check_richiesta is not None
        else False,
        "has_foto": bool(progresso.foto_path),
        "created_at": _iso_dt(progresso.created_at),
    }


def serialize_detail(progresso: Progresso) -> dict[str, Any]:
    misure = None
    composizione = None
    if progresso.misure_antropometriche_rel:
        misure = progresso.misure_antropometriche_rel[0]
    if progresso.composizione_corporea_rel:
        composizione = progresso.composizione_corporea_rel[0]

    detail = serialize_summary(progresso)
    detail["misure"] = serialize_misure(misure)
    detail["composizione"] = serialize_composizione(composizione)
    return detail


class ProgressValidationError(ValueError):
    pass


def create_for_patient(
    patient_id: int,
    *,
    peso_settimanale: Any,
    frequenza_allenamenti: Optional[str] = None,
    aderenza: Any = None,
) -> Progresso:
    """Crea check paziente come route web (data_check=oggi, check_richiesta=True)."""
    if peso_settimanale is None or peso_settimanale == "":
        raise ProgressValidationError("peso_settimanale obbligatorio")
    try:
        peso = Decimal(str(peso_settimanale).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProgressValidationError("peso_settimanale non valido") from exc
    if peso <= 0 or peso > 400:
        raise ProgressValidationError("peso_settimanale non valido")

    aderenza_int = None
    if aderenza is not None and aderenza != "":
        try:
            aderenza_int = int(aderenza)
        except (TypeError, ValueError) as exc:
            raise ProgressValidationError("aderenza non valida") from exc
        if aderenza_int < 1 or aderenza_int > 10:
            raise ProgressValidationError("aderenza deve essere tra 1 e 10")

    freq = (frequenza_allenamenti or "").strip() or None

    nuovo = Progresso(
        patient_id=patient_id,
        data_check=date.today(),
        tipo_check="paziente",
        peso_settimanale=peso,
        frequenza_allenamenti=freq,
        aderenza=aderenza_int,
        check_richiesta=True,
    )
    db.session.add(nuovo)
    db.session.commit()
    return nuovo
