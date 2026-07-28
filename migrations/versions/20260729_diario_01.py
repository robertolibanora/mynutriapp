"""Fase 1 diario: utente, colonne patients, consultation/audio/transcript/diary_entry.

Revision ID: 20260729_diario_01
Revises:
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_diario_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

consultation_stato_enum = sa.Enum(
    "BOZZA",
    "CARICATO",
    "TRASCRITTO",
    "ELABORATO",
    "CONFERMATO",
    "ERRORE",
    name="consultation_stato",
)


def upgrade() -> None:
    op.create_table(
        "utente",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nome", sa.String(100), nullable=False),
        sa.Column("cognome", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("telefono", sa.String(20), nullable=True),
        sa.Column("attivo", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("creato_il", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "aggiornato_il",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("email", name="uq_utente_email"),
        sa.UniqueConstraint("telefono", name="uq_utente_telefono"),
    )

    # Estende patients esistente (non si crea una seconda tabella patient)
    with op.batch_alter_table("patients") as batch:
        batch.add_column(sa.Column("email", sa.String(255), nullable=True))
        batch.add_column(sa.Column("nutrizionista_id", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "consenso_registrazione",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.add_column(
            sa.Column(
                "consenso_ai",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.add_column(sa.Column("consenso_aggiornato_il", sa.DateTime(), nullable=True))
        batch.add_column(
            sa.Column(
                "aggiornato_il",
                sa.DateTime(),
                nullable=True,
                server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            )
        )
        batch.create_unique_constraint("uq_patients_email", ["email"])
        batch.create_foreign_key(
            "fk_patients_nutrizionista_id_utente",
            "utente",
            ["nutrizionista_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_patients_nutrizionista_id", ["nutrizionista_id"])

    op.create_table(
        "consultation",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("nutrizionista_id", sa.Integer(), nullable=False),
        sa.Column("data_colloquio", sa.DateTime(), nullable=False),
        sa.Column(
            "stato",
            consultation_stato_enum,
            nullable=False,
            server_default="BOZZA",
        ),
        sa.Column("note_manuali", sa.Text(), nullable=True),
        sa.Column("creato_il", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "aggiornato_il",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name="fk_consultation_patient_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["nutrizionista_id"],
            ["utente.id"],
            name="fk_consultation_nutrizionista_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_consultation_patient_id", "consultation", ["patient_id"])
    op.create_index("ix_consultation_nutrizionista_id", "consultation", ["nutrizionista_id"])
    op.create_index("ix_consultation_data_colloquio", "consultation", ["data_colloquio"])
    op.create_index(
        "ix_consultation_patient_data",
        "consultation",
        ["patient_id", "data_colloquio"],
    )

    op.create_table(
        "audio_recording",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("consultation_id", sa.Integer(), nullable=False),
        sa.Column("path_file", sa.String(512), nullable=False),
        sa.Column("nome_originale", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("dimensione_byte", sa.BigInteger(), nullable=False),
        sa.Column("durata_sec", sa.Float(), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("cifrato", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("cancellato_il", sa.DateTime(), nullable=True),
        sa.Column("creato_il", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["consultation_id"],
            ["consultation.id"],
            name="fk_audio_recording_consultation_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("consultation_id", name="uq_audio_recording_consultation_id"),
    )

    op.create_table(
        "transcript",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("consultation_id", sa.Integer(), nullable=False),
        sa.Column("testo", sa.Text(), nullable=False),
        sa.Column("lingua", sa.String(16), nullable=False, server_default="it"),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("modello", sa.String(128), nullable=False),
        sa.Column("durata_elaborazione_sec", sa.Float(), nullable=True),
        sa.Column("creato_il", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["consultation_id"],
            ["consultation.id"],
            name="fk_transcript_consultation_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("consultation_id", name="uq_transcript_consultation_id"),
    )

    op.create_table(
        "diary_entry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("consultation_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("contenuto_json", sa.JSON(), nullable=False),
        sa.Column("riassunto_testo", sa.Text(), nullable=True),
        sa.Column("modello_usato", sa.String(128), nullable=False),
        sa.Column("revisionato_da", sa.Integer(), nullable=True),
        sa.Column("revisionato_il", sa.DateTime(), nullable=True),
        sa.Column(
            "modificato_manualmente",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("creato_il", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column(
            "aggiornato_il",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["consultation_id"],
            ["consultation.id"],
            name="fk_diary_entry_consultation_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name="fk_diary_entry_patient_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["revisionato_da"],
            ["utente.id"],
            name="fk_diary_entry_revisionato_da",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("consultation_id", name="uq_diary_entry_consultation_id"),
    )
    op.create_index("ix_diary_entry_patient_id", "diary_entry", ["patient_id"])
    op.create_index("ix_diary_entry_revisionato_da", "diary_entry", ["revisionato_da"])


def downgrade() -> None:
    # MySQL crea indici impliciti per le FK: drop_table li rimuove insieme.
    op.drop_table("diary_entry")
    op.drop_table("transcript")
    op.drop_table("audio_recording")
    op.drop_table("consultation")

    with op.batch_alter_table("patients") as batch:
        batch.drop_constraint("fk_patients_nutrizionista_id_utente", type_="foreignkey")
        batch.drop_constraint("uq_patients_email", type_="unique")
        batch.drop_column("aggiornato_il")
        batch.drop_column("consenso_aggiornato_il")
        batch.drop_column("consenso_ai")
        batch.drop_column("consenso_registrazione")
        batch.drop_column("nutrizionista_id")
        batch.drop_column("email")

    op.drop_table("utente")
