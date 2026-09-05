"""Assegnazione Fisica Authority V1 (ASSEGNAZIONE_FISICA_AUTHORITY_FREEZE.md).

Revision ID: 20260905_0032
Revises: 20260905_0031

Congela ASSEGNAZIONE_FISICA come nuovo Register append-only (Fact-only):
lega una RACCOLTA a una RIGA_ORDINE, con un riferimento opzionale a una
CONSEGNA (ASSEGNAZIONI.md). V1 copre solo la Fact di creazione. Nessun
vincolo di capienza/quantità imposto (Owner Decision
D-ASSEGNAZIONE_FISICA-capacity): quantita_assegnata è dichiarativa, nessuna
somma verificata contro raccolte.quantita o righe_ordine.quantita. Nessuna
relazione con le identita' ALL di production planning (concetti distinti,
conflitto gia' registrato in AUTHORITY_REGISTRY.yaml).

Precedente strutturale diretto: tpo.raccolte/tpo.raccolta_recording_requests
(20260830_0022_raccolta_authority.py) per la forma Register+reservation con
public_id/PermanentId e il trigger di immutabilita' totale (Fact append-only,
a differenza di ARTICOLO che e' una Configuration e ammette un trigger di
sola protezione dei campi costitutivi).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0032"
down_revision: str | Sequence[str] | None = "20260905_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

UOM = postgresql.ENUM("SET", "GRAM", "UNIT", name="unit_of_measure", schema=SCHEMA, create_type=False)

TRIGGERS_SQL = r"""
CREATE FUNCTION tpo.protect_assegnazione_fisica_authority()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  RAISE EXCEPTION 'Assegnazione fisica fact authority is immutable';
END $$;
CREATE TRIGGER protect_assegnazione_fisica_authority
BEFORE UPDATE OR DELETE ON tpo.assegnazioni_fisiche
FOR EACH ROW EXECUTE FUNCTION tpo.protect_assegnazione_fisica_authority();

CREATE FUNCTION tpo.protect_assegnazione_fisica_request()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
     AND NEW.operation_scope=OLD.operation_scope
     AND NEW.idempotency_key=OLD.idempotency_key
     AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
     AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
     AND OLD.assegnazione_fisica_id IS NULL AND OLD.result_public_id IS NULL
     AND NEW.assegnazione_fisica_id IS NOT NULL AND NEW.result_public_id IS NOT NULL THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Assegnazione fisica request authority is immutable';
