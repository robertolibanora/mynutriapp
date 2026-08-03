"""Servizi GDPR: export portabilità, richiesta/esecuzione oblio, retention."""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.config.config import Config, get_full_path
from app.models.models import (
    Allenamento,
    Appuntamento,
    AuditLog,
    Dieta,
    DietPlan,
    Documento,
    Patient,
    Progresso,
    db,
)
from app.utils.audit import log_audit_event

logger = logging.getLogger(__name__)


class GdprError(Exception):
    """Errore dominio GDPR."""


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def apply_consents(
    patient: Patient,
    *,
    consenso_privacy: Optional[bool] = None,
    consenso_marketing: Optional[bool] = None,
) -> None:
    """Aggiorna consensi privacy/marketing con timestamp e versione policy."""
    now = datetime.utcnow()
    version = Config.PRIVACY_POLICY_VERSION
    if consenso_privacy is not None:
        patient.consenso_privacy = bool(consenso_privacy)
        patient.consenso_privacy_il = now if consenso_privacy else patient.consenso_privacy_il
        if consenso_privacy:
            patient.privacy_policy_version = version
    if consenso_marketing is not None:
        patient.consenso_marketing = bool(consenso_marketing)
        patient.consenso_marketing_il = now if consenso_marketing else None


def export_patient_data(patient: Patient) -> Dict[str, Any]:
    """Esporta i dati del paziente in struttura JSON (Art. 20)."""
    diete = [
        {
            "id": d.id,
            "data_inizio": _iso(d.data_inizio),
            "data_fine": _iso(d.data_fine),
            "note": d.note,
            "pdf_path": d.pdf_path,
        }
        for d in (patient.diete or [])
    ]
    plans = DietPlan.query.filter_by(patient_id=patient.id).all()
    diet_plans = [
        {
            "id": p.id,
            "title": p.title,
            "status": p.status,
            "goal": p.goal,
            "notes": p.notes,
            "created_at": _iso(getattr(p, "created_at", None)),
        }
        for p in plans
    ]
    allenamenti = [
        {
            "id": a.id,
            "data_inizio": _iso(a.data_inizio),
            "data_fine": _iso(a.data_fine),
            "note": a.note,
            "pdf_path": a.pdf_path,
        }
        for a in (patient.allenamenti or [])
    ]
    progressi = [
        {
            "id": pr.id,
            "data_check": _iso(pr.data_check),
            "tipo_check": pr.tipo_check,
            "peso_settimanale": float(pr.peso_settimanale) if pr.peso_settimanale is not None else None,
            "frequenza_allenamenti": pr.frequenza_allenamenti,
            "aderenza": pr.aderenza,
        }
        for pr in (patient.progressi or [])
    ]
    documenti = [
        {
            "id": doc.id,
            "tipo": doc.tipo,
            "descrizione": doc.descrizione,
            "data_upload": _iso(doc.data_upload),
            "file_path": doc.file_path,
        }
        for doc in (patient.documenti or [])
    ]
    appuntamenti = [
        {
            "id": ap.id,
            "data_appuntamento": _iso(ap.data_appuntamento),
            "tipo": ap.tipo,
            "stato": ap.stato,
            "note": ap.note,
        }
        for ap in (patient.appuntamenti or [])
    ]

    diary_entries = []
    for entry in getattr(patient, "diary_entries", None) or []:
        diary_entries.append(
            {
                "id": entry.id,
                "creato_il": _iso(getattr(entry, "creato_il", None) or getattr(entry, "created_at", None)),
                "stato": getattr(entry, "stato", None),
                "contenuto_json": getattr(entry, "contenuto_json", None),
            }
        )

    return {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "privacy_policy_version": patient.privacy_policy_version,
        "patient": {
            "id": patient.id,
            "nome": patient.nome,
            "cognome": patient.cognome,
            "telefono": patient.telefono,
            "email": patient.email,
            "sesso": patient.sesso,
            "data_nascita": _iso(patient.data_nascita),
            "altezza_cm": patient.altezza_cm,
            "peso_iniziale": float(patient.peso_iniziale) if patient.peso_iniziale is not None else None,
            "stato_cliente": patient.stato_cliente,
            "intolleranze": getattr(patient, "intolleranze_decrypted", None) or patient.intolleranze,
            "cibi_da_ev": patient.cibi_da_ev,
            "patologie": getattr(patient, "patologie_decrypted", None) or patient.patologie,
            "esami_biochimici": getattr(patient, "esami_biochimici_decrypted", None)
            or patient.esami_biochimici,
            "allenamenti_descr": patient.allenamenti_descr,
            "data_creazione": _iso(patient.data_creazione),
        },
        "consensi": {
            "privacy": bool(patient.consenso_privacy),
            "marketing": bool(patient.consenso_marketing),
            "registrazione": bool(patient.consenso_registrazione),
            "ai": bool(patient.consenso_ai),
            "privacy_il": _iso(patient.consenso_privacy_il),
            "marketing_il": _iso(patient.consenso_marketing_il),
            "aggiornato_il": _iso(patient.consenso_aggiornato_il),
        },
        "diete_pdf": diete,
        "diet_plans": diet_plans,
        "allenamenti": allenamenti,
        "progressi": progressi,
        "documenti": documenti,
        "appuntamenti": appuntamenti,
        "diario": diary_entries,
    }


