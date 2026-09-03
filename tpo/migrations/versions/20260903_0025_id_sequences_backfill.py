"""Seed id_sequences for MOVIMENTO, ORDINE, CONSEGNA and RUN identities.

Revision ID: 20260903_0025
Revises: 20260903_0024
"""
from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa

revision: str = "20260903_0025"
down_revision: str | Sequence[str] | None = "20260903_0024"
branch_labels = None
depends_on = None
SCHEMA = "tpo"

_SEQUENCES = (
    ("MOVIMENTO_ID", "MovimentoId", "MOV"),
    ("ORDINE_ID", "OrdineId", "ORD"),
    ("CONSEGNA_ID", "ConsegnaId", "CON"),
    ("RUN_ID", "RunId", "RUN"),
)


def upgrade() -> None:
    for sequence_name, identifier_type, prefix in _SEQUENCES:
        op.execute(sa.text(
            "INSERT INTO tpo.id_sequences "
            "(sequence_name,identifier_type,prefix,next_value,version,updated_at,updated_by) "
            f"VALUES ('{sequence_name}','{identifier_type}','{prefix}',1,0,CURRENT_TIMESTAMP,"
            "'migration-20260903-0025')"
        ))


def downgrade() -> None:
    bind = op.get_bind()
    if not context.is_offline_mode():
        drifted = bind.execute(sa.text(
            "SELECT count(*) FROM tpo.id_sequences "
            "WHERE sequence_name IN ('MOVIMENTO_ID','ORDINE_ID','CONSEGNA_ID','RUN_ID') "
            "AND (next_value<>1 OR version<>0)"
        )).scalar_one()
        if drifted:
            raise RuntimeError(
                "cannot downgrade: one or more seeded id_sequences already advanced"
            )
    op.execute(sa.text(
        "DELETE FROM tpo.id_sequences WHERE sequence_name IN "
        "('MOVIMENTO_ID','ORDINE_ID','CONSEGNA_ID','RUN_ID') "
        "AND next_value=1 AND version=0"
    ))
