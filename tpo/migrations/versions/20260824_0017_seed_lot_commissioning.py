"""Seed Lot Commissioning Boundary V1 persistence.

Revision ID: 20260824_0017
Revises: 20260823_0016
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260824_0017"
down_revision: str | Sequence[str] | None = "20260823_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM tpo.lotti_seme) THEN
                    RAISE EXCEPTION
                        'seed-lot migration requires explicit legacy reconciliation';
                END IF;
            END $$
        """))

    with op.batch_alter_table("lotti_seme", schema=SCHEMA) as batch:
        batch.add_column(sa.Column("public_id", sa.Text(), nullable=False))
        batch.create_unique_constraint("uq_lotti_seme_public_id", ["public_id"])
        batch.create_unique_constraint(
            "uq_lotti_seme_id_public_id", ["id", "public_id"]
        )
        batch.create_check_constraint("ck_lotti_seme_uom_gram", "unita_misura = 'GRAM'")
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_lotti_seme_public_id", "lotti_seme",
            "public_id ~ '^LSE-[0-9]{6,}$'", schema=SCHEMA,
        )

    hash_check = (
        "canonical_payload_hash ~ '^[0-9a-f]{64}$'"
        if bind.dialect.name == "postgresql"
        else "canonical_payload_hash GLOB '[0-9a-f]*' AND length(canonical_payload_hash)=64"
    )
    op.create_table(
        "seed_lot_commissioning_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("seed_lot_id", sa.BigInteger(), nullable=True),
        sa.Column("result_public_id", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["seed_lot_id", "result_public_id"],
            [f"{SCHEMA}.lotti_seme.id", f"{SCHEMA}.lotti_seme.public_id"],
            onupdate="RESTRICT", ondelete="RESTRICT",
            name="fk_seed_lot_commissioning_authoritative_result",
        ),
        sa.UniqueConstraint(
            "operation_scope", "idempotency_key",
            name="uq_seed_lot_commissioning_request_key",
        ),
        sa.UniqueConstraint("seed_lot_id", name="uq_seed_lot_commissioning_seed_lot"),
        sa.UniqueConstraint("result_public_id", name="uq_seed_lot_commissioning_result"),
        sa.CheckConstraint("operation_scope = 'SEED_LOT_COMMISSIONING_V1'", name="ck_seed_lot_commissioning_scope"),
        sa.CheckConstraint("btrim(idempotency_key) <> ''", name="ck_seed_lot_commissioning_key"),
        sa.CheckConstraint(hash_check, name="ck_seed_lot_commissioning_hash"),
        sa.CheckConstraint(
            "(outcome = 'RESERVED' AND seed_lot_id IS NULL AND result_public_id IS NULL) OR "
            "(outcome = 'COMMITTED' AND seed_lot_id IS NOT NULL AND result_public_id IS NOT NULL)",
            name="ck_seed_lot_commissioning_outcome",
        ),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_seed_lot_commissioning_actor"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_seed_lot_commissioning_result", "seed_lot_commissioning_requests",
        ["result_public_id"], schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
            CREATE FUNCTION tpo.protect_seed_lot_constitutive_authority()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.public_id IS DISTINCT FROM OLD.public_id
                 OR NEW.semente_id IS DISTINCT FROM OLD.semente_id
                 OR NEW.numero_lotto_produttore IS DISTINCT FROM OLD.numero_lotto_produttore
              THEN
                RAISE EXCEPTION 'LOTTO_SEME constitutive authority is immutable';
              END IF;
              RETURN NEW;
            END;
            $$;
            CREATE TRIGGER protect_seed_lot_constitutive_authority
            BEFORE UPDATE ON tpo.lotti_seme
            FOR EACH ROW EXECUTE FUNCTION tpo.protect_seed_lot_constitutive_authority();

            CREATE FUNCTION tpo.protect_seed_lot_commissioning_authority()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Seed lot commissioning authority is permanent';
              END IF;
              IF OLD.outcome = 'RESERVED'
                 AND NEW.operation_scope = OLD.operation_scope
                 AND NEW.idempotency_key = OLD.idempotency_key
                 AND NEW.canonical_payload_hash = OLD.canonical_payload_hash
                 AND NEW.created_by = OLD.created_by
                 AND NEW.outcome = 'COMMITTED'
                 AND OLD.seed_lot_id IS NULL
                 AND OLD.result_public_id IS NULL
                 AND NEW.seed_lot_id IS NOT NULL
                 AND NEW.result_public_id IS NOT NULL
              THEN
                RETURN NEW;
              END IF;
              RAISE EXCEPTION 'Seed lot commissioning authority is immutable';
            END;
            $$;
            CREATE TRIGGER protect_seed_lot_commissioning_authority
            BEFORE UPDATE OR DELETE ON tpo.seed_lot_commissioning_requests
            FOR EACH ROW EXECUTE FUNCTION tpo.protect_seed_lot_commissioning_authority();
        """))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
            DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM tpo.lotti_seme) THEN
                    RAISE EXCEPTION 'cannot downgrade: commissioned seed lots exist';
                END IF;
            END $$
        """))
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
            DROP TRIGGER protect_seed_lot_commissioning_authority
              ON tpo.seed_lot_commissioning_requests;
            DROP FUNCTION tpo.protect_seed_lot_commissioning_authority();
            DROP TRIGGER protect_seed_lot_constitutive_authority ON tpo.lotti_seme;
            DROP FUNCTION tpo.protect_seed_lot_constitutive_authority();
        """))
    op.drop_index(
        "ix_seed_lot_commissioning_result",
        table_name="seed_lot_commissioning_requests", schema=SCHEMA,
    )
    op.drop_table("seed_lot_commissioning_requests", schema=SCHEMA)
    with op.batch_alter_table("lotti_seme", schema=SCHEMA) as batch:
        if bind.dialect.name == "postgresql":
            batch.drop_constraint("ck_lotti_seme_public_id", type_="check")
        batch.drop_constraint("ck_lotti_seme_uom_gram", type_="check")
        batch.drop_constraint("uq_lotti_seme_id_public_id", type_="unique")
        batch.drop_constraint("uq_lotti_seme_public_id", type_="unique")
        batch.drop_column("public_id")
