"""PROGRAMMA_FORNITURA Sospensione/Riattivazione Authority V1
(PROGRAMMA_FORNITURA_SOSPENSIONE_RIATTIVAZIONE_AUTHORITY_FREEZE.md).

Revision ID: 20260916_0034
Revises: 20260915_0033

Implementa la proposta approvata (Owner Decision 2026-09-10,
docs/architecture/PROGRAMMA_FORNITURA_SOSPENSIONE_RIATTIVAZIONE_PROPOSTA.md):
chiude il gap operativo lasciato aperto da PROGRAMMI_FORNITURA.md (stato
SOSPESO definito ma nessun comando applicativo lo governa).

Due parti additive e retrocompatibili:

1. `tpo.programmi_fornitura.data_ripresa_prevista DATE NULL` — puramente
   informativa (D1), vive sull'header (non versionata): non e' un fatto del
   periodo di validita' di una specifica versione, e' un promemoria
   operativo che sopravvive alla transizione di stato stessa.
2. Due tabelle di reservation per idempotenza, simmetriche a
   `raccolta_recording_requests`/`raccolta_correzione_requests` (per non
   mischiare la semantica di idempotenza tra sospendi e riattiva):
   `programma_fornitura_sospendi_requests` e
   `programma_fornitura_riattiva_requests`. A differenza di RACCOLTA (fatti
   append-only mai riusati), lo stesso PROGRAMMA_FORNITURA puo' essere
   sospeso e riattivato piu' volte nel tempo: niente vincolo di unicita' su
   programma_fornitura_id da solo, solo su (operation_scope,idempotency_key).
   Il FK composito (programma_fornitura_id,result_numero_versione) verso
   `programmi_fornitura_versioni(programma_fornitura_id,numero_versione)`
   (gia' UNIQUE via uq_programmi_fornitura_versioni_numero) ancora il
   risultato committed a una riga versione reale, storicamente immutabile
   anche dopo transizioni successive.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa

revision: str = "20260916_0034"
down_revision: str | Sequence[str] | None = "20260915_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"


def _create_requests_table(scope: str, table_name: str, fk_name: str, unique_name: str,
                            result_extra_columns: list[sa.Column]) -> None:
    op.create_table(
        table_name,
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("programma_fornitura_id", sa.BigInteger()),
        sa.Column("result_numero_versione", sa.Integer()),
        *result_extra_columns,
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["programma_fornitura_id", "result_numero_versione"],
            [f"{SCHEMA}.programmi_fornitura_versioni.programma_fornitura_id",
             f"{SCHEMA}.programmi_fornitura_versioni.numero_versione"],
            onupdate="RESTRICT", ondelete="RESTRICT",
            name=fk_name, deferrable=True, initially="DEFERRED",
        ),
        sa.UniqueConstraint("operation_scope", "idempotency_key", name=unique_name),
        sa.CheckConstraint(f"operation_scope='{scope}'", name=f"ck_{table_name}_scope"),
        sa.CheckConstraint("btrim(idempotency_key)<>''", name=f"ck_{table_name}_key"),
        sa.CheckConstraint(
            "canonical_payload_hash ~ '^[0-9a-f]{64}$'", name=f"ck_{table_name}_hash",
        ),
        sa.CheckConstraint(
            "(outcome='RESERVED' AND programma_fornitura_id IS NULL "
            "AND result_numero_versione IS NULL) OR "
            "(outcome='COMMITTED' AND programma_fornitura_id IS NOT NULL "
            "AND result_numero_versione IS NOT NULL)",
            name=f"ck_{table_name}_outcome",
        ),
        sa.CheckConstraint("btrim(created_by)<>''", name=f"ck_{table_name}_actor"),
        schema=SCHEMA,
    )
    op.create_index(
        f"ix_{table_name}_programma", table_name, ["programma_fornitura_id"], schema=SCHEMA,
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "programmi_fornitura", sa.Column("data_ripresa_prevista", sa.Date()), schema=SCHEMA,
    )

    _create_requests_table(
        "PROGRAMMA_FORNITURA_SOSPENDI_V1", "programma_fornitura_sospendi_requests",
        "fk_pf_sospendi_result_versione", "uq_pf_sospendi_request_key",
        [sa.Column("result_data_ripresa_prevista", sa.Date())],
    )
    _create_requests_table(
        "PROGRAMMA_FORNITURA_RIATTIVA_V1", "programma_fornitura_riattiva_requests",
        "fk_pf_riattiva_result_versione", "uq_pf_riattiva_request_key",
        [],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    if not context.is_offline_mode():
        for table_name in (
            "programma_fornitura_riattiva_requests", "programma_fornitura_sospendi_requests",
        ):
            count = bind.execute(
                sa.text(f"SELECT count(*) FROM tpo.{table_name}")
            ).scalar_one()
            if count:
                raise RuntimeError(
                    f"cannot downgrade: governed {table_name} authority history exists"
                )

    op.drop_index(
        "ix_programma_fornitura_riattiva_requests_programma",
        table_name="programma_fornitura_riattiva_requests", schema=SCHEMA,
    )
    op.drop_table("programma_fornitura_riattiva_requests", schema=SCHEMA)
    op.drop_index(
        "ix_programma_fornitura_sospendi_requests_programma",
        table_name="programma_fornitura_sospendi_requests", schema=SCHEMA,
    )
    op.drop_table("programma_fornitura_sospendi_requests", schema=SCHEMA)

    op.drop_column("programmi_fornitura", "data_ripresa_prevista", schema=SCHEMA)
