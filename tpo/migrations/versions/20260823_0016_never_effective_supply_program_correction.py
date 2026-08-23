"""Represent governed correction of never-effective supply-program versions.

Revision ID: 20260823_0016
Revises: 20260822_0015
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260823_0016"
down_revision: str | Sequence[str] | None = "20260822_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"
TABLE = "programmi_fornitura_versioni"


def upgrade() -> None:
    with op.batch_alter_table(TABLE, schema=SCHEMA) as batch:
        batch.add_column(sa.Column("voided_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("voided_by", sa.Text()))
        batch.add_column(sa.Column("void_reason", sa.Text()))
        batch.add_column(sa.Column("void_correlation_id", sa.Text()))
        batch.add_column(sa.Column("replacement_version_id", sa.BigInteger()))
        batch.create_foreign_key(
            "programmi_fornitura_versioni_replacement_version_id_fkey",
            TABLE, ["replacement_version_id"], ["id"],
            referent_schema=SCHEMA, onupdate="RESTRICT", ondelete="RESTRICT",
        )
        batch.create_unique_constraint(
            "uq_programmi_fornitura_versioni_replacement",
            ["replacement_version_id"],
        )
        batch.create_check_constraint(
            "ck_programmi_fornitura_versioni_void_complete",
            "(voided_at IS NULL AND voided_by IS NULL AND void_reason IS NULL "
            "AND void_correlation_id IS NULL AND replacement_version_id IS NULL) OR "
            "(voided_at IS NOT NULL AND btrim(voided_by) <> '' "
            "AND btrim(void_reason) <> '' AND btrim(void_correlation_id) <> '')",
        )
    op.drop_index("uq_programmi_fornitura_versioni_corrente", table_name=TABLE, schema=SCHEMA)
    op.drop_index("uq_programmi_fornitura_versioni_cliente_attivo", table_name=TABLE, schema=SCHEMA)
    op.create_index(
        "uq_programmi_fornitura_versioni_corrente", TABLE,
        ["programma_fornitura_id"], unique=True, schema=SCHEMA,
        postgresql_where=sa.text("valida_al IS NULL AND voided_at IS NULL"),
        sqlite_where=sa.text("valida_al IS NULL AND voided_at IS NULL"),
    )
    op.create_index(
        "uq_programmi_fornitura_versioni_cliente_attivo", TABLE,
        ["cliente_id"], unique=True, schema=SCHEMA,
        postgresql_where=sa.text(
            "valida_al IS NULL AND voided_at IS NULL AND stato = 'ATTIVO'"
        ),
        sqlite_where=sa.text(
            "valida_al IS NULL AND voided_at IS NULL AND stato = 'ATTIVO'"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_programmi_fornitura_versioni_cliente_attivo", table_name=TABLE, schema=SCHEMA)
    op.drop_index("uq_programmi_fornitura_versioni_corrente", table_name=TABLE, schema=SCHEMA)
    op.create_index(
        "uq_programmi_fornitura_versioni_corrente", TABLE,
        ["programma_fornitura_id"], unique=True, schema=SCHEMA,
        postgresql_where=sa.text("valida_al IS NULL"),
        sqlite_where=sa.text("valida_al IS NULL"),
    )
    op.create_index(
        "uq_programmi_fornitura_versioni_cliente_attivo", TABLE,
        ["cliente_id"], unique=True, schema=SCHEMA,
        postgresql_where=sa.text("valida_al IS NULL AND stato = 'ATTIVO'"),
        sqlite_where=sa.text("valida_al IS NULL AND stato = 'ATTIVO'"),
    )
    with op.batch_alter_table(TABLE, schema=SCHEMA) as batch:
        batch.drop_constraint("ck_programmi_fornitura_versioni_void_complete", type_="check")
        batch.drop_constraint("uq_programmi_fornitura_versioni_replacement", type_="unique")
        batch.drop_constraint(
            "programmi_fornitura_versioni_replacement_version_id_fkey", type_="foreignkey"
        )
        for column in (
            "replacement_version_id", "void_correlation_id", "void_reason",
            "voided_by", "voided_at",
        ):
            batch.drop_column(column)
