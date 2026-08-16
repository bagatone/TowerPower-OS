"""Allow seed quantity absence for zero-production planning lines.

Revision ID: 20260815_0013
Revises: 20260814_0012
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa

revision: str = "20260815_0013"
down_revision: str | Sequence[str] | None = "20260814_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"
TABLE = "righe_piano_semina"
CONSTRAINT = "ck_righe_piano_semina_quantities"
BASE_QUANTITIES = """
domanda_originaria > 0
AND quantita_consegnata_snapshot >= 0
AND domanda_residua_commerciale >= 0
AND copertura_stock >= 0
AND copertura_produzione_in_corso >= 0
AND copertura_raccolta_allocata >= 0
AND deficit_produttivo >= 0
AND buffer_quantitativo_calcolato >= 0
AND quantita_pre_granularita >= 0
AND granularita_produttiva > 0
AND quantita_produttiva_autorizzata >= 0
AND quantita_avviata >= 0
AND quantita_residua_da_avviare >= 0
AND resa_attesa > 0
"""
OLD_CHECK = BASE_QUANTITIES + "AND grammi_seme_richiesti > 0"
NEW_CHECK = BASE_QUANTITIES + """AND (
  (quantita_produttiva_autorizzata = 0 AND grammi_seme_richiesti IS NULL)
  OR
  (quantita_produttiva_autorizzata > 0
   AND grammi_seme_richiesti IS NOT NULL
   AND grammi_seme_richiesti > 0)
)"""


def _historical_commissioning_gate(bind: sa.engine.Connection) -> None:
    if bind.dialect.name != "postgresql":
        return
    statement = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM tpo.righe_piano_semina
    WHERE quantita_produttiva_autorizzata = 0
      AND grammi_seme_richiesti IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'zero-production planning line commissioning required';
  END IF;
END;
$$
"""
    if context.is_offline_mode():
        op.execute(statement)
        return
    requires_commissioning = bind.execute(sa.text("""
        SELECT EXISTS (
          SELECT 1
          FROM tpo.righe_piano_semina
          WHERE quantita_produttiva_autorizzata = 0
            AND grammi_seme_richiesti IS NOT NULL
        )
    """)).scalar_one()
    if requires_commissioning:
        raise RuntimeError("zero-production planning line commissioning required")


def _downgrade_gate(bind: sa.engine.Connection) -> None:
    if bind.dialect.name != "postgresql":
        return
    statement = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM tpo.righe_piano_semina
    WHERE grammi_seme_richiesti IS NULL
  ) THEN
    RAISE EXCEPTION 'zero-production planning line downgrade commissioning required';
  END IF;
END;
$$
"""
    if context.is_offline_mode():
        op.execute(statement)
        return
    has_null_seed_quantity = bind.execute(sa.text("""
        SELECT EXISTS (
          SELECT 1 FROM tpo.righe_piano_semina
          WHERE grammi_seme_richiesti IS NULL
        )
    """)).scalar_one()
    if has_null_seed_quantity:
        raise RuntimeError(
            "zero-production planning line downgrade commissioning required"
        )


def upgrade() -> None:
    bind = op.get_bind()
    _historical_commissioning_gate(bind)
    with op.batch_alter_table(TABLE, schema=SCHEMA) as batch:
        batch.drop_constraint(CONSTRAINT, type_="check")
        batch.alter_column(
            "grammi_seme_richiesti",
            existing_type=sa.Numeric(20, 6),
            nullable=True,
        )
        batch.create_check_constraint(CONSTRAINT, NEW_CHECK)


def downgrade() -> None:
    bind = op.get_bind()
    _downgrade_gate(bind)
    with op.batch_alter_table(TABLE, schema=SCHEMA) as batch:
        batch.drop_constraint(CONSTRAINT, type_="check")
        batch.create_check_constraint(CONSTRAINT, OLD_CHECK)
        batch.alter_column(
            "grammi_seme_richiesti",
            existing_type=sa.Numeric(20, 6),
            nullable=False,
        )
