"""Create the PostgreSQL order commit schema.

Revision ID: 20260806_0002
Revises: 20260804_0001
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260806_0002"
down_revision: str | Sequence[str] | None = "20260804_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"

unit_of_measure = postgresql.ENUM(
    "SET", "GRAM", "UNIT", name="unit_of_measure", schema=SCHEMA, create_type=False
)
varieta_state = postgresql.ENUM(
    "ATTIVA",
    "IN_SPERIMENTAZIONE",
    "SOSPESA",
    "DISMESSA",
    name="varieta_state",
    schema=SCHEMA,
    create_type=False,
)
programma_fornitura_state = postgresql.ENUM(
    "ATTIVO",
    "SOSPESO",
    "TERMINATO",
    name="programma_fornitura_state",
    schema=SCHEMA,
    create_type=False,
)
tipo_ricorrenza = postgresql.ENUM(
    "SETTIMANALE",
    "QUINDICINALE",
    "MENSILE",
    "OGNI_X_GIORNI",
    "GIORNI_SETTIMANA",
    name="tipo_ricorrenza",
    schema=SCHEMA,
    create_type=False,
)
ordine_state = postgresql.ENUM(
    "APERTO",
    "PARZIALMENTE_EVASO",
    "EVASO",
    "ANNULLATO",
    name="ordine_state",
    schema=SCHEMA,
    create_type=False,
)
ordine_creation_type = postgresql.ENUM(
    "AUTOMATICO",
    "MANUALE",
    name="ordine_creation_type",
    schema=SCHEMA,
    create_type=False,
)
audit_operation = postgresql.ENUM(
    "INSERT",
    "UPDATE",
    "DELETE",
    "STATE_TRANSITION",
    "CORRECTION",
    name="audit_operation",
    schema=SCHEMA,
    create_type=False,
)
json_object = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

ENUMS = (
    unit_of_measure,
    varieta_state,
    programma_fornitura_state,
    tipo_ricorrenza,
    ordine_state,
    ordine_creation_type,
    audit_operation,
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum in ENUMS:
            enum.create(bind, checkfirst=True)

    op.create_table(
        "clienti",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("denominazione", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint("btrim(denominazione) <> ''", name="ck_clienti_denominazione_not_blank"),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_clienti_created_by_not_blank"),
        sa.CheckConstraint("btrim(updated_by) <> ''", name="ck_clienti_updated_by_not_blank"),
        sa.CheckConstraint("updated_at >= created_at", name="ck_clienti_updated_not_before_created"),
        sa.CheckConstraint("version >= 0", name="ck_clienti_version_nonnegative"),
        schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_clienti_public_id_format",
            "clienti",
            "public_id ~ '^CLI-[0-9]{6,}$'",
            schema=SCHEMA,
        )
    op.create_index("ix_clienti_denominazione", "clienti", ["denominazione"], schema=SCHEMA)

    op.create_table(
        "varieta",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("denominazione", sa.Text(), nullable=False),
        sa.Column("stato", varieta_state, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint("btrim(denominazione) <> ''", name="ck_varieta_denominazione_not_blank"),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_varieta_created_by_not_blank"),
        sa.CheckConstraint("btrim(updated_by) <> ''", name="ck_varieta_updated_by_not_blank"),
        sa.CheckConstraint("updated_at >= created_at", name="ck_varieta_updated_not_before_created"),
        sa.CheckConstraint("version >= 0", name="ck_varieta_version_nonnegative"),
        schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_varieta_public_id_format",
            "varieta",
            "public_id ~ '^VAR-[0-9]{6,}$'",
            schema=SCHEMA,
        )
    if bind.dialect.name == "postgresql":
        op.create_index(
            "uq_varieta_denominazione_normalized",
            "varieta",
            [sa.text("lower(btrim(denominazione))")],
            unique=True,
            schema=SCHEMA,
        )
    op.create_index("ix_varieta_stato", "varieta", ["stato"], schema=SCHEMA)

    op.create_table(
        "programmi_fornitura",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("cliente_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cliente_id"], [f"{SCHEMA}.clienti.id"], onupdate="RESTRICT", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("id", "cliente_id", name="uq_programmi_fornitura_id_cliente"),
        sa.CheckConstraint(
            "btrim(created_by) <> ''", name="ck_programmi_fornitura_created_by_not_blank"
        ),
        schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_programmi_fornitura_public_id_format",
            "programmi_fornitura",
            "public_id ~ '^PF-[0-9]{6,}$'",
            schema=SCHEMA,
        )
    op.create_index(
        "ix_programmi_fornitura_cliente_id",
        "programmi_fornitura",
        ["cliente_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "programmi_fornitura_versioni",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("programma_fornitura_id", sa.BigInteger(), nullable=False),
        sa.Column("cliente_id", sa.BigInteger(), nullable=False),
        sa.Column("numero_versione", sa.Integer(), nullable=False),
        sa.Column("stato", programma_fornitura_state, nullable=False),
        sa.Column("data_inizio", sa.Date(), nullable=False),
        sa.Column("data_fine", sa.Date()),
        sa.Column(
            "orario_generazione",
            sa.Time(timezone=False),
            nullable=False,
            server_default=sa.text("'05:00:00'"),
        ),
        sa.Column("finestra_operativa_giorni", sa.Integer(), nullable=False),
        sa.Column("valida_dal", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valida_al", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["programma_fornitura_id", "cliente_id"],
            [f"{SCHEMA}.programmi_fornitura.id", f"{SCHEMA}.programmi_fornitura.cliente_id"],
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "programma_fornitura_id",
            "numero_versione",
            name="uq_programmi_fornitura_versioni_numero",
        ),
        sa.CheckConstraint(
            "numero_versione > 0", name="ck_programmi_fornitura_versioni_numero_positive"
        ),
        sa.CheckConstraint(
            "data_fine IS NULL OR data_fine >= data_inizio",
            name="ck_programmi_fornitura_versioni_date",
        ),
        sa.CheckConstraint(
            "finestra_operativa_giorni >= 0",
            name="ck_programmi_fornitura_versioni_finestra_nonnegative",
        ),
        sa.CheckConstraint(
            "valida_al IS NULL OR valida_al > valida_dal",
            name="ck_programmi_fornitura_versioni_validita",
        ),
        sa.CheckConstraint(
            "btrim(created_by) <> ''",
            name="ck_programmi_fornitura_versioni_created_by_not_blank",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_programmi_fornitura_versioni_corrente",
        "programmi_fornitura_versioni",
        ["programma_fornitura_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("valida_al IS NULL"),
        sqlite_where=sa.text("valida_al IS NULL"),
    )
    op.create_index(
        "uq_programmi_fornitura_versioni_cliente_attivo",
        "programmi_fornitura_versioni",
        ["cliente_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("valida_al IS NULL AND stato = 'ATTIVO'"),
        sqlite_where=sa.text("valida_al IS NULL AND stato = 'ATTIVO'"),
    )
    op.create_index(
        "ix_programmi_fornitura_versioni_programma_cliente",
        "programmi_fornitura_versioni",
        ["programma_fornitura_id", "cliente_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_programmi_fornitura_versioni_stato_valida_al",
        "programmi_fornitura_versioni",
        ["stato", "valida_al"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_programmi_fornitura_versioni_date",
        "programmi_fornitura_versioni",
        ["data_inizio", "data_fine"],
        schema=SCHEMA,
    )

    op.create_table(
        "righe_programma_fornitura",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("programma_versione_id", sa.BigInteger(), nullable=False),
        sa.Column("posizione", sa.Integer(), nullable=False),
        sa.Column("varieta_id", sa.BigInteger(), nullable=False),
        sa.Column("quantita", sa.Numeric(20, 6), nullable=False),
        sa.Column("unita_misura", unit_of_measure, nullable=False),
        sa.Column("tipo_ricorrenza", tipo_ricorrenza, nullable=False),
        sa.Column("intervallo_giorni", sa.Integer()),
        sa.ForeignKeyConstraint(
            ["programma_versione_id"],
            [f"{SCHEMA}.programmi_fornitura_versioni.id"],
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["varieta_id"], [f"{SCHEMA}.varieta.id"], onupdate="RESTRICT", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "programma_versione_id", "posizione", name="uq_righe_programma_fornitura_posizione"
        ),
        sa.CheckConstraint("posizione > 0", name="ck_righe_programma_fornitura_posizione_positive"),
        sa.CheckConstraint("quantita > 0", name="ck_righe_programma_fornitura_quantita_positive"),
        sa.CheckConstraint(
            "(tipo_ricorrenza = 'OGNI_X_GIORNI' AND intervallo_giorni > 0) OR "
            "(tipo_ricorrenza <> 'OGNI_X_GIORNI' AND intervallo_giorni IS NULL)",
            name="ck_righe_programma_fornitura_intervallo",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_righe_programma_fornitura_varieta_id",
        "righe_programma_fornitura",
        ["varieta_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_righe_programma_fornitura_tipo_versione",
        "righe_programma_fornitura",
        ["tipo_ricorrenza", "programma_versione_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "righe_programma_giorni",
        sa.Column("riga_programma_id", sa.BigInteger(), nullable=False),
        sa.Column("giorno_iso", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["riga_programma_id"],
            [f"{SCHEMA}.righe_programma_fornitura.id"],
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("riga_programma_id", "giorno_iso"),
        sa.CheckConstraint(
            "giorno_iso BETWEEN 1 AND 7", name="ck_righe_programma_giorni_iso_range"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_righe_programma_giorni_giorno_riga",
        "righe_programma_giorni",
        ["giorno_iso", "riga_programma_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "ordini",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("cliente_id", sa.BigInteger(), nullable=False),
        sa.Column("programma_fornitura_id", sa.BigInteger()),
        sa.Column("run_id", sa.BigInteger()),
        sa.Column("data_ordine", sa.Date(), nullable=False),
        sa.Column("data_consegna_prevista", sa.Date()),
        sa.Column("stato", ordine_state, nullable=False),
        sa.Column("tipo_creazione", ordine_creation_type, nullable=False),
        sa.Column("chiave_idempotenza", sa.Text(), unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cliente_id"], [f"{SCHEMA}.clienti.id"], onupdate="RESTRICT", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["programma_fornitura_id"],
            [f"{SCHEMA}.programmi_fornitura.id"],
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], [f"{SCHEMA}.runs.id"], onupdate="RESTRICT", ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "data_consegna_prevista IS NULL OR data_consegna_prevista >= data_ordine",
            name="ck_ordini_consegna_not_before_ordine",
        ),
        sa.CheckConstraint(
            "chiave_idempotenza IS NULL OR btrim(chiave_idempotenza) <> ''",
            name="ck_ordini_chiave_idempotenza_not_blank",
        ),
        sa.CheckConstraint(
            "((tipo_creazione = 'AUTOMATICO' AND run_id IS NOT NULL AND "
            "programma_fornitura_id IS NOT NULL AND data_consegna_prevista IS NOT NULL "
            "AND chiave_idempotenza IS NOT NULL) OR "
            "(tipo_creazione = 'MANUALE' AND run_id IS NULL AND "
            "programma_fornitura_id IS NULL AND chiave_idempotenza IS NULL))",
            name="ck_ordini_tipo_creazione_metadati",
        ),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_ordini_created_by_not_blank"),
        schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_ordini_public_id_format",
            "ordini",
            "public_id ~ '^ORD-[0-9]{6,}$'",
            schema=SCHEMA,
        )
    op.create_index("ix_ordini_cliente_id", "ordini", ["cliente_id"], schema=SCHEMA)
    op.create_index(
        "ix_ordini_programma_fornitura_id",
        "ordini",
        ["programma_fornitura_id"],
        schema=SCHEMA,
    )
    op.create_index("ix_ordini_run_id", "ordini", ["run_id"], schema=SCHEMA)
    op.create_index(
        "ix_ordini_stato_data_consegna_prevista",
        "ordini",
        ["stato", "data_consegna_prevista"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ordini_cliente_data_ordine", "ordini", ["cliente_id", "data_ordine"], schema=SCHEMA
    )
    op.create_index(
        "ix_ordini_programma_data_consegna",
        "ordini",
        ["programma_fornitura_id", "data_consegna_prevista"],
        schema=SCHEMA,
    )

    op.create_table(
        "righe_ordine",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("ordine_id", sa.BigInteger(), nullable=False),
        sa.Column("posizione", sa.Integer(), nullable=False),
        sa.Column("varieta_id", sa.BigInteger(), nullable=False),
        sa.Column("quantita", sa.Numeric(20, 6), nullable=False),
        sa.Column("unita_misura", unit_of_measure, nullable=False),
        sa.ForeignKeyConstraint(
            ["ordine_id"], [f"{SCHEMA}.ordini.id"], onupdate="RESTRICT", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["varieta_id"], [f"{SCHEMA}.varieta.id"], onupdate="RESTRICT", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("ordine_id", "posizione", name="uq_righe_ordine_posizione"),
        sa.CheckConstraint("posizione > 0", name="ck_righe_ordine_posizione_positive"),
        sa.CheckConstraint("quantita > 0", name="ck_righe_ordine_quantita_positive"),
        schema=SCHEMA,
    )
    op.create_index("ix_righe_ordine_varieta_id", "righe_ordine", ["varieta_id"], schema=SCHEMA)
    op.create_index(
        "ix_righe_ordine_varieta_ordine",
        "righe_ordine",
        ["varieta_id", "ordine_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "origini_righe_ordine",
        sa.Column("riga_ordine_id", sa.BigInteger(), nullable=False),
        sa.Column("riga_programma_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["riga_ordine_id"],
            [f"{SCHEMA}.righe_ordine.id"],
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["riga_programma_id"],
            [f"{SCHEMA}.righe_programma_fornitura.id"],
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("riga_ordine_id", "riga_programma_id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_origini_righe_ordine_riga_programma_id",
        "origini_righe_ordine",
        ["riga_programma_id"],
        schema=SCHEMA,
    )

    op.create_table(
        "audit_eventi",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("run_id", sa.BigInteger()),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_public_id", sa.Text()),
        sa.Column("operation", audit_operation, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before_data", json_object),
        sa.Column("after_data", json_object),
        sa.Column("correlation_id", sa.Text()),
        sa.ForeignKeyConstraint(
            ["run_id"], [f"{SCHEMA}.runs.id"], onupdate="RESTRICT", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("btrim(actor) <> ''", name="ck_audit_eventi_actor_not_blank"),
        sa.CheckConstraint("btrim(entity_type) <> ''", name="ck_audit_eventi_entity_type_not_blank"),
        sa.CheckConstraint(
            "entity_public_id IS NULL OR btrim(entity_public_id) <> ''",
            name="ck_audit_eventi_entity_public_id_not_blank",
        ),
        sa.CheckConstraint("btrim(reason) <> ''", name="ck_audit_eventi_reason_not_blank"),
        sa.CheckConstraint(
            "correlation_id IS NULL OR btrim(correlation_id) <> ''",
            name="ck_audit_eventi_correlation_id_not_blank",
        ),
        sa.CheckConstraint(
            "before_data IS NOT NULL OR after_data IS NOT NULL",
            name="ck_audit_eventi_payload_present",
        ),
        sa.CheckConstraint(
            "operation <> 'DELETE' OR before_data IS NOT NULL",
            name="ck_audit_eventi_delete_before",
        ),
        sa.CheckConstraint(
            "operation <> 'INSERT' OR after_data IS NOT NULL",
            name="ck_audit_eventi_insert_after",
        ),
        schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_audit_eventi_before_object",
            "audit_eventi",
            "before_data IS NULL OR jsonb_typeof(before_data) = 'object'",
            schema=SCHEMA,
        )
        op.create_check_constraint(
            "ck_audit_eventi_after_object",
            "audit_eventi",
            "after_data IS NULL OR jsonb_typeof(after_data) = 'object'",
            schema=SCHEMA,
        )
    op.create_index(
        "ix_audit_eventi_entity",
        "audit_eventi",
        ["entity_type", "entity_public_id", "occurred_at"],
        schema=SCHEMA,
    )
    op.create_index("ix_audit_eventi_run_id", "audit_eventi", ["run_id"], schema=SCHEMA)
    op.create_index("ix_audit_eventi_actor", "audit_eventi", ["actor"], schema=SCHEMA)
    op.create_index("ix_audit_eventi_occurred_at", "audit_eventi", ["occurred_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_audit_eventi_occurred_at", table_name="audit_eventi", schema=SCHEMA)
    op.drop_index("ix_audit_eventi_actor", table_name="audit_eventi", schema=SCHEMA)
    op.drop_index("ix_audit_eventi_run_id", table_name="audit_eventi", schema=SCHEMA)
    op.drop_index("ix_audit_eventi_entity", table_name="audit_eventi", schema=SCHEMA)
    op.drop_table("audit_eventi", schema=SCHEMA)
    op.drop_index(
        "ix_origini_righe_ordine_riga_programma_id",
        table_name="origini_righe_ordine",
        schema=SCHEMA,
    )
    op.drop_table("origini_righe_ordine", schema=SCHEMA)
    op.drop_index("ix_righe_ordine_varieta_ordine", table_name="righe_ordine", schema=SCHEMA)
    op.drop_index("ix_righe_ordine_varieta_id", table_name="righe_ordine", schema=SCHEMA)
    op.drop_table("righe_ordine", schema=SCHEMA)
    op.drop_index("ix_ordini_programma_data_consegna", table_name="ordini", schema=SCHEMA)
    op.drop_index("ix_ordini_cliente_data_ordine", table_name="ordini", schema=SCHEMA)
    op.drop_index("ix_ordini_stato_data_consegna_prevista", table_name="ordini", schema=SCHEMA)
    op.drop_index("ix_ordini_run_id", table_name="ordini", schema=SCHEMA)
    op.drop_index("ix_ordini_programma_fornitura_id", table_name="ordini", schema=SCHEMA)
    op.drop_index("ix_ordini_cliente_id", table_name="ordini", schema=SCHEMA)
    op.drop_table("ordini", schema=SCHEMA)
    op.drop_index(
        "ix_righe_programma_giorni_giorno_riga",
        table_name="righe_programma_giorni",
        schema=SCHEMA,
    )
    op.drop_table("righe_programma_giorni", schema=SCHEMA)
    op.drop_index(
        "ix_righe_programma_fornitura_tipo_versione",
        table_name="righe_programma_fornitura",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_righe_programma_fornitura_varieta_id",
        table_name="righe_programma_fornitura",
        schema=SCHEMA,
    )
    op.drop_table("righe_programma_fornitura", schema=SCHEMA)
    op.drop_index(
        "ix_programmi_fornitura_versioni_date",
        table_name="programmi_fornitura_versioni",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_programmi_fornitura_versioni_stato_valida_al",
        table_name="programmi_fornitura_versioni",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_programmi_fornitura_versioni_programma_cliente",
        table_name="programmi_fornitura_versioni",
        schema=SCHEMA,
    )
    op.drop_index(
        "uq_programmi_fornitura_versioni_cliente_attivo",
        table_name="programmi_fornitura_versioni",
        schema=SCHEMA,
    )
    op.drop_index(
        "uq_programmi_fornitura_versioni_corrente",
        table_name="programmi_fornitura_versioni",
        schema=SCHEMA,
    )
    op.drop_table("programmi_fornitura_versioni", schema=SCHEMA)
    op.drop_index(
        "ix_programmi_fornitura_cliente_id", table_name="programmi_fornitura", schema=SCHEMA
    )
    op.drop_table("programmi_fornitura", schema=SCHEMA)
    op.drop_index("ix_varieta_stato", table_name="varieta", schema=SCHEMA)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_index(
            "uq_varieta_denominazione_normalized", table_name="varieta", schema=SCHEMA
        )
    op.drop_table("varieta", schema=SCHEMA)
    op.drop_index("ix_clienti_denominazione", table_name="clienti", schema=SCHEMA)
    op.drop_table("clienti", schema=SCHEMA)

    if bind.dialect.name == "postgresql":
        for enum in reversed(ENUMS):
            enum.drop(bind, checkfirst=True)
