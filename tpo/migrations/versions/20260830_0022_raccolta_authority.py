"""Raccolta Recording Authority V1.

Revision ID: 20260830_0022
Revises: 20260826_0021
"""
from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa

revision: str = "20260830_0022"
down_revision: str | Sequence[str] | None = "20260826_0021"
branch_labels = None
depends_on = None
SCHEMA = "tpo"


def upgrade() -> None:
    bind = op.get_bind()
    if (not context.is_offline_mode()
            and bind.execute(sa.text("SELECT count(*) FROM tpo.raccolte")).scalar_one()):
        raise RuntimeError(
            "forward-only Raccolta cut-over blocked: existing RACCOLTE require reconciliation"
        )
    hash_check = (
        "canonical_payload_hash ~ '^[0-9a-f]{64}$'"
        if bind.dialect.name == "postgresql"
        else "canonical_payload_hash GLOB '[0-9a-f]*' AND length(canonical_payload_hash)=64"
    )
    with op.batch_alter_table("raccolte", schema=SCHEMA) as batch:
        batch.create_unique_constraint("uq_raccolte_id_public_id", ["id", "public_id"])
    op.create_table(
        "raccolta_recording_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("raccolta_id", sa.BigInteger()),
        sa.Column("result_public_id", sa.Text()),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["raccolta_id", "result_public_id"],
            ["tpo.raccolte.id", "tpo.raccolte.public_id"],
            onupdate="RESTRICT", ondelete="RESTRICT",
            name="fk_raccolta_recording_authoritative_result",
            deferrable=True, initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "operation_scope", "idempotency_key",
            name="uq_raccolta_recording_request_key",
        ),
        sa.UniqueConstraint("raccolta_id", name="uq_raccolta_recording_raccolta"),
        sa.UniqueConstraint("result_public_id", name="uq_raccolta_recording_result"),
        sa.CheckConstraint(
            "operation_scope='RACCOLTA_RECORDING_V1'",
            name="ck_raccolta_recording_scope",
        ),
        sa.CheckConstraint("btrim(idempotency_key)<>''", name="ck_raccolta_recording_key"),
        sa.CheckConstraint(hash_check, name="ck_raccolta_recording_hash"),
        sa.CheckConstraint(
            "(outcome='RESERVED' AND raccolta_id IS NULL AND result_public_id IS NULL) OR "
            "(outcome='COMMITTED' AND raccolta_id IS NOT NULL AND result_public_id IS NOT NULL)",
            name="ck_raccolta_recording_outcome",
        ),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_raccolta_recording_actor"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_raccolta_recording_result", "raccolta_recording_requests",
        ["result_public_id"], schema=SCHEMA,
    )
    op.execute(sa.text(
        """INSERT INTO tpo.id_sequences
           (sequence_name,identifier_type,prefix,next_value,version,updated_at,updated_by)
           VALUES ('RACCOLTA_ID','RaccoltaId','RAC',1,0,CURRENT_TIMESTAMP,
                   'migration-20260830-0022')"""
    ))
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
        CREATE FUNCTION tpo.protect_raccolta_authority()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Raccolta physical fact authority is immutable';
        END $$;
        CREATE TRIGGER protect_raccolta_authority
        BEFORE UPDATE OR DELETE ON tpo.raccolte
        FOR EACH ROW EXECUTE FUNCTION tpo.protect_raccolta_authority();

        CREATE FUNCTION tpo.protect_raccolta_recording_request()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
             AND NEW.operation_scope=OLD.operation_scope
             AND NEW.idempotency_key=OLD.idempotency_key
             AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
             AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
             AND OLD.raccolta_id IS NULL AND OLD.result_public_id IS NULL
             AND NEW.raccolta_id IS NOT NULL AND NEW.result_public_id IS NOT NULL THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'Raccolta recording request authority is immutable';
        END $$;
        CREATE TRIGGER protect_raccolta_recording_request
        BEFORE UPDATE OR DELETE ON tpo.raccolta_recording_requests
        FOR EACH ROW EXECUTE FUNCTION tpo.protect_raccolta_recording_request();
        """))


def downgrade() -> None:
    bind = op.get_bind()
    if not context.is_offline_mode():
        facts = bind.execute(sa.text("SELECT count(*) FROM tpo.raccolte")).scalar_one()
        requests = bind.execute(
            sa.text("SELECT count(*) FROM tpo.raccolta_recording_requests")
        ).scalar_one()
        if facts or requests:
            raise RuntimeError("cannot downgrade: governed RACCOLTA authority history exists")
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
        DROP TRIGGER protect_raccolta_authority ON tpo.raccolte;
        DROP FUNCTION tpo.protect_raccolta_authority();
        DROP TRIGGER protect_raccolta_recording_request ON tpo.raccolta_recording_requests;
        DROP FUNCTION tpo.protect_raccolta_recording_request();
        """))
    op.execute(sa.text(
        "DELETE FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID' "
        "AND identifier_type='RaccoltaId' AND prefix='RAC' AND next_value=1 AND version=0"
    ))
    op.drop_index(
        "ix_raccolta_recording_result", table_name="raccolta_recording_requests",
        schema=SCHEMA,
    )
    op.drop_table("raccolta_recording_requests", schema=SCHEMA)
    with op.batch_alter_table("raccolte", schema=SCHEMA) as batch:
        batch.drop_constraint("uq_raccolte_id_public_id", type_="unique")