def request_erasure(patient: Patient) -> None:
    """Registra richiesta di oblio (Art. 17)."""
    if patient.erasure_completed_at:
        raise GdprError("Oblio già completato per questo paziente")
    patient.erasure_requested_at = datetime.utcnow()
    log_audit_event(
        "ERASURE_REQUEST",
        "patient",
        patient.id,
        details={"nome": patient.nome, "cognome": patient.cognome},
    )


def _safe_remove_file(path: Optional[str]) -> None:
    if not path:
        return
    try:
        full = get_full_path(path) if not os.path.isabs(path) else path
        if os.path.exists(full):
            os.remove(full)
    except OSError as exc:
        logger.warning("Impossibile eliminare file %s: %s", path, exc)


def _purge_patient_files(patient: Patient) -> None:
    for dieta in list(patient.diete or []):
        _safe_remove_file(dieta.pdf_path)
    for allena in list(patient.allenamenti or []):
        _safe_remove_file(allena.pdf_path)
    for doc in list(patient.documenti or []):
        _safe_remove_file(doc.file_path)
    for pr in list(patient.progressi or []):
        if pr.foto_path:
            _safe_remove_file(os.path.join("static", pr.foto_path))
    for consultation in list(getattr(patient, "consultations", None) or []):
        recording = getattr(consultation, "audio_recording", None)
        if recording is not None:
            _safe_remove_file(getattr(recording, "path_file", None))
            recording.cancellato_il = datetime.utcnow()


def anonymize_patient(patient: Patient) -> None:
    """Anonimizza PII mantenendo shell per hold legale (retention_until)."""
    token = f"erased-{patient.id}"
    patient.nome = "Anonimizzato"
    patient.cognome = token
    patient.telefono = f"000{patient.id:07d}"[-10:]
    patient.email = None
    patient.password_hash = "!"  # non utilizzabile
    patient.sesso = None
    patient.data_nascita = None
    patient.altezza_cm = None
    patient.peso_iniziale = None
    patient.intolleranze = None
    patient.cibi_da_ev = None
    patient.patologie = None
    patient.esami_biochimici = None
    patient.allenamenti_descr = None
    patient.consenso_privacy = False
    patient.consenso_marketing = False
    patient.consenso_registrazione = False
    patient.consenso_ai = False
    patient.stato_cliente = "non_attivo"
    patient.erasure_completed_at = datetime.utcnow()


