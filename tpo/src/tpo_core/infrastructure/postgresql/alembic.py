"""Configurazione programmatica e metadata delle migrazioni PostgreSQL."""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects import postgresql
from sqlalchemy.pool import NullPool

from .settings import PostgreSQLSettings

SCHEMA_NAME = "tpo"
MIGRATIONS_PATH = Path(__file__).parents[4] / "migrations"

RUN_STATE = sa.Enum(
    "SUCCESS",
    "SUCCESS_WITH_WARNINGS",
    "FAILED",
    name="run_state",
    schema=SCHEMA_NAME,
)
RUN_MESSAGE_TYPE = sa.Enum(
    "WARNING",
    "ERROR",
    name="run_message_type",
    schema=SCHEMA_NAME,
)
RUN_LOG_LEVEL = sa.Enum(
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    name="run_log_level",
    schema=SCHEMA_NAME,
)
JSON_OBJECT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

METADATA = sa.MetaData(schema=SCHEMA_NAME)

ID_SEQUENCES = sa.Table(
    "id_sequences",
    METADATA,
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
)

RUNS = sa.Table(
    "runs",
    METADATA,
    sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
    sa.Column("public_id", sa.Text(), nullable=False, unique=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    sa.Column("simulation", sa.Boolean(), nullable=False),
    sa.Column("state", RUN_STATE),
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
    sa.CheckConstraint(
        "public_id ~ '^RUN-[0-9]{6,}$'",
        name="ck_runs_public_id_format",
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
)

RUN_MESSAGGI = sa.Table(
    "run_messaggi",
    METADATA,
    sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
    sa.Column(
        "run_id",
        sa.BigInteger(),
        sa.ForeignKey(f"{SCHEMA_NAME}.runs.id", onupdate="RESTRICT", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("tipo", RUN_MESSAGE_TYPE, nullable=False),
    sa.Column("posizione", sa.Integer(), nullable=False),
    sa.Column("messaggio", sa.Text(), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.UniqueConstraint("run_id", "tipo", "posizione", name="uq_run_messaggi_order"),
    sa.CheckConstraint("posizione > 0", name="ck_run_messaggi_posizione_positive"),
    sa.CheckConstraint("btrim(messaggio) <> ''", name="ck_run_messaggi_messaggio_not_blank"),
)

RUN_LOG = sa.Table(
    "run_log",
    METADATA,
    sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
    sa.Column(
        "run_id",
        sa.BigInteger(),
        sa.ForeignKey(f"{SCHEMA_NAME}.runs.id", onupdate="RESTRICT", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("level", RUN_LOG_LEVEL, nullable=False),
    sa.Column("event_type", sa.Text(), nullable=False),
    sa.Column("message", sa.Text(), nullable=False),
    sa.Column("context", JSON_OBJECT, nullable=False, server_default=sa.text("'{}'")),
    sa.CheckConstraint("btrim(event_type) <> ''", name="ck_run_log_event_type_not_blank"),
    sa.CheckConstraint("btrim(message) <> ''", name="ck_run_log_message_not_blank"),
    sa.CheckConstraint("jsonb_typeof(context) = 'object'", name="ck_run_log_context_object"),
)

sa.Index("ix_runs_state_started_at", RUNS.c.state, RUNS.c.started_at)
sa.Index("ix_runs_completed_at", RUNS.c.completed_at)
sa.Index("ix_runs_simulation_started_at", RUNS.c.simulation, RUNS.c.started_at)
sa.Index("ix_run_messaggi_run_id", RUN_MESSAGGI.c.run_id)
sa.Index("ix_run_messaggi_run_id_tipo", RUN_MESSAGGI.c.run_id, RUN_MESSAGGI.c.tipo)
sa.Index("ix_run_log_run_id_occurred_at", RUN_LOG.c.run_id, RUN_LOG.c.occurred_at)
sa.Index("ix_run_log_level_occurred_at", RUN_LOG.c.level, RUN_LOG.c.occurred_at)


def make_config(*, connection: sa.Connection | None = None) -> Config:
    """Costruisce una configurazione Alembic senza file o credenziali globali."""

    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def migration_url(settings: PostgreSQLSettings) -> sa.URL:
    """Costruisce una URL strutturata la cui rappresentazione oscura la password."""

    return sa.URL.create(
        "postgresql+psycopg",
        username=settings.user,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database=settings.database,
        query={
            "sslmode": settings.sslmode,
            "connect_timeout": str(settings.connect_timeout_seconds),
        },
    )


def upgrade(settings: PostgreSQLSettings, revision: str = "head") -> None:
    """Applica esplicitamente le migrazioni; nessuna connessione avviene all'import."""

    engine = sa.create_engine(migration_url(settings), poolclass=NullPool)
    try:
        with engine.connect() as connection:
            command.upgrade(make_config(connection=connection), revision)
    finally:
        engine.dispose()
