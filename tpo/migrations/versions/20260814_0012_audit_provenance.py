"""Add nullable audit provenance without rewriting historical rows.

Revision ID: 20260814_0012
Revises: 20260814_0011
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260814_0012"
down_revision: str | Sequence[str] | None = "20260814_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"
TABLE = "audit_eventi"
CHECK = "provenance IS NULL OR btrim(provenance) <> ''"


def upgrade() -> None:
    with op.batch_alter_table(TABLE, schema=SCHEMA) as batch:
        batch.add_column(sa.Column("provenance", sa.Text(), nullable=True))
        batch.create_check_constraint("ck_audit_eventi_provenance", CHECK)


def downgrade() -> None:
    with op.batch_alter_table(TABLE, schema=SCHEMA) as batch:
        batch.drop_constraint("ck_audit_eventi_provenance", type_="check")
        batch.drop_column("provenance")
