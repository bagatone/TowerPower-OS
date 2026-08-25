"""Semina Commissioning Boundary V1 persistence.

Revision ID: 20260825_0019
Revises: 20260824_0018
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "20260825_0019"
down_revision: str | Sequence[str] | None = "20260824_0018"
branch_labels = None
depends_on = None
SCHEMA = "tpo"


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("semine", schema=SCHEMA) as batch:
        batch.create_unique_constraint("uq_semine_id_public_id", ["id", "public_id"])
        batch.create_check_constraint(
            "ck_semine_commissioning_origin",
            "causa_origine IN ('PIANO_PRODUZIONE','ORDINE_CLIENTE','RIPRISTINO_STOCK')",
        )
    hash_check = ("canonical_payload_hash ~ '^[0-9a-f]{64}$'" if bind.dialect.name == "postgresql"
                  else "canonical_payload_hash GLOB '[0-9a-f]*' AND length(canonical_payload_hash)=64")
    op.create_table(
        "semina_commissioning_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("semina_id", sa.BigInteger()),
        sa.Column("result_public_id", sa.Text()),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["semina_id", "result_public_id"],
            ["tpo.semine.id", "tpo.semine.public_id"],
            onupdate="RESTRICT", ondelete="RESTRICT",
            name="fk_semina_commissioning_authoritative_result",
        ),
        sa.UniqueConstraint("operation_scope", "idempotency_key", name="uq_semina_commissioning_request_key"),
        sa.UniqueConstraint("semina_id", name="uq_semina_commissioning_semina"),
        sa.UniqueConstraint("result_public_id", name="uq_semina_commissioning_result"),
        sa.CheckConstraint("operation_scope='SEMINA_COMMISSIONING_V1'", name="ck_semina_commissioning_scope"),
        sa.CheckConstraint("btrim(idempotency_key)<>''", name="ck_semina_commissioning_key"),
        sa.CheckConstraint(hash_check, name="ck_semina_commissioning_hash"),
        sa.CheckConstraint(
            "(outcome='RESERVED' AND semina_id IS NULL AND result_public_id IS NULL) OR "
            "(outcome='COMMITTED' AND semina_id IS NOT NULL AND result_public_id IS NOT NULL)",
            name="ck_semina_commissioning_outcome",
        ),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_semina_commissioning_actor"),
        schema=SCHEMA,
    )
    op.create_index("ix_semina_commissioning_result", "semina_commissioning_requests",
                    ["result_public_id"], schema=SCHEMA)
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
        CREATE FUNCTION tpo.protect_semina_commissioning_authority()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
             AND NEW.operation_scope=OLD.operation_scope
             AND NEW.idempotency_key=OLD.idempotency_key
             AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
             AND NEW.created_by=OLD.created_by
             AND OLD.semina_id IS NULL AND OLD.result_public_id IS NULL
             AND NEW.semina_id IS NOT NULL AND NEW.result_public_id IS NOT NULL THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'Semina commissioning authority is immutable';
        END $$;
        CREATE TRIGGER protect_semina_commissioning_authority
        BEFORE UPDATE OR DELETE ON tpo.semina_commissioning_requests
        FOR EACH ROW EXECUTE FUNCTION tpo.protect_semina_commissioning_authority();

        CREATE FUNCTION tpo.protect_semina_constitutive_authority()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF NEW.public_id IS DISTINCT FROM OLD.public_id
             OR NEW.varieta_id IS DISTINCT FROM OLD.varieta_id
             OR NEW.cultivar_id IS DISTINCT FROM OLD.cultivar_id
             OR NEW.cultivar_uso_id IS DISTINCT FROM OLD.cultivar_uso_id
             OR NEW.lotto_seme_id IS DISTINCT FROM OLD.lotto_seme_id
             OR NEW.protocollo_versione_id IS DISTINCT FROM OLD.protocollo_versione_id
             OR NEW.quantita_seme IS DISTINCT FROM OLD.quantita_seme
             OR NEW.unita_misura IS DISTINCT FROM OLD.unita_misura
             OR NEW.data_avvio IS DISTINCT FROM OLD.data_avvio
             OR NEW.causa_origine IS DISTINCT FROM OLD.causa_origine
             OR NEW.cultivar_snapshot IS DISTINCT FROM OLD.cultivar_snapshot
             OR NEW.uso_produttivo_snapshot IS DISTINCT FROM OLD.uso_produttivo_snapshot
             OR NEW.lotto_seme_snapshot IS DISTINCT FROM OLD.lotto_seme_snapshot
             OR NEW.protocollo_snapshot IS DISTINCT FROM OLD.protocollo_snapshot THEN
            RAISE EXCEPTION 'SEMINA constitutive authority is immutable';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER protect_semina_constitutive_authority
        BEFORE UPDATE ON tpo.semine FOR EACH ROW
        EXECUTE FUNCTION tpo.protect_semina_constitutive_authority();
        """))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM tpo.semina_commissioning_requests WHERE outcome='COMMITTED')
          THEN RAISE EXCEPTION 'cannot downgrade: commissioned semine exist'; END IF;
        END $$;
        DROP TRIGGER protect_semina_constitutive_authority ON tpo.semine;
        DROP FUNCTION tpo.protect_semina_constitutive_authority();
        DROP TRIGGER protect_semina_commissioning_authority ON tpo.semina_commissioning_requests;
        DROP FUNCTION tpo.protect_semina_commissioning_authority();
        """))
    op.drop_index("ix_semina_commissioning_result", table_name="semina_commissioning_requests", schema=SCHEMA)
    op.drop_table("semina_commissioning_requests", schema=SCHEMA)
    with op.batch_alter_table("semine", schema=SCHEMA) as batch:
        batch.drop_constraint("ck_semine_commissioning_origin", type_="check")
        batch.drop_constraint("uq_semine_id_public_id", type_="unique")
