"""Piccoli upgrade schema SQL eseguiti al volo (senza Alembic)."""

import logging

from sqlalchemy import inspect, text

from app.models.models import db

logger = logging.getLogger(__name__)

_SEGRETARIO_REMOVED_OK = False
_NUTRITION_SCHEMA_OK = False
_FINANCE_REMOVED_OK = False

_AGENDA_SCHEMA_OK = False
_RICHIESTE_SCHEMA_OK = False
_PATIENT_STATO_OK = False
_GDPR_SCHEMA_OK = False
_ACTIVITY_NOTES_SCHEMA_OK = False
_AUTH_TOKENS_SCHEMA_OK = False


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


def ensure_gdpr_schema() -> None:
    """Aggiunge colonne GDPR (consensi, erasure, retention) su patients."""
    global _GDPR_SCHEMA_OK
    if _GDPR_SCHEMA_OK:
        return
    try:
        insp = inspect(db.engine)
        if "patients" not in set(insp.get_table_names()):
            return
        cols = {c["name"] for c in insp.get_columns("patients")}
        stmts = []
        bool_cols = ("consenso_privacy", "consenso_marketing")
        for col_name in bool_cols:
            if col_name not in cols:
                stmts.append(
                    f"ALTER TABLE patients ADD COLUMN {col_name} "
                    "TINYINT(1) NOT NULL DEFAULT 0"
                )
        for col_name, ddl in (
            ("privacy_policy_version", "VARCHAR(32) NULL"),
            ("consenso_privacy_il", "DATETIME NULL"),
            ("consenso_marketing_il", "DATETIME NULL"),
            ("erasure_requested_at", "DATETIME NULL"),
            ("erasure_completed_at", "DATETIME NULL"),
            ("retention_until", "DATE NULL"),
        ):
            if col_name not in cols:
                stmts.append(f"ALTER TABLE patients ADD COLUMN {col_name} {ddl}")
        if stmts:
            with db.engine.begin() as conn:
                for stmt in stmts:
                    conn.execute(text(stmt))
            logger.info("Schema patients aggiornato (colonne GDPR)")
        _GDPR_SCHEMA_OK = True
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning("Impossibile aggiornare schema GDPR patients: %s", exc)


def ensure_richieste_appuntamento_schema() -> None:
    """Crea la tabella richieste_appuntamento (landing pubblica) se mancante."""
    global _RICHIESTE_SCHEMA_OK
    if _RICHIESTE_SCHEMA_OK:
        return
    try:
        from app.models.models import RichiestaAppuntamento

        ensure_patient_stato_schema()
        ensure_gdpr_schema()
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
        insp = inspect(db.engine)
        orari_cols = {c["name"] for c in insp.get_columns("orari_settimanali")} if "orari_settimanali" in set(insp.get_table_names()) else set()
        if OrarioSettimanale.query.count() == 0 and "utente_id" in orari_cols:
            # richiede un tenant; se assente salta (verrà creato dopo seed)
            from app.models.diario import Utente
            from app.models.enums import UtenteRuolo

            tenant = (
                Utente.query.filter_by(ruolo=UtenteRuolo.NUTRIZIONISTA.value)
                .order_by(Utente.id.asc())
                .first()
            )
            if tenant is not None:
                visti: set = set()
                for slot in SlotDisponibilita.query.all():
                    if not slot.data_ora:
                        continue
                    chiave = (
                        slot.data_ora.weekday(),
                        slot.data_ora.time().replace(second=0, microsecond=0),
                    )
                    if chiave in visti:
                        continue
                    visti.add(chiave)
                    db.session.add(
                        OrarioSettimanale(
                            utente_id=tenant.id,
                            giorno_settimana=chiave[0],
                            ora=chiave[1],
                            attivo=True,
                            note=slot.note,
                        )
                    )
                if visti:
                    db.session.commit()
                    logger.info(
                        "Migrati %d orari settimanali da slot_disponibilita", len(visti)
                    )

        _AGENDA_SCHEMA_OK = True
        logger.info("Schema agenda verificato (orari_settimanali, agenda_eccezioni)")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning("Impossibile creare lo schema agenda: %s", exc)