def purge_patient(patient: Patient, *, force_hard_delete: bool = False) -> str:
    """Esegue oblio: file + dati. Hard-delete se nessun hold, altrimenti anonimizza.

    Returns:
        'deleted' | 'anonymized'
    """
    _purge_patient_files(patient)
    log_audit_event(
        "ERASURE",
        "patient",
        patient.id,
        details={"mode": "start"},
    )

    hold = patient.retention_until
    if hold and hold > date.today() and not force_hard_delete:
        anonymize_patient(patient)
        db.session.commit()
        return "anonymized"

    patient_id = patient.id
    db.session.delete(patient)
    db.session.commit()
    log_audit_event(
        "ERASURE",
        "patient",
        patient_id,
        details={"mode": "hard_delete"},
    )
    db.session.commit()
    return "deleted"


def patients_due_for_retention_purge() -> List[Patient]:
    """Pazienti non_attivi oltre retention senza hold, o con erasure richiesta scaduta."""
    cutoff = datetime.utcnow() - timedelta(days=Config.PATIENT_DATA_RETENTION_DAYS)
    today = date.today()
    q = Patient.query.filter(
        db.or_(
            db.and_(
                Patient.erasure_requested_at.isnot(None),
                Patient.erasure_completed_at.is_(None),
                db.or_(Patient.retention_until.is_(None), Patient.retention_until <= today),
            ),
            db.and_(
                Patient.stato_cliente == "non_attivo",
                Patient.aggiornato_il < cutoff,
                db.or_(Patient.retention_until.is_(None), Patient.retention_until <= today),
            ),
            db.and_(
                Patient.erasure_completed_at.isnot(None),
                Patient.retention_until.isnot(None),
                Patient.retention_until <= today,
            ),
        )
    )
    return q.all()


def purge_audit_logs(dry_run: bool = False) -> int:
    cutoff = datetime.utcnow() - timedelta(days=Config.AUDIT_LOG_RETENTION_DAYS)
    q = AuditLog.query.filter(AuditLog.timestamp < cutoff)
    count = q.count()
    if not dry_run and count:
        q.delete(synchronize_session=False)
        db.session.commit()
    return count


def purge_old_audio(dry_run: bool = False) -> int:
    """Soft-delete audio consultation oltre AUDIO_RETENTION_DAYS."""
    try:
        from app.models.diario import AudioRecording
    except ImportError:
        return 0

    cutoff = datetime.utcnow() - timedelta(days=Config.AUDIO_RETENTION_DAYS)
    q = AudioRecording.query.filter(
        AudioRecording.cancellato_il.is_(None),
        AudioRecording.creato_il < cutoff,
    )
    rows = q.all()
    if dry_run:
        return len(rows)
    n = 0
    for rec in rows:
        _safe_remove_file(getattr(rec, "path_file", None))
        rec.cancellato_il = datetime.utcnow()
        n += 1
    if n:
        db.session.commit()
    return n


def run_retention_job(dry_run: bool = False) -> Dict[str, Any]:
    """Esegue purge retention: audio, pazienti, audit."""
    audio_n = purge_old_audio(dry_run=dry_run)
    patients = patients_due_for_retention_purge()
    purged_patients = 0
    anonymized = 0
    if not dry_run:
        for p in patients:
            mode = purge_patient(p)
            if mode == "deleted":
                purged_patients += 1
            else:
                anonymized += 1
    else:
        purged_patients = len(patients)

    audit_n = purge_audit_logs(dry_run=dry_run)
    return {
        "dry_run": dry_run,
        "audio_purged": audio_n,
        "patients_processed": purged_patients + anonymized if not dry_run else purged_patients,
        "patients_deleted": purged_patients if not dry_run else 0,
        "patients_anonymized": anonymized,
        "audit_deleted": audit_n,
    }


def export_as_json_bytes(patient: Patient) -> bytes:
    payload = export_patient_data(patient)
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
