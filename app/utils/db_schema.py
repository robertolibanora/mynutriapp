"""Piccoli upgrade schema SQL eseguiti al volo (senza Alembic)."""

import logging

from sqlalchemy import inspect, text

from app.models.models import db

logger = logging.getLogger(__name__)

_SEGRETARIO_DEVIAZIONE_OK = False
_NUTRITION_SCHEMA_OK = False
_FINANCE_REMOVED_OK = False

_AGENDA_SCHEMA_OK = False
_RICHIESTE_SCHEMA_OK = False
_PATIENT_STATO_OK = False


def ensure_finance_removed() -> None:
    """Rimuove tabelle/colonne del modulo finanziario (listino, vendite)."""
    global _FINANCE_REMOVED_OK
    if _FINANCE_REMOVED_OK:
        return
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        with db.engine.begin() as conn:
            if "appuntamenti" in tables:
                cols = {c["name"] for c in insp.get_columns("appuntamenti")}
                if "vendita_id" in cols:
                    # MySQL: drop FK se presente, poi colonna
                    fks = insp.get_foreign_keys("appuntamenti")
                    for fk in fks:
                        if "vendita_id" in (fk.get("constrained_columns") or []):
                            name = fk.get("name")
                            if name:
                                conn.execute(text(f"ALTER TABLE appuntamenti DROP FOREIGN KEY `{name}`"))
                    conn.execute(text("ALTER TABLE appuntamenti DROP COLUMN vendita_id"))
                    logger.info("Rimossa colonna appuntamenti.vendita_id")
            if "vendite" in tables:
                conn.execute(text("DROP TABLE IF EXISTS vendite"))
                logger.info("Rimossa tabella vendite")
            if "listino" in tables:
                conn.execute(text("DROP TABLE IF EXISTS listino"))
                logger.info("Rimossa tabella listino")
        _FINANCE_REMOVED_OK = True
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning("Impossibile rimuovere lo schema finanziario: %s", exc)


def ensure_patient_stato_schema() -> None:
    """Aggiunge stato_cliente e rende nullable i campi non noti in prenotazione."""
    global _PATIENT_STATO_OK
    if _PATIENT_STATO_OK:
        return
    try:
        insp = inspect(db.engine)
        if "patients" not in set(insp.get_table_names()):
            return
        cols = {c["name"]: c for c in insp.get_columns("patients")}
        stmts = []
        if "stato_cliente" not in cols:
            stmts.append(
                "ALTER TABLE patients "
                "ADD COLUMN stato_cliente ENUM('provvisorio','attivo','non_attivo') "
                "NOT NULL DEFAULT 'attivo'"
            )
        # Campi anagrafici/fisici: nullable per clienti provvisori
        for col_name, ddl in (
            ("sesso", "MODIFY COLUMN sesso ENUM('M','F','Altro') NULL"),
            ("data_nascita", "MODIFY COLUMN data_nascita DATE NULL"),
            ("altezza_cm", "MODIFY COLUMN altezza_cm INT NULL"),
            ("peso_iniziale", "MODIFY COLUMN peso_iniziale DECIMAL(5,2) NULL"),
        ):
            col = cols.get(col_name)
            if col is not None and not col.get("nullable", False):
                stmts.append(f"ALTER TABLE patients {ddl}")

        if stmts:
            with db.engine.begin() as conn:
                for stmt in stmts:
                    conn.execute(text(stmt))
            logger.info("Schema patients aggiornato (stato_cliente + campi nullable)")
        _PATIENT_STATO_OK = True
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning("Impossibile aggiornare schema patients/stato_cliente: %s", exc)