def ensure_nutrition_schema() -> None:
    """Crea le tabelle del modulo nutrizione se mancanti.

    Usa ``create_all`` limitato alle sole tabelle nuove: è idempotente e
    non tocca le tabelle esistenti. Coerente con l'approccio senza Alembic
    già usato nel progetto. Aggiunge anche colonne nuove su tabelle già presenti
    (es. ``diet_meals.day_index_to`` per intervalli di giorni).
    """
    global _NUTRITION_SCHEMA_OK
    if _NUTRITION_SCHEMA_OK:
        return
    try:
        from app.models.models import DietMeal, DietMealItem, DietPlan, Food

        tables = [m.__table__ for m in (Food, DietPlan, DietMeal, DietMealItem)]
        db.metadata.create_all(bind=db.engine, tables=tables, checkfirst=True)

        insp = inspect(db.engine)
        if "diet_meals" in set(insp.get_table_names()):
            cols = {c["name"] for c in insp.get_columns("diet_meals")}
            if "day_index_to" not in cols:
                with db.engine.begin() as conn:
                    conn.execute(
                        text(
                            "ALTER TABLE diet_meals "
                            "ADD COLUMN day_index_to INT NOT NULL DEFAULT 0"
                        )
                    )
                    conn.execute(text("UPDATE diet_meals SET day_index_to = day_index"))
                logger.info("Aggiunta colonna diet_meals.day_index_to")

        if "diet_plans" in set(insp.get_table_names()):
            plan_cols = {c["name"] for c in insp.get_columns("diet_plans")}
            target_cols = {
                "target_kcal": "INT NULL",
                "target_protein_pct": "DECIMAL(5,2) NULL",
                "target_carbs_pct": "DECIMAL(5,2) NULL",
                "target_fat_pct": "DECIMAL(5,2) NULL",
            }
            missing = {k: v for k, v in target_cols.items() if k not in plan_cols}
            if missing:
                with db.engine.begin() as conn:
                    for col, ddl in missing.items():
                        conn.execute(
                            text(f"ALTER TABLE diet_plans ADD COLUMN {col} {ddl}")
                        )
                logger.info(
                    "Aggiunte colonne obiettivi su diet_plans: %s",
                    ", ".join(missing),
                )

        _NUTRITION_SCHEMA_OK = True
        logger.info("Schema modulo nutrizione verificato (foods, diet_plans, diet_meals, diet_meal_items)")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Impossibile creare lo schema nutrizione: %s", exc)


def ensure_segretario_removed() -> None:
    """Rimuove tabelle del modulo Segretario AI (Vapi / chiamate inbound)."""
    global _SEGRETARIO_REMOVED_OK
    if _SEGRETARIO_REMOVED_OK:
        return
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        with db.engine.begin() as conn:
            if "chiamate_inbound" in tables:
                conn.execute(text("DROP TABLE IF EXISTS chiamate_inbound"))
                logger.info("Rimossa tabella chiamate_inbound")
            if "segretario_config" in tables:
                conn.execute(text("DROP TABLE IF EXISTS segretario_config"))
                logger.info("Rimossa tabella segretario_config")
        _SEGRETARIO_REMOVED_OK = True
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning("Impossibile rimuovere lo schema segretario: %s", exc)


_MULTI_TENANT_OK = False


def _column_names(insp, table: str) -> set[str]:
    return {c["name"] for c in insp.get_columns(table)}


def _index_names(insp, table: str) -> set[str]:
    return {ix["name"] for ix in insp.get_indexes(table) if ix.get("name")}


def _fk_names(insp, table: str) -> set[str]:
    return {fk["name"] for fk in insp.get_foreign_keys(table) if fk.get("name")}


def _unique_constraint_names(insp, table: str) -> set[str]:
    names = set()
    for uc in insp.get_unique_constraints(table):
        if uc.get("name"):
            names.add(uc["name"])
    # MySQL a volte espone UNIQUE come index
    for ix in insp.get_indexes(table):
        if ix.get("unique") and ix.get("name"):
            names.add(ix["name"])
    return names


