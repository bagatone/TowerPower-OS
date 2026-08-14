"""Create the allocation quantitative lifecycle register.

Revision ID: 20260814_0010
Revises: 20260812_0009
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0010"
down_revision: str | Sequence[str] | None = "20260812_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"

allocation_transition_type = postgresql.ENUM(
    "CONSUMATA",
    "RILASCIATA",
    "SOSTITUITA",
    "INVALIDA",
    name="allocation_transition_type",
    schema=SCHEMA,
    create_type=False,
)

APPEND_ONLY_SQL = """
CREATE FUNCTION tpo.fn_transizioni_allocazione_append_only()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'transizioni_allocazione is append-only';
END;
$$;

CREATE TRIGGER tr_transizioni_allocazione_append_only
BEFORE UPDATE OR DELETE ON tpo.transizioni_allocazione
FOR EACH ROW EXECUTE FUNCTION tpo.fn_transizioni_allocazione_append_only();
"""


def _historical_commissioning_gate(bind: sa.engine.Connection) -> None:
    if bind.dialect.name != "postgresql":
        return
    if context.is_offline_mode():
        op.execute("""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM tpo.allocazioni WHERE state <> 'ATTIVA') THEN
    RAISE EXCEPTION 'historical allocation commissioning required';
  END IF;
END;
$$
""")
        return
    has_terminal = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM tpo.allocazioni WHERE state <> 'ATTIVA')")
    ).scalar_one()
    if has_terminal:
        raise RuntimeError("historical allocation commissioning required")


def upgrade() -> None:
    bind = op.get_bind()
    _historical_commissioning_gate(bind)

    if bind.dialect.name == "postgresql":
        allocation_transition_type.create(bind, checkfirst=False)

    op.create_table(
        "transizioni_allocazione",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("allocation_id", sa.BigInteger(), nullable=False),
        sa.Column("transition_type", allocation_transition_type, nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("replacement_allocation_id", sa.BigInteger(), nullable=True),
        sa.Column("expected_allocation_version", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="transizioni_allocazione_pkey"),
        sa.ForeignKeyConstraint(
            ["allocation_id"],
            ["tpo.allocazioni.id"],
            name="transizioni_allocazione_allocation_id_fkey",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replacement_allocation_id"],
            ["tpo.allocazioni.id"],
            name="transizioni_allocazione_replacement_allocation_id_fkey",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_transizioni_allocazione_quantity"),
        sa.CheckConstraint(
            "expected_allocation_version >= 0",
            name="ck_transizioni_allocazione_expected_version",
        ),
        sa.CheckConstraint(
            "btrim(created_by) <> '' AND btrim(reason) <> '' AND btrim(provenance) <> ''",
            name="ck_transizioni_allocazione_texts",
        ),
        sa.CheckConstraint(
            "(transition_type = 'SOSTITUITA' AND replacement_allocation_id IS NOT NULL) "
            "OR (transition_type <> 'SOSTITUITA' AND replacement_allocation_id IS NULL)",
            name="ck_transizioni_allocazione_replacement",
        ),
        sa.CheckConstraint(
            "replacement_allocation_id IS NULL OR replacement_allocation_id <> allocation_id",
            name="ck_transizioni_allocazione_distinct_allocations",
        ),
        sa.UniqueConstraint(
            "allocation_id",
            "expected_allocation_version",
            "transition_type",
            name="uq_transizioni_allocazione_epoch_type",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_transizioni_allocazione_replacement",
        "transizioni_allocazione",
        ["replacement_allocation_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("replacement_allocation_id IS NOT NULL"),
    )
    op.create_index(
        "ix_transizioni_allocazione_allocation_epoch",
        "transizioni_allocazione",
        ["allocation_id", "expected_allocation_version", "id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_transizioni_allocazione_allocation_created",
        "transizioni_allocazione",
        ["allocation_id", "created_at", "id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_transizioni_allocazione_replacement",
        "transizioni_allocazione",
        ["replacement_allocation_id"],
        schema=SCHEMA,
        postgresql_where=sa.text("replacement_allocation_id IS NOT NULL"),
    )

    if bind.dialect.name == "postgresql":
        op.execute(APPEND_ONLY_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER tr_transizioni_allocazione_append_only "
            "ON tpo.transizioni_allocazione"
        )
        op.execute("DROP FUNCTION tpo.fn_transizioni_allocazione_append_only()")

    for name in (
        "ix_transizioni_allocazione_replacement",
        "ix_transizioni_allocazione_allocation_created",
        "ix_transizioni_allocazione_allocation_epoch",
        "uq_transizioni_allocazione_replacement",
    ):
        op.drop_index(name, table_name="transizioni_allocazione", schema=SCHEMA)
    op.drop_table("transizioni_allocazione", schema=SCHEMA)

    if bind.dialect.name == "postgresql":
        allocation_transition_type.drop(bind, checkfirst=False)