def ensure_richieste_appuntamento_schema() -> None:
    """Crea la tabella richieste_appuntamento (landing pubblica) se mancante."""
    global _RICHIESTE_SCHEMA_OK
    if _RICHIESTE_SCHEMA_OK:
        return
    try:
        from app.models.models import RichiestaAppuntamento

        ensure_patient_stato_schema()
        db.metadata.create_all(
            bind=db.engine,
            tables=[RichiestaAppuntamento.__table__],
            checkfirst=True,
        )
        _RICHIESTE_SCHEMA_OK = True
        logger.info("Schema richieste_appuntamento verificato")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning("Impossibile creare lo schema richieste_appuntamento: %s", exc)


def ensure_agenda_schema() -> None:
    """Crea tabelle orari settimanali ed eccezioni agenda se mancanti."""
    global _AGENDA_SCHEMA_OK
    if _AGENDA_SCHEMA_OK:
        return
    try:
        from app.models.models import AgendaEccezione, OrarioSettimanale, SlotDisponibilita

        tables = [m.__table__ for m in (OrarioSettimanale, AgendaEccezione)]
        db.metadata.create_all(bind=db.engine, tables=tables, checkfirst=True)
        ensure_richieste_appuntamento_schema()

        # Migrazione una tantum: slot puntuali → orari settimanali ricorrenti.
        if OrarioSettimanale.query.count() == 0:
            visti: set = set()
            for slot in SlotDisponibilita.query.all():
                if not slot.data_ora:
                    continue
                chiave = (slot.data_ora.weekday(), slot.data_ora.time().replace(second=0, microsecond=0))
                if chiave in visti:
                    continue
                visti.add(chiave)
                db.session.add(
                    OrarioSettimanale(
                        giorno_settimana=chiave[0],
                        ora=chiave[1],
                        attivo=True,
                        note=slot.note,
                    )
                )
            if visti:
                db.session.commit()
                logger.info("Migrati %d orari settimanali da slot_disponibilita", len(visti))

        _AGENDA_SCHEMA_OK = True
        logger.info("Schema agenda verificato (orari_settimanali, agenda_eccezioni)")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning("Impossibile creare lo schema agenda: %s", exc)


def ensure_nutrition_schema() -> None:
    """Crea le tabelle del modulo nutrizione se mancanti.

    Usa ``create_all`` limitato alle sole tabelle nuove: è idempotente e
    non tocca le tabelle esistenti. Coerente con l'approccio senza Alembic
    già usato nel progetto.
    """
    global _NUTRITION_SCHEMA_OK
    if _NUTRITION_SCHEMA_OK:
        return
    try:
        from app.models.models import DietMeal, DietMealItem, DietPlan, Food

        tables = [m.__table__ for m in (Food, DietPlan, DietMeal, DietMealItem)]
        db.metadata.create_all(bind=db.engine, tables=tables, checkfirst=True)
        _NUTRITION_SCHEMA_OK = True
        logger.info("Schema modulo nutrizione verificato (foods, diet_plans, diet_meals, diet_meal_items)")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Impossibile creare lo schema nutrizione: %s", exc)


def ensure_segretario_deviazione_schema() -> None:
    global _SEGRETARIO_DEVIAZIONE_OK
    if _SEGRETARIO_DEVIAZIONE_OK:
        return
    try:
        insp = inspect(db.engine)
        cols = {c["name"] for c in insp.get_columns("segretario_config")}
        stmts = []
        if "deviazione_attiva" not in cols:
            stmts.append(
                "ALTER TABLE segretario_config "
                "ADD COLUMN deviazione_attiva BOOLEAN NOT NULL DEFAULT FALSE"
            )
        if "deviazione_aggiornata_at" not in cols:
            stmts.append(
                "ALTER TABLE segretario_config "
                "ADD COLUMN deviazione_aggiornata_at DATETIME NULL"
            )
        if stmts:
            with db.engine.begin() as conn:
                for stmt in stmts:
                    conn.execute(text(stmt))
            logger.info("Schema segretario_config aggiornato (deviazione chiamate)")
        _SEGRETARIO_DEVIAZIONE_OK = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Impossibile verificare schema deviazione: %s", exc)
