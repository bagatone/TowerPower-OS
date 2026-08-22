"""Persist authoritative in-progress resource facts.

Revision ID: 20260822_0015
Revises: 20260822_0014
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260822_0015"
down_revision: str | Sequence[str] | None = "20260822_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"
UOM = postgresql.ENUM(
    "SET", "GRAM", "UNIT", name="unit_of_measure", schema=SCHEMA,
    create_type=False,
)


def upgrade() -> None:
    op.add_column(
        "semine", sa.Column("expected_useful_quantity", sa.Numeric(20, 6)),
        schema=SCHEMA,
    )
    op.add_column(
        "semine", sa.Column("expected_useful_uom", UOM), schema=SCHEMA,
    )
    op.add_column(
        "semine", sa.Column("harvest_window_start", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.add_column(
        "semine", sa.Column("harvest_window_end", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    with op.batch_alter_table("semine", schema=SCHEMA) as batch:
        batch.create_check_constraint(
            "ck_semine_expected_useful_pair",
            "(expected_useful_quantity IS NULL AND expected_useful_uom IS NULL) OR "
            "(expected_useful_quantity IS NOT NULL AND expected_useful_quantity > 0 "
            "AND expected_useful_uom IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_semine_harvest_window_pair",
            "(harvest_window_start IS NULL AND harvest_window_end IS NULL) OR "
            "(harvest_window_start IS NOT NULL AND harvest_window_end IS NOT NULL "
            "AND harvest_window_end > harvest_window_start)",
        )
        batch.create_check_constraint(
            "ck_semine_planning_authority_commissioning",
            "(expected_useful_quantity IS NULL AND expected_useful_uom IS NULL "
            "AND harvest_window_start IS NULL AND harvest_window_end IS NULL) OR "
            "(expected_useful_quantity IS NOT NULL AND expected_useful_uom IS NOT NULL "
            "AND harvest_window_start IS NOT NULL AND harvest_window_end IS NOT NULL)",
        )

    # Historical readiness evidence remains; new snapshots no longer invent it.
    with op.batch_alter_table("replanning_snapshot_stock", schema=SCHEMA) as batch:
        batch.alter_column(
            "readiness_code", existing_type=sa.Text(), nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("""
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM tpo.replanning_snapshot_stock
            WHERE readiness_code IS NULL
          ) THEN
            RAISE EXCEPTION 'cannot downgrade: new STOCK snapshots have no legacy readiness';
          END IF;
        END $$
        """)
    with op.batch_alter_table("replanning_snapshot_stock", schema=SCHEMA) as batch:
        batch.alter_column(
            "readiness_code", existing_type=sa.Text(), nullable=False,
        )
    with op.batch_alter_table("semine", schema=SCHEMA) as batch:
        batch.drop_constraint(
            "ck_semine_planning_authority_commissioning", type_="check",
        )
        batch.drop_constraint("ck_semine_harvest_window_pair", type_="check")
        batch.drop_constraint("ck_semine_expected_useful_pair", type_="check")
    for column in (
        "harvest_window_end", "harvest_window_start", "expected_useful_uom",
        "expected_useful_quantity",
    ):
        op.drop_column("semine", column, schema=SCHEMA)