def ensure_multi_tenant_schema() -> None:
    """Colonne/FK multi-tenant: utente.ruolo, patients.nutrizionista_id, agenda.utente_id."""
    global _MULTI_TENANT_OK
    if _MULTI_TENANT_OK:
        return
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if "utente" not in tables:
            return

        with db.engine.begin() as conn:
            # --- utente ---
            u_cols = _column_names(insp, "utente")
            if "ruolo" not in u_cols:
                conn.execute(
                    text(
                        "ALTER TABLE utente ADD COLUMN ruolo VARCHAR(20) "
                        "NOT NULL DEFAULT 'nutrizionista' AFTER telefono"
                    )
                )
            if "password_hash" not in u_cols:
                conn.execute(
                    text(
                        "ALTER TABLE utente ADD COLUMN password_hash VARCHAR(255) NULL AFTER ruolo"
                    )
                )
            if "creato_da" not in u_cols:
                conn.execute(
                    text(
                        "ALTER TABLE utente ADD COLUMN creato_da INT NULL AFTER password_hash"
                    )
                )
            # refresh insp for FK
            insp = inspect(db.engine)
            if "fk_utente_creato_da" not in _fk_names(insp, "utente"):
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE utente ADD CONSTRAINT fk_utente_creato_da "
                            "FOREIGN KEY (creato_da) REFERENCES utente(id) ON DELETE SET NULL"
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass

            # --- patients: drop global uniques, add composite after backfill ---
            if "patients" in tables:
                p_uniques = _unique_constraint_names(insp, "patients")
                # drop telefono unique (name often `telefono`)
                for uname in ("telefono", "uq_patients_email"):
                    if uname in p_uniques or uname in _index_names(insp, "patients"):
                        try:
                            conn.execute(text(f"ALTER TABLE patients DROP INDEX `{uname}`"))
                        except Exception:  # noqa: BLE001
                            pass

            # --- agenda / richieste / appuntamenti: add utente_id nullable first ---
            for table, after_col in (
                ("orari_settimanali", "id"),
                ("agenda_eccezioni", "id"),
                ("slot_disponibilita", "id"),
                ("richieste_appuntamento", "id"),
                ("appuntamenti", "patient_id"),
            ):
                if table not in tables:
                    continue
                cols = _column_names(insp, table)
                if "utente_id" not in cols:
                    conn.execute(
                        text(
                            f"ALTER TABLE `{table}` ADD COLUMN utente_id INT NULL "
                            f"AFTER `{after_col}`"
                        )
                    )

            # slot: drop global unique on data_ora
            if "slot_disponibilita" in tables:
                for uname in ("data_ora", "uq_slot_data_ora"):
                    try:
                        conn.execute(text(f"ALTER TABLE slot_disponibilita DROP INDEX `{uname}`"))
                    except Exception:  # noqa: BLE001
                        pass

            # orari: drop old unique
            if "orari_settimanali" in tables:
                for uname in ("uq_orario_settimanale_giorno_ora",):
                    try:
                        conn.execute(text(f"ALTER TABLE orari_settimanali DROP INDEX `{uname}`"))
                    except Exception:  # noqa: BLE001
                        pass

            # appuntamenti.created_by: allow 'admin'
            if "appuntamenti" in tables:
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE appuntamenti MODIFY COLUMN created_by "
                            "ENUM('Enrico','user','admin') NOT NULL"
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass

            # foods / diet_plans professional_id FK (best-effort)
            for table in ("foods", "diet_plans"):
                if table not in tables:
                    continue
                fk_name = f"fk_{table}_professional_id"
                if fk_name not in _fk_names(insp, table):
                    try:
                        conn.execute(
                            text(
                                f"ALTER TABLE `{table}` ADD CONSTRAINT `{fk_name}` "
                                "FOREIGN KEY (professional_id) REFERENCES utente(id) "
                                "ON DELETE SET NULL"
                            )
                        )
                    except Exception:  # noqa: BLE001
                        pass

        # Backfill + NOT NULL + composite unique + FK (dopo seed super admin esterno)
        _MULTI_TENANT_OK = True
        logger.info("Schema multi-tenant base applicato (colonne utente_id/ruolo)")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning("Impossibile applicare schema multi-tenant: %s", exc)


