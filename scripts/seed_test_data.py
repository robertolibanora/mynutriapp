#!/usr/bin/env python3
"""
Popola il database MyNutriApp con dati di test.

Uso:
    python scripts/seed_test_data.py
    python scripts/seed_test_data.py --reset   # svuota e ripopola
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
    Listino,
    MisureAntropometriche,
    Patient,
    Progresso,
    SlotDisponibilita,
    Vendita,
    db,
)
from app.utils.encryption import encrypt_field

TEST_PASSWORD = "test123"


def clear_test_data() -> None:
    for model in (
        Appuntamento,
        Vendita,
        MisureAntropometriche,
        ComposizioneCorporea,
        Progresso,
        Documento,
        Dieta,
        Allenamento,
        Patient,
        SlotDisponibilita,
        Listino,
    ):
        db.session.query(model).delete()
    db.session.commit()


def seed() -> None:
    today = date.today()
    now = datetime.now()

    listino_items = [
        Listino(
            nome_prodotto="Dieta personalizzata 3 mesi",
            categoria="nutrizione",
            durata_mesi=3,
            check_inclusi=2,
            prezzo=249.00,
            note="Include 2 controlli nutrizionista",
            attivo=True,
        ),
        Listino(
            nome_prodotto="Piano allenamento 3 mesi",
            categoria="allenamento",
            durata_mesi=3,
            check_inclusi=1,
            prezzo=199.00,
            note="Programma strength + cardio",
            attivo=True,
        ),
        Listino(
            nome_prodotto="Pacchetto completo 6 mesi",
            categoria="completo",
            durata_mesi=6,
            check_inclusi=4,
            prezzo=699.00,
            note="Dieta + allenamento + check mensili",
            attivo=True,
        ),
        Listino(
            nome_prodotto="Sessione 1-to-1",
            categoria="1to1",
            durata_mesi=1,
            check_inclusi=0,
            prezzo=60.00,
            note="Singola seduta in studio",
            attivo=True,
        ),
    ]
    db.session.add_all(listino_items)
    db.session.flush()

    patients_data = [
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
    ]

    patients: list[Patient] = []
    pwd_hash = generate_password_hash(TEST_PASSWORD)

    for data in patients_data:
        p = Patient(
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
        )
        db.session.add(p)
        patients.append(p)

    db.session.flush()

    vendite: list[Vendita] = []
    vendite_specs = [
        (0, 0, 0, "carta", 249.00),
        (1, 1, -15, "bonifico", 169.15),
        (2, 2, 0, "contanti", 699.00),
        (3, 0, 10, "carta", 224.10),
    ]
    for i, (p_idx, l_idx, sconto, metodo, importo) in enumerate(vendite_specs):
        v = Vendita(
            patient_id=patients[p_idx].id,
            listino_id=listino_items[l_idx].id,
            data_acquisto=now - timedelta(days=30 * (i + 1)),
            data_inizio=today - timedelta(days=25 * (i + 1)),
            metodo_pagamento=metodo,
            sconto=sconto,
            importo_finale=importo,
            stato="pagato",
            note="Vendita test seed",
        )
        db.session.add(v)
        vendite.append(v)

    db.session.flush()

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

    appuntamenti_specs = [
        (0, 0, "check", "confermato", 3),
        (1, 1, "rinnovo_dieta", "completato", -7),
        (2, 2, "allenamento_1to1", "in_attesa", 5),
        (3, 3, "check", "confermato", 10),
        (0, None, "altro", "in_attesa", 14),
    ]
    for p_idx, v_idx, tipo, stato, days_ahead in appuntamenti_specs:
        db.session.add(
            Appuntamento(
                patient_id=patients[p_idx].id,
                vendita_id=vendite[v_idx].id if v_idx is not None else None,
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

    for day in (2, 4, 9, 11, 16):
        slot_dt = (now + timedelta(days=day)).replace(hour=9, minute=0, second=0, microsecond=0)
        db.session.add(
            SlotDisponibilita(
                data_ora=slot_dt,
                attivo=True,
                note="Slot test disponibile",
            )
        )
        db.session.add(
            SlotDisponibilita(
                data_ora=slot_dt.replace(hour=15, minute=30),
                attivo=True,
                note="Slot pomeriggio test",
            )
        )

    db.session.commit()

    print("✅ Database popolato con dati di test")
    print(f"   Pazienti: {len(patients)}")
    print(f"   Listino: {len(listino_items)} prodotti")
    print(f"   Vendite: {len(vendite)}")
    print(f"   Password pazienti: {TEST_PASSWORD}")
    print()
    print("   Account pazienti (telefono / password):")
    for p in patients:
        print(f"   - {p.nome} {p.cognome}: {p.telefono} / {TEST_PASSWORD}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed dati di test MyNutriApp")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Svuota le tabelle principali prima di inserire i dati",
    )
    args = parser.parse_args()

    with app.app_context():
        if args.reset or Patient.query.count() > 0:
            if Patient.query.count() > 0 and not args.reset:
                print("⚠️  Il database contiene già dati. Usa --reset per svuotare e ripopolare.")
                return
            print("🗑️  Pulizia dati esistenti...")
            clear_test_data()
        seed()


if __name__ == "__main__":
    main()
