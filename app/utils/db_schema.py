"""Piccoli upgrade schema SQL eseguiti al volo (senza Alembic)."""

import logging

from sqlalchemy import inspect, text

from app.models.models import db

logger = logging.getLogger(__name__)

_SEGRETARIO_DEVIAZIONE_OK = False
_NUTRITION_SCHEMA_OK = False


_AGENDA_SCHEMA_OK = False


def ensure_agenda_schema() -> None:
    """Crea tabelle orari settimanali ed eccezioni agenda se mancanti."""
    global _AGENDA_SCHEMA_OK
    if _AGENDA_SCHEMA_OK:
        return
    try:
        from app.models.models import AgendaEccezione, OrarioSettimanale, SlotDisponibilita

        tables = [m.__table__ for m in (OrarioSettimanale, AgendaEccezione)]
        db.metadata.create_all(bind=db.engine, tables=tables, checkfirst=True)

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
