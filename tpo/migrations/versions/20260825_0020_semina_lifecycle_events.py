"""Semina Lifecycle Event Authority V1.

Revision ID: 20260825_0020
Revises: 20260825_0019
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260825_0020"
down_revision: str | Sequence[str] | None = "20260825_0019"
branch_labels = None
depends_on = None
SCHEMA = "tpo"


def upgrade() -> None:
    bind = op.get_bind()
    state = postgresql.ENUM(name="semina_state", schema=SCHEMA, create_type=False)
    outcome = postgresql.ENUM(name="semina_esito", schema=SCHEMA, create_type=False)
    json_object = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    hash_check = ("canonical_payload_hash ~ '^[0-9a-f]{64}$'" if bind.dialect.name == "postgresql"
                  else "canonical_payload_hash GLOB '[0-9a-f]*' AND length(canonical_payload_hash)=64")
    op.create_table(
        "semina_lifecycle_transition_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("result_event_id", sa.BigInteger()),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.UniqueConstraint("operation_scope", "idempotency_key", name="uq_semina_lifecycle_request_key"),
        sa.UniqueConstraint("result_event_id", name="uq_semina_lifecycle_request_result"),
        sa.CheckConstraint("operation_scope='SEMINA_LIFECYCLE_TRANSITION_V1'", name="ck_semina_lifecycle_request_scope"),
        sa.CheckConstraint("btrim(idempotency_key)<>''", name="ck_semina_lifecycle_request_key"),
        sa.CheckConstraint(hash_check, name="ck_semina_lifecycle_request_hash"),
        sa.CheckConstraint(
            "(outcome='RESERVED' AND result_event_id IS NULL) OR "
            "(outcome='COMMITTED' AND result_event_id IS NOT NULL)",
            name="ck_semina_lifecycle_request_outcome",
        ),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_semina_lifecycle_request_actor"),
        schema=SCHEMA,
    )
    op.create_table(
        "semina_lifecycle_eventi",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("request_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("semina_id", sa.BigInteger(), nullable=False),
        sa.Column("semina_public_id", sa.Text(), nullable=False),
        sa.Column("from_state", state, nullable=False),
        sa.Column("to_state", state, nullable=False),
        sa.Column("esito_finale", outcome),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version_before", sa.BigInteger(), nullable=False),
        sa.Column("version_after", sa.BigInteger(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("provenance", json_object, nullable=False),
        sa.ForeignKeyConstraint(["request_id"], [f"{SCHEMA}.semina_lifecycle_transition_requests.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["semina_id", "semina_public_id"], [f"{SCHEMA}.semine.id", f"{SCHEMA}.semine.public_id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "request_id", name="uq_semina_lifecycle_event_id_request"),
        sa.CheckConstraint("from_state<>to_state", name="ck_semina_lifecycle_event_state_change"),
        sa.CheckConstraint("(to_state='CHIUSA' AND esito_finale IS NOT NULL) OR (to_state<>'CHIUSA' AND esito_finale IS NULL)", name="ck_semina_lifecycle_event_outcome"),
        sa.CheckConstraint("version_before>=0 AND version_after=version_before+1", name="ck_semina_lifecycle_event_versions"),
        sa.CheckConstraint("btrim(actor)<>'' AND btrim(reason)<>'' AND btrim(correlation_id)<>''", name="ck_semina_lifecycle_event_context"),
        schema=SCHEMA,
    )
    op.create_index("ix_semina_lifecycle_event_semina_effective", "semina_lifecycle_eventi", ["semina_id", "effective_at"], schema=SCHEMA)
    op.create_index("ix_semina_lifecycle_event_correlation", "semina_lifecycle_eventi", ["correlation_id"], schema=SCHEMA)
    if bind.dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_semina_lifecycle_request_authoritative_result",
            "semina_lifecycle_transition_requests", "semina_lifecycle_eventi",
            ["result_event_id", "id"], ["id", "request_id"],
            source_schema=SCHEMA, referent_schema=SCHEMA,
            onupdate="RESTRICT", ondelete="RESTRICT",
            deferrable=True, initially="DEFERRED",
        )
        op.create_check_constraint("ck_semina_lifecycle_event_provenance_object", "semina_lifecycle_eventi", "jsonb_typeof(provenance)='object'", schema=SCHEMA)
        op.execute(sa.text("""
        CREATE FUNCTION tpo.protect_semina_lifecycle_event()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Semina lifecycle event authority is immutable';
        END $$;
        CREATE TRIGGER protect_semina_lifecycle_event
        BEFORE UPDATE OR DELETE ON tpo.semina_lifecycle_eventi
        FOR EACH ROW EXECUTE FUNCTION tpo.protect_semina_lifecycle_event();

        CREATE FUNCTION tpo.protect_semina_lifecycle_request()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
          IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
             AND NEW.operation_scope=OLD.operation_scope
             AND NEW.idempotency_key=OLD.idempotency_key
             AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
             AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
             AND OLD.result_event_id IS NULL AND NEW.result_event_id IS NOT NULL THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'Semina lifecycle request authority is immutable';
        END $$;
        CREATE TRIGGER protect_semina_lifecycle_request
        BEFORE UPDATE OR DELETE ON tpo.semina_lifecycle_transition_requests
        FOR EACH ROW EXECUTE FUNCTION tpo.protect_semina_lifecycle_request();
        """))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM tpo.semina_lifecycle_eventi) THEN
            RAISE EXCEPTION 'cannot downgrade: semina lifecycle history exists';
          END IF;
        END $$;
        DROP TRIGGER protect_semina_lifecycle_event ON tpo.semina_lifecycle_eventi;
        DROP FUNCTION tpo.protect_semina_lifecycle_event();
        DROP TRIGGER protect_semina_lifecycle_request ON tpo.semina_lifecycle_transition_requests;
        DROP FUNCTION tpo.protect_semina_lifecycle_request();
        """))
        op.drop_constraint(
            "fk_semina_lifecycle_request_authoritative_result",
            "semina_lifecycle_transition_requests", schema=SCHEMA, type_="foreignkey",
        )
    op.drop_index("ix_semina_lifecycle_event_correlation", table_name="semina_lifecycle_eventi", schema=SCHEMA)
    op.drop_index("ix_semina_lifecycle_event_semina_effective", table_name="semina_lifecycle_eventi", schema=SCHEMA)
    op.drop_table("semina_lifecycle_eventi", schema=SCHEMA)
    op.drop_table("semina_lifecycle_transition_requests", schema=SCHEMA)
