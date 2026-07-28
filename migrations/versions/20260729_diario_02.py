"""Aggiunge consultation.errore_pipeline per stato ERRORE + GET status.

Revision ID: 20260729_diario_02
Revises: 20260729_diario_01
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_diario_02"
down_revision: Union[str, Sequence[str], None] = "20260729_diario_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "consultation",
        sa.Column("errore_pipeline", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("consultation", "errore_pipeline")
