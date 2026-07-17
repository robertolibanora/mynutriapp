#!/usr/bin/env python3
"""
Popola il database MyNutriApp con dati di test.

Uso:
    python scripts/seed_test_data.py            # additivo: non cancella, salta telefoni già presenti
    python scripts/seed_test_data.py --reset    # svuota e ripopola
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

from wsgi import app
from app.models.models import (
    Allenamento,
    Appuntamento,
    ComposizioneCorporea,
    Dieta,
    Documento,
    MisureAntropometriche,
    Patient,
    Progresso,
    SlotDisponibilita,
    db,
)
from app.utils.encryption import encrypt_field

TEST_PASSWORD = "test123"

PATIENTS_DATA = [
    {
        "nome": "Maria",
        "cognome": "Rossi",
        "sesso": "F",
        "data_nascita": date(1990, 3, 15),
        "telefono": "3401234567",
        "altezza_cm": 165,
        "peso_iniziale": 72.5,
        "intolleranze": "Lattosio",
        "cibi_da_ev": "Fritti, bibite zuccherate",
        "patologie": "Ipotiroidismo in terapia",
        "allenamenti_descr": "3x settimana palestra + camminata",
        "esami_biochimici": "Glicemia 92 mg/dl, Colesterolo totale 195",
    },
    {
        "nome": "Luca",
        "cognome": "Bianchi",
        "sesso": "M",
        "data_nascita": date(1985, 7, 22),
        "telefono": "3409876543",
        "altezza_cm": 178,
        "peso_iniziale": 88.0,
        "intolleranze": None,
        "cibi_da_ev": "Alcol, dolci serali",
        "patologie": None,
        "allenamenti_descr": "Crossfit 4x settimana",
        "esami_biochimici": "Emocromo nella norma",
    },
    {
        "nome": "Giulia",
        "cognome": "Verdi",
        "sesso": "F",
        "data_nascita": date(1998, 11, 8),
        "telefono": "3471122334",
        "altezza_cm": 170,
        "peso_iniziale": 63.0,
        "intolleranze": "Glutine",
        "cibi_da_ev": "Prodotti industriali",
        "patologie": "Celiachia diagnosticata",
        "allenamenti_descr": "Yoga 2x + nuoto 1x",
        "esami_biochimici": "Ferritina 45 ng/ml",
    },
    {
        "nome": "Marco",
        "cognome": "Ferrari",
        "sesso": "M",
        "data_nascita": date(1978, 1, 30),
        "telefono": "3334455667",
        "altezza_cm": 182,
        "peso_iniziale": 95.5,
        "intolleranze": None,
        "cibi_da_ev": "Fast food",
        "patologie": "Ipertensione lieve",
        "allenamenti_descr": "Camminata quotidiana 30 min",
        "esami_biochimici": "PA 135/85, LDL 130",
    },
    {
        "nome": "Sofia",
        "cognome": "Neri",
        "sesso": "F",
        "data_nascita": date(1995, 6, 12),
        "telefono": "3395566778",
        "altezza_cm": 168,
        "peso_iniziale": 68.0,
        "intolleranze": "Nichel",
        "cibi_da_ev": "Cibi in scatola",
        "patologie": None,
        "allenamenti_descr": "Pilates 3x settimana",
        "esami_biochimici": "TSH 2.1 mUI/L",
    },
    {
        "nome": "Andrea",
        "cognome": "Romano",
        "sesso": "M",
        "data_nascita": date(1992, 9, 5),
        "telefono": "3386677889",
        "altezza_cm": 175,
        "peso_iniziale": 82.0,
        "intolleranze": None,
        "cibi_da_ev": "Snack salati",
        "patologie": None,
        "allenamenti_descr": "Corsa 3x + pesi 2x",
        "esami_biochimici": "Vitamina D 28 ng/ml",
    },
]


def clear_test_data() -> None:
    for model in (
        Appuntamento,
        MisureAntropometriche,
        ComposizioneCorporea,
        Progresso,
        Documento,
        Dieta,
        Allenamento,
        Patient,
        SlotDisponibilita,
    ):
        db.session.query(model).delete()
    db.session.commit()


def _create_patient(data: dict, pwd_hash: str) -> Patient:
    return Patient(
        nome=data["nome"],
        cognome=data["cognome"],
        sesso=data["sesso"],
        data_nascita=data["data_nascita"],
        telefono=data["telefono"],
        password_hash=pwd_hash,
        altezza_cm=data["altezza_cm"],
        peso_iniziale=data["peso_iniziale"],
        intolleranze=encrypt_field(data["intolleranze"]) if data["intolleranze"] else None,
        cibi_da_ev=data["cibi_da_ev"],
        patologie=encrypt_field(data["patologie"]) if data["patologie"] else None,
        allenamenti_descr=data["allenamenti_descr"],
        esami_biochimici=encrypt_field(data["esami_biochimici"]) if data["esami_biochimici"] else None,
        stato_cliente="attivo",
    )


def _seed_related_for_patients(patients: list[Patient], today: date, now: datetime) -> None:
    for i, p in enumerate(patients):
        db.session.add(
            Dieta(
                patient_id=p.id,
                data_inizio=today - timedelta(days=14),
                data_fine=today + timedelta(days=75),
                pdf_path=f"static/uploads/diete/dieta_test_{p.id}.pdf",
                kcal=1800 + i * 100,
                carbo=180 + i * 10,
                proteine=120 + i * 5,
                grassi=55 + i * 3,
                note=f"Piano alimentare test per {p.nome}",
            )
        )
        db.session.add(
            Allenamento(
                patient_id=p.id,
                data_inizio=today - timedelta(days=10),
                data_fine=today + timedelta(days=80),
                pdf_path=f"static/uploads/allenamenti/allenamento_test_{p.id}.pdf",
                note=f"Scheda allenamento test per {p.nome}",
            )
        )

    if not patients:
        return

    appuntamenti_specs = [
        (0, "check", "confermato", 3),
        (1 % len(patients), "rinnovo_dieta", "completato", -7),
        (2 % len(patients), "allenamento_1to1", "in_attesa", 5),
        (3 % len(patients), "check", "confermato", 10),
        (0, "altro", "in_attesa", 14),
    ]
    for p_idx, tipo, stato, days_ahead in appuntamenti_specs:
        db.session.add(
            Appuntamento(
                patient_id=patients[p_idx].id,
                created_by="Enrico",
                data_appuntamento=now + timedelta(days=days_ahead, hours=10),
                tipo=tipo,
                stato=stato,
                note="Appuntamento di test",
                promemoria_inviato=False,
            )
        )

    for week, p in enumerate(patients[:3]):
        for w in range(4):
            check_date = today - timedelta(weeks=3 - w)
            peso = float(p.peso_iniziale) - (w * 0.6) - week * 0.3
            prog = Progresso(
                patient_id=p.id,
                data_check=check_date,
                tipo_check="paziente" if w % 2 == 0 else "nutrizionista",
                peso_settimanale=peso,
                frequenza_allenamenti=f"{2 + w} allenamenti / settimana",
                aderenza=7 + w,
                check_richiesta=w == 3,
            )
            db.session.add(prog)
            db.session.flush()

            db.session.add(
                MisureAntropometriche(
                    patient_id=p.id,
                    progresso_id=prog.id,
                    data_misurazione=check_date,
                    circonferenza_vita=88 - w,
                    circonferenza_fianchi=102 - w,
                    circonferenza_coscia=58 - w * 0.5,
                    plica_addominale=22 - w,
                    note="Misurazione test",
                )
            )
            db.session.add(
                ComposizioneCorporea(
                    patient_id=p.id,
                    progresso_id=prog.id,
                    data_misurazione=check_date,
                    grasso_corporeo=28 - w - week,
                    massa_muscolare=45 + w * 0.2,
                    grasso_viscerale=10 - w * 0.3,
                    tbw=52 + w * 0.1,
                    tasso_metabolico_basale=1600 + week * 20,
                    bmi=round(peso / ((p.altezza_cm / 100) ** 2), 1),
                    note="BIA test",
                )
            )

    for i, p in enumerate(patients):
        db.session.add(
            Documento(
                patient_id=p.id,
                tipo="analisi" if i % 2 == 0 else "referto",
                file_path=f"static/uploads/documenti/doc_test_{p.id}.pdf",
                descrizione=f"Documento clinico test - {p.cognome}",
            )
        )


def _seed_slots(now: datetime) -> int:
    created = 0
    for day in (2, 4, 9, 11, 16):
        for hour, minute, note in (
            (9, 0, "Slot test disponibile"),
            (15, 30, "Slot pomeriggio test"),
        ):
            slot_dt = (now + timedelta(days=day)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            if SlotDisponibilita.query.filter_by(data_ora=slot_dt).first():
                continue
            db.session.add(
                SlotDisponibilita(
                    data_ora=slot_dt,
                    attivo=True,
                    note=note,
                )
            )
            created += 1
    return created


def seed(*, additive: bool = True) -> None:
    today = date.today()
    now = datetime.now()
    pwd_hash = generate_password_hash(TEST_PASSWORD)

    patients: list[Patient] = []
    skipped: list[str] = []

    for data in PATIENTS_DATA:
        existing = Patient.query.filter_by(telefono=data["telefono"]).first()
        if existing:
            skipped.append(f"{data['nome']} {data['cognome']} ({data['telefono']})")
            continue
        p = _create_patient(data, pwd_hash)
        db.session.add(p)
        patients.append(p)

    if patients:
        db.session.flush()
        _seed_related_for_patients(patients, today, now)

    slots_created = _seed_slots(now)
    db.session.commit()

    if patients:
        print("✅ Dati di test inseriti (senza cancellare i record esistenti)" if additive else "✅ Database popolato con dati di test")
        print(f"   Nuovi pazienti: {len(patients)}")
        print(f"   Password pazienti: {TEST_PASSWORD}")
        print()
        print("   Account pazienti (telefono / password):")
        for p in patients:
            print(f"   - {p.nome} {p.cognome}: {p.telefono} / {TEST_PASSWORD}")
    else:
        print("ℹ️  Nessun nuovo paziente da inserire (telefoni già presenti).")

    if skipped:
        print(f"   Saltati (già presenti): {len(skipped)}")
        for s in skipped:
            print(f"   - {s}")

    print(f"   Slot disponibilità creati: {slots_created}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed dati di test MyNutriApp")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Svuota le tabelle principali prima di inserire i dati",
    )
    args = parser.parse_args()

    with app.app_context():
        if args.reset:
            print("🗑️  Pulizia dati esistenti...")
            clear_test_data()
            seed(additive=False)
        else:
            seed(additive=True)


if __name__ == "__main__":
    main()