END $$;
CREATE TRIGGER protect_assegnazione_fisica_request
BEFORE UPDATE OR DELETE ON tpo.assegnazione_fisica_requests
FOR EACH ROW EXECUTE FUNCTION tpo.protect_assegnazione_fisica_request();
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "assegnazioni_fisiche",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("raccolta_id", sa.BigInteger(), nullable=False),
        sa.Column("riga_ordine_id", sa.BigInteger(), nullable=False),
        sa.Column("consegna_id", sa.BigInteger()),
        sa.Column("quantita_assegnata", sa.Numeric(20, 6), nullable=False),
        sa.Column("unita_misura", UOM, nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["raccolta_id"], [f"{SCHEMA}.raccolte.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["riga_ordine_id"], [f"{SCHEMA}.righe_ordine.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["consegna_id"], [f"{SCHEMA}.consegne.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.CheckConstraint("quantita_assegnata > 0", name="ck_assegnazioni_fisiche_quantita_positive"),
        sa.CheckConstraint("btrim(motivo)<>''", name="ck_assegnazioni_fisiche_motivo_not_blank"),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_assegnazioni_fisiche_created_by_not_blank"),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_assegnazioni_fisiche_public_id_format", "assegnazioni_fisiche",
        "public_id ~ '^ASF-[0-9]{6,}$'", schema=SCHEMA,
    )
    with op.batch_alter_table("assegnazioni_fisiche", schema=SCHEMA) as batch:
        batch.create_unique_constraint("uq_assegnazioni_fisiche_id_public_id", ["id", "public_id"])
    op.create_index("ix_assegnazioni_fisiche_raccolta_id", "assegnazioni_fisiche", ["raccolta_id"], schema=SCHEMA)
    op.create_index("ix_assegnazioni_fisiche_riga_ordine_id", "assegnazioni_fisiche", ["riga_ordine_id"], schema=SCHEMA)
    op.create_index("ix_assegnazioni_fisiche_consegna_id", "assegnazioni_fisiche", ["consegna_id"], schema=SCHEMA)

    hash_check = "canonical_payload_hash ~ '^[0-9a-f]{64}$'"
    op.create_table(
        "assegnazione_fisica_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("assegnazione_fisica_id", sa.BigInteger()),
        sa.Column("result_public_id", sa.Text()),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assegnazione_fisica_id", "result_public_id"],
            [f"{SCHEMA}.assegnazioni_fisiche.id", f"{SCHEMA}.assegnazioni_fisiche.public_id"],
            onupdate="RESTRICT", ondelete="RESTRICT",
            name="fk_assegnazione_fisica_authoritative_result",
            deferrable=True, initially="DEFERRED",
        ),
        sa.UniqueConstraint("operation_scope", "idempotency_key", name="uq_assegnazione_fisica_request_key"),
        sa.UniqueConstraint("assegnazione_fisica_id", name="uq_assegnazione_fisica_request_result_entity"),
        sa.UniqueConstraint("result_public_id", name="uq_assegnazione_fisica_request_result"),
        sa.CheckConstraint("operation_scope='ASSEGNAZIONE_FISICA_V1'", name="ck_assegnazione_fisica_request_scope"),
        sa.CheckConstraint("btrim(idempotency_key)<>''", name="ck_assegnazione_fisica_request_key"),
        sa.CheckConstraint(hash_check, name="ck_assegnazione_fisica_request_hash"),
        sa.CheckConstraint(
            "(outcome='RESERVED' AND assegnazione_fisica_id IS NULL AND result_public_id IS NULL) OR "
            "(outcome='COMMITTED' AND assegnazione_fisica_id IS NOT NULL AND result_public_id IS NOT NULL)",
            name="ck_assegnazione_fisica_request_outcome",
        ),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_assegnazione_fisica_request_actor"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_assegnazione_fisica_request_result", "assegnazione_fisica_requests",
        ["result_public_id"], schema=SCHEMA,
    )

    op.execute(sa.text(
        """INSERT INTO tpo.id_sequences
           (sequence_name,identifier_type,prefix,next_value,version,updated_at,updated_by)
           VALUES ('ASSEGNAZIONE_FISICA_ID','AssegnazioneFisicaId','ASF',1,0,CURRENT_TIMESTAMP,
                   'migration-20260905-0032')"""
    ))

    op.execute(TRIGGERS_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not context.is_offline_mode():
        for table in ("assegnazioni_fisiche", "assegnazione_fisica_requests"):
            count = bind.execute(sa.text(f"SELECT count(*) FROM tpo.{table}")).scalar_one()
            if count:
                raise RuntimeError(
                    f"cannot downgrade: governed ASSEGNAZIONE FISICA authority history exists in tpo.{table}"
                )

    op.execute("""
DROP TRIGGER protect_assegnazione_fisica_request ON tpo.assegnazione_fisica_requests;
DROP FUNCTION tpo.protect_assegnazione_fisica_request();
DROP TRIGGER protect_assegnazione_fisica_authority ON tpo.assegnazioni_fisiche;
DROP FUNCTION tpo.protect_assegnazione_fisica_authority();
""")

    op.execute(sa.text(
        "DELETE FROM tpo.id_sequences WHERE sequence_name='ASSEGNAZIONE_FISICA_ID' "
        "AND identifier_type='AssegnazioneFisicaId' AND prefix='ASF' AND next_value=1 AND version=0"
    ))

    op.drop_index(
        "ix_assegnazione_fisica_request_result", table_name="assegnazione_fisica_requests",
        schema=SCHEMA,
    )
    op.drop_table("assegnazione_fisica_requests", schema=SCHEMA)

    op.drop_index("ix_assegnazioni_fisiche_consegna_id", table_name="assegnazioni_fisiche", schema=SCHEMA)
    op.drop_index("ix_assegnazioni_fisiche_riga_ordine_id", table_name="assegnazioni_fisiche", schema=SCHEMA)
    op.drop_index("ix_assegnazioni_fisiche_raccolta_id", table_name="assegnazioni_fisiche", schema=SCHEMA)
    with op.batch_alter_table("assegnazioni_fisiche", schema=SCHEMA) as batch:
        batch.drop_constraint("uq_assegnazioni_fisiche_id_public_id", type_="unique")
    op.drop_table("assegnazioni_fisiche", schema=SCHEMA)
