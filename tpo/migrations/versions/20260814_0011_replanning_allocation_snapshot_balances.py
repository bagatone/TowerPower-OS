"""Align replanning allocation snapshots with quantitative balances.

Revision ID: 20260814_0011
Revises: 20260814_0010
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa

revision: str = "20260814_0011"
down_revision: str | Sequence[str] | None = "20260814_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"
TABLE = "replanning_snapshot_allocazioni"
OLD_CHECK = "allocated_quantity > 0"
NEW_CHECK = """
allocated_quantity > 0
AND consumed_quantity >= 0
AND released_quantity >= 0
AND transferred_quantity >= 0
AND invalidated_quantity >= 0
AND remaining_quantity >= 0
AND remaining_quantity = allocated_quantity
  - consumed_quantity
  - released_quantity
  - transferred_quantity
  - invalidated_quantity
"""


def _historical_commissioning_gate(bind: sa.engine.Connection) -> None:
    if bind.dialect.name != "postgresql":
        return
    statement = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM tpo.replanning_snapshot_allocazioni) THEN
    RAISE EXCEPTION 'historical replanning allocation snapshot commissioning required';
  END IF;
END;
$$
"""
    if context.is_offline_mode():
        op.execute(statement)
        return
    has_historical_rows = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM tpo.replanning_snapshot_allocazioni)")
    ).scalar_one()
    if has_historical_rows:
        raise RuntimeError(
            "historical replanning allocation snapshot commissioning required"
        )


def upgrade() -> None:
    bind = op.get_bind()
    _historical_commissioning_gate(bind)

    with op.batch_alter_table(TABLE, schema=SCHEMA) as batch:
        batch.drop_constraint(
            "ck_replanning_snapshot_allocazioni_quantity", type_="check"
        )
        for name in (
            "consumed_quantity",
            "released_quantity",
            "transferred_quantity",
            "invalidated_quantity",
            "remaining_quantity",
        ):
            batch.add_column(sa.Column(name, sa.Numeric(20, 6), nullable=False))
        batch.create_check_constraint(
            "ck_replanning_snapshot_allocazioni_quantity", NEW_CHECK
        )


def downgrade() -> None:
    with op.batch_alter_table(TABLE, schema=SCHEMA) as batch:
        batch.drop_constraint(
            "ck_replanning_snapshot_allocazioni_quantity", type_="check"
        )
        batch.create_check_constraint(
            "ck_replanning_snapshot_allocazioni_quantity", OLD_CHECK
        )
        for name in (
            "remaining_quantity",
            "invalidated_quantity",
            "transferred_quantity",
            "released_quantity",
            "consumed_quantity",
        ):
            batch.drop_column(name)
