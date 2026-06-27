"""Piccoli upgrade schema SQL eseguiti al volo (senza Alembic)."""

import logging

from sqlalchemy import inspect, text

from app.models.models import db

logger = logging.getLogger(__name__)

_SEGRETARIO_DEVIAZIONE_OK = False


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
