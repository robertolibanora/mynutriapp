"""Consensi GDPR privacy/marketing + campi oblio/retention su patients.

Revision ID: 20260803_gdpr_01
Revises: 20260729_diario_02
Create Date: 2026-08-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_gdpr_01"
down_revision: Union[str, Sequence[str], None] = "20260729_diario_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "patients",
        sa.Column(
            "consenso_privacy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "patients",
        sa.Column(
            "consenso_marketing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "patients",
        sa.Column("privacy_policy_version", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "patients",
        sa.Column("consenso_privacy_il", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "patients",
        sa.Column("consenso_marketing_il", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "patients",
        sa.Column("erasure_requested_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "patients",
        sa.Column("erasure_completed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "patients",
        sa.Column("retention_until", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("patients", "retention_until")
    op.drop_column("patients", "erasure_completed_at")
    op.drop_column("patients", "erasure_requested_at")
    op.drop_column("patients", "consenso_marketing_il")
    op.drop_column("patients", "consenso_privacy_il")
    op.drop_column("patients", "privacy_policy_version")
    op.drop_column("patients", "consenso_marketing")
    op.drop_column("patients", "consenso_privacy")
