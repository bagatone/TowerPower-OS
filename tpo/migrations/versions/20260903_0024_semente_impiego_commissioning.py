"""Semente Impiego Commissioning Boundary V1 persistence.

Revision ID: 20260903_0024
Revises: 20260903_0023
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260903_0024"
down_revision: str | Sequence[str] | None = "20260903_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"


def upgrade() -> None:
    bind = op.get_bind()

    hash_check = (
        "canonical_payload_hash ~ '^[0-9a-f]{64}$'"
        if bind.dialect.name == "postgresql"
        else "canonical_payload_hash GLOB '[0-9a-f]*' AND length(canonical_payload_hash)=64"
    )
    op.create_table(
        "semente_impiego_commissioning_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("semente_impiego_id", sa.BigInteger(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["semente_impiego_id"], [f"{SCHEMA}.semente_impieghi.id"],
            onupdate="RESTRICT", ondelete="RESTRICT",
            name="fk_semente_impiego_commissioning_authoritative_result",
        ),
        sa.UniqueConstraint(
            "operation_scope", "idempotency_key",
            name="uq_semente_impiego_commissioning_request_key",
        ),
        sa.UniqueConstraint("semente_impiego_id", name="uq_semente_impiego_commissioning_semente_impiego"),
        sa.CheckConstraint("operation_scope = 'SEMENTE_IMPIEGO_COMMISSIONING_V1'", name="ck_semente_impiego_commissioning_scope"),
        sa.CheckConstraint("btrim(idempotency_key) <> ''", name="ck_semente_impiego_commissioning_key"),
        sa.CheckConstraint(hash_check, name="ck_semente_impiego_commissioning_hash"),
        sa.CheckConstraint(
            "(outcome = 'RESERVED' AND semente_impiego_id IS NULL) OR "
            "(outcome = 'COMMITTED' AND semente_impiego_id IS NOT NULL)",
            name="ck_semente_impiego_commissioning_outcome",
        ),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_semente_impiego_commissioning_actor"),
        schema=SCHEMA,
    )

    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
            CREATE FUNCTION tpo.protect_semente_impiego_constitutive_authority()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.semente_id IS DISTINCT FROM OLD.semente_id
                 OR NEW.cultivar_uso_id IS DISTINCT FROM OLD.cultivar_uso_id
              THEN
                RAISE EXCEPTION 'SEMENTE_IMPIEGO constitutive authority is immutable';
              END IF;
              RETURN NEW;
            END;
            $$;
            CREATE TRIGGER protect_semente_impiego_constitutive_authority
            BEFORE UPDATE ON tpo.semente_impieghi
            FOR EACH ROW EXECUTE FUNCTION tpo.protect_semente_impiego_constitutive_authority();

            CREATE FUNCTION tpo.protect_semente_impiego_commissioning_authority()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Semente impiego commissioning authority is permanent';
              END IF;
              IF OLD.outcome = 'RESERVED'
                 AND NEW.operation_scope = OLD.operation_scope
                 AND NEW.idempotency_key = OLD.idempotency_key
                 AND NEW.canonical_payload_hash = OLD.canonical_payload_hash
                 AND NEW.created_by = OLD.created_by
                 AND NEW.outcome = 'COMMITTED'
                 AND OLD.semente_impiego_id IS NULL
                 AND NEW.semente_impiego_id IS NOT NULL
              THEN
                RETURN NEW;
              END IF;
              RAISE EXCEPTION 'Semente impiego commissioning authority is immutable';
            END;
            $$;
            CREATE TRIGGER protect_semente_impiego_commissioning_authority
            BEFORE UPDATE OR DELETE ON tpo.semente_impiego_commissioning_requests
            FOR EACH ROW EXECUTE FUNCTION tpo.protect_semente_impiego_commissioning_authority();
        """))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
            DROP TRIGGER protect_semente_impiego_commissioning_authority
              ON tpo.semente_impiego_commissioning_requests;
            DROP FUNCTION tpo.protect_semente_impiego_commissioning_authority();
            DROP TRIGGER protect_semente_impiego_constitutive_authority ON tpo.semente_impieghi;
            DROP FUNCTION tpo.protect_semente_impiego_constitutive_authority();
        """))
    op.drop_table("semente_impiego_commissioning_requests", schema=SCHEMA)
