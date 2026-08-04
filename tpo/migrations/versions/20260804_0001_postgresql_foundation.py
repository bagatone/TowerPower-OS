"""Create the PostgreSQL runtime foundation.

Revision ID: 20260804_0001
Revises: None
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260804_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"

run_state = sa.Enum(
    "SUCCESS", "SUCCESS_WITH_WARNINGS", "FAILED", name="run_state", schema=SCHEMA
)
run_message_type = sa.Enum(
    "WARNING", "ERROR", name="run_message_type", schema=SCHEMA
)
run_log_level = sa.Enum(
    "DEBUG", "INFO", "WARNING", "ERROR", name="run_log_level", schema=SCHEMA
)
json_object = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.schema.CreateSchema(SCHEMA))

    op.create_table(
        "id_sequences",
        sa.Column("sequence_name", sa.Text(), primary_key=True),
        sa.Column("identifier_type", sa.Text(), nullable=False, unique=True),
        sa.Column("prefix", sa.Text(), nullable=False, unique=True),
        sa.Column("next_value", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.CheckConstraint("next_value > 0", name="ck_id_sequences_next_value_positive"),
        sa.CheckConstraint("version >= 0", name="ck_id_sequences_version_nonnegative"),
        sa.CheckConstraint("btrim(sequence_name) <> ''", name="ck_id_sequences_name_not_blank"),
        sa.CheckConstraint("btrim(identifier_type) <> ''", name="ck_id_sequences_type_not_blank"),
        sa.CheckConstraint("btrim(prefix) <> ''", name="ck_id_sequences_prefix_not_blank"),
        sa.CheckConstraint("btrim(updated_by) <> ''", name="ck_id_sequences_updated_by_not_blank"),
        schema=SCHEMA,
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("simulation", sa.Boolean(), nullable=False),
        sa.Column("state", run_state),
        sa.Column("programmi_letti", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("righe_valutate", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("occorrenze_valutate", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("ordini_generati", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("elementi_saltati", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "completed_at IS NULL AND state IS NULL OR "
            "completed_at IS NOT NULL AND state IS NOT NULL",
            name="ck_runs_completion_state",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_runs_completed_not_before_started",
        ),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_runs_created_by_not_blank"),
        *(
            sa.CheckConstraint(f"{name} >= 0", name=f"ck_runs_{name}_nonnegative")
            for name in (
                "programmi_letti",
                "righe_valutate",
                "occorrenze_valutate",
                "ordini_generati",
                "elementi_saltati",
                "version",
            )
        ),
        schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_runs_public_id_format",
            "runs",
            "public_id ~ '^RUN-[0-9]{6,}$'",
            schema=SCHEMA,
        )
    op.create_index("ix_runs_state_started_at", "runs", ["state", "started_at"], schema=SCHEMA)
    op.create_index("ix_runs_completed_at", "runs", ["completed_at"], schema=SCHEMA)
    op.create_index(
        "ix_runs_simulation_started_at", "runs", ["simulation", "started_at"], schema=SCHEMA
    )
    op.create_table(
        "run_messaggi",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo", run_message_type, nullable=False),
        sa.Column("posizione", sa.Integer(), nullable=False),
        sa.Column("messaggio", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["run_id"], [f"{SCHEMA}.runs.id"], onupdate="RESTRICT", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("run_id", "tipo", "posizione", name="uq_run_messaggi_order"),
        sa.CheckConstraint("posizione > 0", name="ck_run_messaggi_posizione_positive"),
        sa.CheckConstraint("btrim(messaggio) <> ''", name="ck_run_messaggi_messaggio_not_blank"),
        schema=SCHEMA,
    )
    op.create_index("ix_run_messaggi_run_id", "run_messaggi", ["run_id"], schema=SCHEMA)
    op.create_index(
        "ix_run_messaggi_run_id_tipo", "run_messaggi", ["run_id", "tipo"], schema=SCHEMA
    )
    op.create_table(
        "run_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", run_log_level, nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", json_object, nullable=False, server_default=sa.text("'{}'")),
        sa.ForeignKeyConstraint(
            ["run_id"], [f"{SCHEMA}.runs.id"], onupdate="RESTRICT", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("btrim(event_type) <> ''", name="ck_run_log_event_type_not_blank"),
        sa.CheckConstraint("btrim(message) <> ''", name="ck_run_log_message_not_blank"),
        schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_run_log_context_object",
            "run_log",
            "jsonb_typeof(context) = 'object'",
            schema=SCHEMA,
        )
    op.create_index(
        "ix_run_log_run_id_occurred_at", "run_log", ["run_id", "occurred_at"], schema=SCHEMA
    )
    op.create_index(
        "ix_run_log_level_occurred_at", "run_log", ["level", "occurred_at"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_run_log_level_occurred_at", table_name="run_log", schema=SCHEMA)
    op.drop_index("ix_run_log_run_id_occurred_at", table_name="run_log", schema=SCHEMA)
    op.drop_table("run_log", schema=SCHEMA)
    op.drop_index("ix_run_messaggi_run_id_tipo", table_name="run_messaggi", schema=SCHEMA)
    op.drop_index("ix_run_messaggi_run_id", table_name="run_messaggi", schema=SCHEMA)
    op.drop_table("run_messaggi", schema=SCHEMA)
    op.drop_index("ix_runs_simulation_started_at", table_name="runs", schema=SCHEMA)
    op.drop_index("ix_runs_completed_at", table_name="runs", schema=SCHEMA)
    op.drop_index("ix_runs_state_started_at", table_name="runs", schema=SCHEMA)
    op.drop_table("runs", schema=SCHEMA)
    op.drop_table("id_sequences", schema=SCHEMA)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        run_log_level.drop(bind, checkfirst=True)
        run_message_type.drop(bind, checkfirst=True)
        run_state.drop(bind, checkfirst=True)
        op.execute(sa.schema.DropSchema(SCHEMA))