def finalize_multi_tenant_constraints(default_utente_id: int) -> None:
    """Backfill FK e vincoli NOT NULL / unique compositi dopo seed super_admin.

    Idempotente e con lock_wait_timeout breve per non bloccare i worker gunicorn.
    """
    if not default_utente_id:
        return
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        with db.engine.begin() as conn:
            conn.execute(text("SET SESSION lock_wait_timeout = 3"))

            if "patients" in tables:
                conn.execute(
                    text(
                        "UPDATE patients SET nutrizionista_id = :uid "
                        "WHERE nutrizionista_id IS NULL"
                    ),
                    {"uid": default_utente_id},
                )
                p_cols = {c["name"]: c for c in insp.get_columns("patients")}
                nutr_col = p_cols.get("nutrizionista_id")
                already_nn = nutr_col is not None and not nutr_col.get("nullable", True)
                if not already_nn:
                    try:
                        for fk in insp.get_foreign_keys("patients"):
                            if "nutrizionista_id" in (fk.get("constrained_columns") or []):
                                name = fk.get("name")
                                if name:
                                    conn.execute(
                                        text(
                                            f"ALTER TABLE patients DROP FOREIGN KEY `{name}`"
                                        )
                                    )
                        conn.execute(
                            text(
                                "ALTER TABLE patients MODIFY COLUMN nutrizionista_id INT NOT NULL"
                            )
                        )
                        conn.execute(
                            text(
                                "ALTER TABLE patients ADD CONSTRAINT "
                                "fk_patients_nutrizionista_id_utente "
                                "FOREIGN KEY (nutrizionista_id) REFERENCES utente(id) "
                                "ON DELETE RESTRICT"
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("patients.nutrizionista_id constraint: %s", exc)

                for uname, cols in (
                    ("uq_patients_tenant_telefono", "(nutrizionista_id, telefono)"),
                    ("uq_patients_tenant_email", "(nutrizionista_id, email)"),
                ):
                    try:
                        conn.execute(
                            text(
                                f"ALTER TABLE patients ADD UNIQUE KEY `{uname}` {cols}"
                            )
                        )
                    except Exception:  # noqa: BLE001
                        pass

            for table in (
                "orari_settimanali",
                "agenda_eccezioni",
                "slot_disponibilita",
                "richieste_appuntamento",
                "appuntamenti",
            ):
                if table not in tables:
                    continue
                cols = _column_names(insp, table)
                if "utente_id" not in cols:
                    continue
                conn.execute(
                    text(
                        f"UPDATE `{table}` SET utente_id = :uid WHERE utente_id IS NULL"
                    ),
                    {"uid": default_utente_id},
                )
                if table in ("orari_settimanali", "agenda_eccezioni", "slot_disponibilita"):
                    nulls = conn.execute(
                        text(f"SELECT COUNT(*) FROM `{table}` WHERE utente_id IS NULL")
                    ).scalar()
                    colmeta = {c["name"]: c for c in insp.get_columns(table)}.get(
                        "utente_id"
                    )
                    if int(nulls or 0) == 0 and colmeta and colmeta.get("nullable", True):
                        try:
                            conn.execute(
                                text(
                                    f"ALTER TABLE `{table}` MODIFY COLUMN utente_id INT NOT NULL"
                                )
                            )
                        except Exception:  # noqa: BLE001
                            pass
                fk_name = f"fk_{table}_utente_id"
                if fk_name not in _fk_names(insp, table):
                    ondel = (
                        "CASCADE"
                        if table.startswith(("orari", "agenda", "slot"))
                        else "RESTRICT"
                    )
                    try:
                        conn.execute(
                            text(
                                f"ALTER TABLE `{table}` ADD CONSTRAINT `{fk_name}` "
                                f"FOREIGN KEY (utente_id) REFERENCES utente(id) "
                                f"ON DELETE {ondel}"
                            )
                        )
                    except Exception:  # noqa: BLE001
                        pass

            for stmt in (
                "ALTER TABLE orari_settimanali ADD UNIQUE KEY "
                "uq_orario_utente_giorno_ora (utente_id, giorno_settimana, ora)",
                "ALTER TABLE slot_disponibilita ADD UNIQUE KEY "
                "uq_slot_utente_data_ora (utente_id, data_ora)",
            ):
                try:
                    conn.execute(text(stmt))
                except Exception:  # noqa: BLE001
                    pass

            if "appuntamenti" in tables and "patients" in tables:
                conn.execute(
                    text(
                        "UPDATE appuntamenti a "
                        "JOIN patients p ON p.id = a.patient_id "
                        "SET a.utente_id = p.nutrizionista_id "
                        "WHERE a.utente_id IS NULL"
                    )
                )

        logger.info("Vincoli multi-tenant finalizzati (default utente_id=%s)", default_utente_id)
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning("finalize_multi_tenant_constraints fallita: %s", exc)


_BILLING_SCHEMA_OK = False


def ensure_billing_schema() -> None:
    """Colonne piano/Stripe su utente + indici per conteggio pazienti attivi."""
    global _BILLING_SCHEMA_OK
    if _BILLING_SCHEMA_OK:
        return
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        if "utente" not in tables:
            return

        with db.engine.begin() as conn:
            u_cols = _column_names(insp, "utente")
            if "plan" not in u_cols:
                conn.execute(
                    text(
                        "ALTER TABLE utente ADD COLUMN plan VARCHAR(32) "
                        "NOT NULL DEFAULT 'starter' AFTER attivo"
                    )
                )
            if "stripe_customer_id" not in u_cols:
                conn.execute(
                    text(
                        "ALTER TABLE utente ADD COLUMN stripe_customer_id VARCHAR(255) "
                        "NULL AFTER plan"
                    )
                )
            if "stripe_subscription_id" not in u_cols:
                conn.execute(
                    text(
                        "ALTER TABLE utente ADD COLUMN stripe_subscription_id VARCHAR(255) "
                        "NULL AFTER stripe_customer_id"
                    )
                )
            if "subscription_status" not in u_cols:
                conn.execute(
                    text(
                        "ALTER TABLE utente ADD COLUMN subscription_status VARCHAR(32) "
                        "NOT NULL DEFAULT 'none' AFTER stripe_subscription_id"
                    )
                )
            # refresh columns after possible ALTER
            insp = inspect(db.engine)
            u_cols = _column_names(insp, "utente")
            if "needs_password_setup" not in u_cols:
                conn.execute(
                    text(
                        "ALTER TABLE utente ADD COLUMN needs_password_setup TINYINT(1) "
                        "NOT NULL DEFAULT 0 AFTER subscription_status"
                    )
                )

            insp = inspect(db.engine)
            u_cols = _column_names(insp, "utente")
            if "public_slug" not in u_cols:
                conn.execute(
                    text(
                        "ALTER TABLE utente ADD COLUMN public_slug VARCHAR(80) "
                        "NULL AFTER needs_password_setup"
                    )
                )

            insp = inspect(db.engine)
            u_cols = _column_names(insp, "utente")
            if "studio_nome" not in u_cols:
                conn.execute(
                    text(
                        "ALTER TABLE utente ADD COLUMN studio_nome VARCHAR(120) "
                        "NULL AFTER public_slug"
                    )
                )

            insp = inspect(db.engine)
            u_indexes = _index_names(insp, "utente")
            if "uq_utente_stripe_customer_id" not in u_indexes:
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE utente ADD UNIQUE KEY "
                            "uq_utente_stripe_customer_id (stripe_customer_id)"
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass

            if "uq_utente_public_slug" not in u_indexes:
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE utente ADD UNIQUE KEY "
                            "uq_utente_public_slug (public_slug)"
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass

            if "diet_plans" in tables:
                dp_indexes = _index_names(insp, "diet_plans")
                if "idx_diet_plan_patient_status" not in dp_indexes:
                    try:
                        conn.execute(
                            text(
                                "ALTER TABLE diet_plans ADD INDEX "
                                "idx_diet_plan_patient_status (patient_id, status)"
                            )
                        )
                    except Exception:  # noqa: BLE001
                        pass

            if "diete" in tables:
                d_indexes = _index_names(insp, "diete")
                if "idx_diete_patient_data_fine" not in d_indexes:
                    try:
                        conn.execute(
                            text(
                                "ALTER TABLE diete ADD INDEX "
                                "idx_diete_patient_data_fine (patient_id, data_fine)"
                            )
                        )
                    except Exception:  # noqa: BLE001
                        pass

        _BILLING_SCHEMA_OK = True
        logger.info("Schema billing verificato (utente.plan + indici diete attive)")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning("Impossibile aggiornare schema billing: %s", exc)


def ensure_auth_tokens_schema() -> None:
    """Colonne account_status/token_version + tabella auth_secure_tokens."""
    global _AUTH_TOKENS_SCHEMA_OK
    if _AUTH_TOKENS_SCHEMA_OK:
        return
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        with db.engine.begin() as conn:
            if "patients" in tables:
                p_cols = _column_names(insp, "patients")
                if "account_status" not in p_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE patients ADD COLUMN account_status "
                            "VARCHAR(20) NOT NULL DEFAULT 'active' AFTER stato_cliente"
                        )
                    )
                insp = inspect(db.engine)
                p_cols = _column_names(insp, "patients")
                if "token_version" not in p_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE patients ADD COLUMN token_version "
                            "INT NOT NULL DEFAULT 0 AFTER account_status"
                        )
                    )

            if "auth_secure_tokens" not in tables:
                conn.execute(
                    text(
                        """
                        CREATE TABLE auth_secure_tokens (
                          id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                          purpose VARCHAR(32) NOT NULL,
                          subject_id INT NOT NULL,
                          token_hash CHAR(64) NOT NULL,
                          expires_at DATETIME NOT NULL,
                          used_at DATETIME NULL,
                          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                          UNIQUE KEY uq_auth_secure_tokens_hash (token_hash),
                          KEY ix_auth_secure_tokens_purpose_subject (purpose, subject_id),
                          KEY ix_auth_secure_tokens_expires (expires_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                )
                logger.info("Creata tabella auth_secure_tokens")

            if "utente" in tables:
                u_cols = _column_names(inspect(db.engine), "utente")
                if "studio_nome" not in u_cols:
                    conn.execute(
                        text(
                            "ALTER TABLE utente ADD COLUMN studio_nome VARCHAR(120) "
                            "NULL AFTER public_slug"
                        )
                    )
        _AUTH_TOKENS_SCHEMA_OK = True
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning("Impossibile aggiornare schema auth tokens: %s", exc)


def ensure_activity_notes_schema() -> None:
    """Crea tabelle patient_notes e activities se assenti."""
    global _ACTIVITY_NOTES_SCHEMA_OK
    if _ACTIVITY_NOTES_SCHEMA_OK:
        return
    try:
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        with db.engine.begin() as conn:
            if "patient_notes" not in tables:
                conn.execute(
                    text(
                        """
                        CREATE TABLE patient_notes (
                          id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                          patient_id INT NOT NULL,
                          utente_id INT NOT NULL,
                          body TEXT NOT NULL,
                          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                          updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                          INDEX ix_patient_notes_patient_id (patient_id),
                          INDEX ix_patient_notes_utente_id (utente_id),
                          CONSTRAINT fk_patient_notes_patient
                            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
                          CONSTRAINT fk_patient_notes_utente
                            FOREIGN KEY (utente_id) REFERENCES utente(id) ON DELETE RESTRICT
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                )
                logger.info("Creata tabella patient_notes")

            if "activities" not in tables:
                conn.execute(
                    text(
                        """
                        CREATE TABLE activities (
                          id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                          utente_id INT NOT NULL,
                          patient_id INT NULL,
                          title VARCHAR(255) NOT NULL,
                          tipo VARCHAR(40) NOT NULL DEFAULT 'manuale',
                          priority VARCHAR(20) NOT NULL DEFAULT 'medium',
                          due_at DATETIME NULL,
                          status VARCHAR(20) NOT NULL DEFAULT 'open',
                          source VARCHAR(20) NOT NULL DEFAULT 'manual',
                          notes TEXT NULL,
                          created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
                          completed_at DATETIME NULL,
                          INDEX ix_activities_utente_id (utente_id),
                          INDEX ix_activities_patient_id (patient_id),
                          INDEX ix_activities_due_at (due_at),
                          INDEX ix_activities_status (status),
                          CONSTRAINT fk_activities_utente
                            FOREIGN KEY (utente_id) REFERENCES utente(id) ON DELETE CASCADE,
                          CONSTRAINT fk_activities_patient
                            FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                        """
                    )
                )
                logger.info("Creata tabella activities")
        _ACTIVITY_NOTES_SCHEMA_OK = True
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.warning("Impossibile aggiornare schema activity/notes: %s", exc)
