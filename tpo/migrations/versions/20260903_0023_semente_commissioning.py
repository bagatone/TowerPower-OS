"""Semente Commissioning Boundary V1 persistence.

Revision ID: 20260903_0023
Revises: 20260830_0022
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260903_0023"
down_revision: str | Sequence[str] | None = "20260830_0022"
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
        "semente_commissioning_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("semente_id", sa.BigInteger(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["semente_id"], [f"{SCHEMA}.sementi.id"],
            onupdate="RESTRICT", ondelete="RESTRICT",
            name="fk_semente_commissioning_authoritative_result",
        ),
        sa.UniqueConstraint(
            "operation_scope", "idempotency_key",
            name="uq_semente_commissioning_request_key",
        ),
        sa.UniqueConstraint("semente_id", name="uq_semente_commissioning_semente"),
        sa.CheckConstraint("operation_scope = 'SEMENTE_COMMISSIONING_V1'", name="ck_semente_commissioning_scope"),
        sa.CheckConstraint("btrim(idempotency_key) <> ''", name="ck_semente_commissioning_key"),
        sa.CheckConstraint(hash_check, name="ck_semente_commissioning_hash"),
        sa.CheckConstraint(
            "(outcome = 'RESERVED' AND semente_id IS NULL) OR "
            "(outcome = 'COMMITTED' AND semente_id IS NOT NULL)",
            name="ck_semente_commissioning_outcome",
        ),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_semente_commissioning_actor"),
        schema=SCHEMA,
    )

    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
            CREATE FUNCTION tpo.protect_semente_constitutive_authority()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.fornitore IS DISTINCT FROM OLD.fornitore
                 OR NEW.referenza_commerciale IS DISTINCT FROM OLD.referenza_commerciale
              THEN
                RAISE EXCEPTION 'SEMENTE constitutive authority is immutable';
              END IF;
              RETURN NEW;
            END;
            $$;
            CREATE TRIGGER protect_semente_constitutive_authority
            BEFORE UPDATE ON tpo.sementi
            FOR EACH ROW EXECUTE FUNCTION tpo.protect_semente_constitutive_authority();

            CREATE FUNCTION tpo.protect_semente_commissioning_authority()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Semente commissioning authority is permanent';
              END IF;
              IF OLD.outcome = 'RESERVED'
                 AND NEW.operation_scope = OLD.operation_scope
                 AND NEW.idempotency_key = OLD.idempotency_key
                 AND NEW.canonical_payload_hash = OLD.canonical_payload_hash
                 AND NEW.created_by = OLD.created_by
                 AND NEW.outcome = 'COMMITTED'
                 AND OLD.semente_id IS NULL
                 AND NEW.semente_id IS NOT NULL
              THEN
                RETURN NEW;
              END IF;
              RAISE EXCEPTION 'Semente commissioning authority is immutable';
            END;
            $$;
            CREATE TRIGGER protect_semente_commissioning_authority
            BEFORE UPDATE OR DELETE ON tpo.semente_commissioning_requests
            FOR EACH ROW EXECUTE FUNCTION tpo.protect_semente_commissioning_authority();
        """))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
            DROP TRIGGER protect_semente_commissioning_authority
              ON tpo.semente_commissioning_requests;
            DROP FUNCTION tpo.protect_semente_commissioning_authority();
            DROP TRIGGER protect_semente_constitutive_authority ON tpo.sementi;
            DROP FUNCTION tpo.protect_semente_constitutive_authority();
        """))
    op.drop_table("semente_commissioning_requests", schema=SCHEMA)
