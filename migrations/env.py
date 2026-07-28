"""Alembic environment: usa SQLALCHEMY_DATABASE_URI da Config (.env).

Override opzionale: variabile d'ambiente ``ALEMBIC_DATABASE_URI``
(utile per testare upgrade/downgrade su un DB dedicato).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config.config import Config
from app.models import db  # noqa: F401 — registra metadata
import app.models  # noqa: F401 — importa Patient + modelli diario

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = db.metadata

db_url = os.getenv("ALEMBIC_DATABASE_URI") or Config.SQLALCHEMY_DATABASE_URI
# escape % for ConfigParser
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

# Log mirato (senza credenziali) per evitare upgrade accidentali sul DB sbagliato
_safe = db_url.split("@")[-1] if "@" in db_url else db_url
print(f"[alembic] target database: {_safe}")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
