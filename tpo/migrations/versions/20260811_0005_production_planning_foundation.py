"""Create staged Production Planning policy, run, and legacy extensions.

Revision ID: 20260811_0005
Revises: 20260810_0004
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0005"
down_revision: str | Sequence[str] | None = "20260810_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"

run_message_type = postgresql.ENUM("WARNING", "ERROR", name="run_message_type", schema=SCHEMA, create_type=False)
run_log_level = postgresql.ENUM("DEBUG", "INFO", "WARNING", "ERROR", name="run_log_level", schema=SCHEMA, create_type=False)
unit_of_measure = postgresql.ENUM("SET", "GRAM", "UNIT", name="unit_of_measure", schema=SCHEMA, create_type=False)
protocollo_versione_approval_state = postgresql.ENUM("BOZZA", "APPROVATA", "RITIRATA", name="protocollo_versione_approval_state", schema=SCHEMA, create_type=False)
production_planning_run_state = postgresql.ENUM("OPEN", "COMMITTED", "FAILED", "RECONCILIATION_REQUIRED", name="production_planning_run_state", schema=SCHEMA, create_type=False)
quantitative_buffer_policy_type = postgresql.ENUM("NONE", "PERCENTAGE", "ABSOLUTE_SET", name="quantitative_buffer_policy_type", schema=SCHEMA, create_type=False)
planning_failure_category = postgresql.ENUM("PLANNING_INPUT_INVALID", "PRODUCTION_KNOWLEDGE_INVALID", "PLANNING_INFEASIBLE", "ALLOCATION_CONFLICT", "CONCURRENCY_CONFLICT", "COMMIT_FAILED_ROLLED_BACK", "RECONCILIATION_REQUIRED", "INTERNAL_ERROR", name="planning_failure_category", schema=SCHEMA, create_type=False)
replanning_reason_code = postgresql.ENUM("DEMAND_CHANGED", "DELIVERY_CHANGED", "STOCK_CHANGED", "IN_PROGRESS_CHANGED", "HARVEST_RESULT_CHANGED", "PROTOCOL_CHANGED", "PLAN_LATE", "MANUAL_REPLAN_AUTHORIZED", name="replanning_reason_code", schema=SCHEMA, create_type=False)
riga_piano_semina_state = postgresql.ENUM("PIANIFICATA", "PRONTA", "AVVIATA", "SODDISFATTA", "ANNULLATA", "SOSTITUITA", "TARDIVA", name="riga_piano_semina_state", schema=SCHEMA, create_type=False)
planning_allocation_state = postgresql.ENUM("ATTIVA", "CONSUMATA", "RILASCIATA", "SOSTITUITA", "INVALIDA", name="planning_allocation_state", schema=SCHEMA, create_type=False)
allocation_type = postgresql.ENUM("DOMANDA", "STOCK", "PRODUZIONE_IN_CORSO", "RACCOLTA", name="allocation_type", schema=SCHEMA, create_type=False)
NEW_ENUMS = (
    protocollo_versione_approval_state, production_planning_run_state,
    quantitative_buffer_policy_type, planning_failure_category,
    replanning_reason_code, riga_piano_semina_state,
    planning_allocation_state, allocation_type,
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum in NEW_ENUMS:
            enum.create(bind, checkfirst=True)

    # Existing rows require Identity and productive commissioning. These columns
    # intentionally remain nullable in schema-expansion phase A.
    protocol_columns = (
        sa.Column("public_id", sa.Text()),
        sa.Column("stato_approvazione", protocollo_versione_approval_state),
        sa.Column("idratazione_ore", sa.Numeric(20, 6)),
        sa.Column("orario_semina_previsto", sa.Time()),
        sa.Column("orario_raccolta_target", sa.Time()),
        sa.Column("germinazione_giorni", sa.Integer()),
        sa.Column("crescita_luce_giorni", sa.Integer()),
        sa.Column("ciclo_produttivo_nominale_giorni", sa.Integer(), sa.Computed("germinazione_giorni + crescita_luce_giorni", persisted=True)),
        sa.Column("grammi_seme_per_set", sa.Numeric(20, 6)),
        sa.Column("resa_attesa", sa.Numeric(20, 6)),
        sa.Column("resa_unita_misura", unit_of_measure),
        sa.Column("granularita_produttiva", sa.Numeric(20, 6)),
        sa.Column("harvest_min_lead_giorni", sa.Integer()),
        sa.Column("harvest_max_lead_giorni", sa.Integer()),
        sa.Column("buffer_temporale_minuti", sa.Integer()),
        sa.Column("provenance", sa.Text()),
        sa.Column("approvata_at", sa.DateTime(timezone=True)),
        sa.Column("approvata_by", sa.Text()),
        sa.Column("ritirata_at", sa.DateTime(timezone=True)),
        sa.Column("ritirata_by", sa.Text()),
    )
    for column in protocol_columns:
        op.add_column("protocollo_versioni", column, schema=SCHEMA)
    op.create_index("uq_protocollo_versioni_public_id", "protocollo_versioni", ["public_id"], unique=True, schema=SCHEMA)
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE tpo.protocollo_versioni DROP CONSTRAINT ex_protocollo_versioni_validita")
        op.drop_constraint("ck_protocollo_versioni_validita", "protocollo_versioni", schema=SCHEMA, type_="check")
        op.execute("ALTER TABLE tpo.protocollo_versioni ADD CONSTRAINT ck_protocollo_versioni_public_id CHECK (public_id IS NULL OR public_id ~ '^PV-[0-9]{6,}$') NOT VALID")
        op.execute("ALTER TABLE tpo.protocollo_versioni ADD CONSTRAINT ck_protocollo_versioni_durate CHECK (idratazione_ore >= 0 AND germinazione_giorni >= 0 AND crescita_luce_giorni >= 0 AND buffer_temporale_minuti >= 0) NOT VALID")
        op.execute("ALTER TABLE tpo.protocollo_versioni ADD CONSTRAINT ck_protocollo_versioni_quantita CHECK (grammi_seme_per_set > 0 AND resa_attesa > 0 AND granularita_produttiva > 0) NOT VALID")
        op.execute("ALTER TABLE tpo.protocollo_versioni ADD CONSTRAINT ck_protocollo_versioni_harvest_lead CHECK (harvest_min_lead_giorni >= 1 AND harvest_max_lead_giorni >= harvest_min_lead_giorni) NOT VALID")
        op.execute("ALTER TABLE tpo.protocollo_versioni ADD CONSTRAINT ck_protocollo_versioni_validita CHECK (valida_al IS NULL OR valida_al > valida_dal) NOT VALID")
        op.execute("ALTER TABLE tpo.protocollo_versioni ADD CONSTRAINT ck_protocollo_versioni_lifecycle CHECK ((stato_approvazione='BOZZA' AND approvata_at IS NULL AND approvata_by IS NULL AND ritirata_at IS NULL AND ritirata_by IS NULL) OR (stato_approvazione='APPROVATA' AND approvata_at IS NOT NULL AND approvata_by IS NOT NULL AND ritirata_at IS NULL AND ritirata_by IS NULL) OR (stato_approvazione='RITIRATA' AND ritirata_at IS NOT NULL AND ritirata_by IS NOT NULL AND ((approvata_at IS NULL AND approvata_by IS NULL) OR (approvata_at IS NOT NULL AND approvata_by IS NOT NULL)))) NOT VALID")
        op.execute("ALTER TABLE tpo.protocollo_versioni ADD CONSTRAINT ex_protocollo_versioni_approvate_validita EXCLUDE USING gist (protocollo_id WITH =, daterange(valida_dal,valida_al,'[)') WITH &&) WHERE (stato_approvazione='APPROVATA')")
    op.create_index("ix_protocollo_versioni_protocollo_stato_validita", "protocollo_versioni", ["protocollo_id", "stato_approvazione", "valida_dal", "valida_al"], schema=SCHEMA)
    op.create_index("ix_protocollo_versioni_precedente", "protocollo_versioni", ["versione_precedente_id"], schema=SCHEMA)

    op.create_table(
        "production_planning_policy_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("policy_set_code", sa.Text(), nullable=False),
        sa.Column("numero_versione", sa.Integer(), nullable=False),
        sa.Column("harvest_target_strategy", sa.Text(), nullable=False),
        sa.Column("buffer_quantitativo_tipo", quantitative_buffer_policy_type, nullable=False),
        sa.Column("buffer_quantitativo_valore", sa.Numeric(20, 6)),
        sa.Column("priority_policy_code", sa.Text(), nullable=False),
        sa.Column("planning_algorithm_version", sa.Text(), nullable=False),
        sa.Column("valida_dal", sa.Date(), nullable=False), sa.Column("valida_al", sa.Date()),
        sa.Column("provenance", sa.Text(), nullable=False), sa.Column("evidenze", sa.Text()),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.UniqueConstraint("policy_set_code", "numero_versione", name="uq_production_planning_policy_versions_set_numero"),
        sa.CheckConstraint("numero_versione > 0", name="ck_production_planning_policy_versions_numero"),
        sa.CheckConstraint("harvest_target_strategy='EARLIEST_APPROVED_WINDOW'", name="ck_production_planning_policy_versions_strategy"),
        sa.CheckConstraint("(buffer_quantitativo_tipo='NONE' AND buffer_quantitativo_valore IS NULL) OR (buffer_quantitativo_tipo='PERCENTAGE' AND buffer_quantitativo_valore BETWEEN 0 AND 100) OR (buffer_quantitativo_tipo='ABSOLUTE_SET' AND buffer_quantitativo_valore >= 0)", name="ck_production_planning_policy_versions_buffer"),
        sa.CheckConstraint("valida_al IS NULL OR valida_al > valida_dal", name="ck_production_planning_policy_versions_validita"),
        sa.CheckConstraint("btrim(policy_set_code)<>'' AND btrim(priority_policy_code)<>'' AND btrim(planning_algorithm_version)<>'' AND btrim(provenance)<>'' AND btrim(approved_by)<>'' AND btrim(created_by)<>''", name="ck_production_planning_policy_versions_testi"), schema=SCHEMA,
    )
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE tpo.production_planning_policy_versions ADD CONSTRAINT ex_production_planning_policy_versions_validita EXCLUDE USING gist (policy_set_code WITH =, daterange(valida_dal,valida_al,'[)') WITH &&)")
    op.create_index("ix_production_planning_policy_versions_set_validita", "production_planning_policy_versions", ["policy_set_code", "valida_dal", "valida_al"], schema=SCHEMA)
    op.create_index("ix_production_planning_policy_versions_set_numero", "production_planning_policy_versions", ["policy_set_code", "numero_versione"], schema=SCHEMA)

    counter_columns = [sa.Column(name, sa.BigInteger(), nullable=False, server_default="0") for name in ("ordini_letti", "righe_ordine_valutate", "righe_coperte_integralmente", "righe_coperte_parzialmente", "righe_piano_generate", "allocazioni_generate", "righe_tardive", "righe_non_producibili", "elementi_saltati")]
    op.create_table(
        "production_planning_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("policy_version_id", sa.BigInteger(), nullable=False),
        sa.Column("business_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", production_planning_run_state, nullable=False, server_default="OPEN"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)), *counter_columns,
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["policy_version_id"], [f"{SCHEMA}.production_planning_policy_versions.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.UniqueConstraint("public_id", name="uq_production_planning_runs_public_id"),
        sa.CheckConstraint("public_id ~ '^RPP-[0-9]{6,}$'", name="ck_production_planning_runs_public_id").ddl_if(dialect="postgresql"),
        sa.CheckConstraint("ordini_letti>=0 AND righe_ordine_valutate>=0 AND righe_coperte_integralmente>=0 AND righe_coperte_parzialmente>=0 AND righe_piano_generate>=0 AND allocazioni_generate>=0 AND righe_tardive>=0 AND righe_non_producibili>=0 AND elementi_saltati>=0", name="ck_production_planning_runs_counters"),
        sa.CheckConstraint("version>=0", name="ck_production_planning_runs_version"),
        sa.CheckConstraint("(state='OPEN' AND completed_at IS NULL) OR (state<>'OPEN' AND completed_at IS NOT NULL AND completed_at>=started_at)", name="ck_production_planning_runs_lifecycle"),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_production_planning_runs_created_by"), schema=SCHEMA,
    )
    op.create_index("ix_production_planning_runs_state_started", "production_planning_runs", ["state", "started_at"], schema=SCHEMA)
    op.create_index("ix_production_planning_runs_business_at", "production_planning_runs", ["business_at"], schema=SCHEMA)
    op.create_index("ix_production_planning_runs_policy_version", "production_planning_runs", ["policy_version_id"], schema=SCHEMA)

    op.create_table("production_planning_run_messaggi",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True), sa.Column("planning_run_id", sa.BigInteger(), nullable=False),
        sa.Column("posizione", sa.Integer(), nullable=False), sa.Column("tipo", run_message_type, nullable=False),
        sa.Column("failure_category", planning_failure_category), sa.Column("codice", sa.Text(), nullable=False),
        sa.Column("messaggio", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["planning_run_id"], [f"{SCHEMA}.production_planning_runs.id"], name="fk_production_planning_run_messaggi_run", onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.UniqueConstraint("planning_run_id", "posizione", name="uq_production_planning_run_messaggi_run_posizione"),
        sa.CheckConstraint("posizione>0", name="ck_production_planning_run_messaggi_posizione"),
        sa.CheckConstraint("btrim(codice)<>''", name="ck_production_planning_run_messaggi_codice"),
        sa.CheckConstraint("btrim(messaggio)<>''", name="ck_production_planning_run_messaggi_testo"),
        sa.CheckConstraint("(tipo='ERROR' AND failure_category IS NOT NULL) OR (tipo<>'ERROR' AND failure_category IS NULL)", name="ck_production_planning_run_messaggi_category"), schema=SCHEMA)
    op.create_index("ix_production_planning_run_messaggi_run_tipo_posizione", "production_planning_run_messaggi", ["planning_run_id", "tipo", "posizione"], schema=SCHEMA)

    op.create_table("production_planning_run_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True), sa.Column("planning_run_id", sa.BigInteger(), nullable=False),
        sa.Column("posizione", sa.BigInteger(), nullable=False), sa.Column("livello", run_log_level, nullable=False),
        sa.Column("codice_evento", sa.Text(), nullable=False), sa.Column("messaggio", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["planning_run_id"], [f"{SCHEMA}.production_planning_runs.id"], name="fk_production_planning_run_log_run", onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.UniqueConstraint("planning_run_id", "posizione", name="uq_production_planning_run_log_run_posizione"),
        sa.CheckConstraint("posizione>0", name="ck_production_planning_run_log_posizione"),
        sa.CheckConstraint("btrim(codice_evento)<>''", name="ck_production_planning_run_log_codice"),
        sa.CheckConstraint("btrim(messaggio)<>''", name="ck_production_planning_run_log_testo"), schema=SCHEMA)
    op.create_index("ix_production_planning_run_log_run_occurred_posizione", "production_planning_run_log", ["planning_run_id", "occurred_at", "posizione"], schema=SCHEMA)

    op.add_column("ordini", sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"), schema=SCHEMA)
    op.add_column("righe_ordine", sa.Column("public_id", sa.Text()), schema=SCHEMA)
    op.add_column("righe_ordine", sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"), schema=SCHEMA)
    op.create_index("uq_righe_ordine_public_id", "righe_ordine", ["public_id"], unique=True, schema=SCHEMA)
    op.create_index("ix_righe_ordine_public_id", "righe_ordine", ["public_id"], schema=SCHEMA)
    op.add_column("semine", sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"), schema=SCHEMA)
    op.add_column("audit_eventi", sa.Column("planning_run_id", sa.BigInteger()), schema=SCHEMA)
    if bind.dialect.name == "postgresql":
        op.create_foreign_key("audit_eventi_planning_run_id_fkey", "audit_eventi", "production_planning_runs", ["planning_run_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, onupdate="RESTRICT", ondelete="RESTRICT")
    op.create_index("ix_audit_eventi_planning_run", "audit_eventi", ["planning_run_id"], schema=SCHEMA)
    op.create_index("ix_audit_eventi_planning_run_occurred", "audit_eventi", ["planning_run_id", "occurred_at"], schema=SCHEMA)
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE tpo.ordini ADD CONSTRAINT ck_ordini_version CHECK (version>=0)")
        op.execute("ALTER TABLE tpo.righe_ordine ADD CONSTRAINT ck_righe_ordine_public_id CHECK (public_id IS NULL OR public_id ~ '^RO-[0-9]{6,}$')")
        op.execute("ALTER TABLE tpo.righe_ordine ADD CONSTRAINT ck_righe_ordine_version CHECK (version>=0)")
        op.execute("ALTER TABLE tpo.semine ADD CONSTRAINT ck_semine_version CHECK (version>=0)")
        op.execute("ALTER TABLE tpo.audit_eventi ADD CONSTRAINT ck_audit_eventi_single_run_owner CHECK (num_nonnulls(run_id,planning_run_id)<=1)")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table, constraint in (("audit_eventi", "ck_audit_eventi_single_run_owner"), ("semine", "ck_semine_version"), ("righe_ordine", "ck_righe_ordine_version"), ("righe_ordine", "ck_righe_ordine_public_id"), ("ordini", "ck_ordini_version")):
            op.drop_constraint(constraint, table, schema=SCHEMA, type_="check")
    op.drop_index("ix_audit_eventi_planning_run_occurred", table_name="audit_eventi", schema=SCHEMA)
    op.drop_index("ix_audit_eventi_planning_run", table_name="audit_eventi", schema=SCHEMA)
    if bind.dialect.name == "postgresql":
        op.drop_constraint("audit_eventi_planning_run_id_fkey", "audit_eventi", schema=SCHEMA, type_="foreignkey")
    op.drop_column("audit_eventi", "planning_run_id", schema=SCHEMA)
    op.drop_column("semine", "version", schema=SCHEMA)
    op.drop_index("ix_righe_ordine_public_id", table_name="righe_ordine", schema=SCHEMA)
    op.drop_index("uq_righe_ordine_public_id", table_name="righe_ordine", schema=SCHEMA)
    op.drop_column("righe_ordine", "version", schema=SCHEMA); op.drop_column("righe_ordine", "public_id", schema=SCHEMA)
    op.drop_column("ordini", "version", schema=SCHEMA)
    op.drop_table("production_planning_run_log", schema=SCHEMA)
    op.drop_table("production_planning_run_messaggi", schema=SCHEMA)
    op.drop_table("production_planning_runs", schema=SCHEMA)
    op.drop_table("production_planning_policy_versions", schema=SCHEMA)
    op.drop_index("ix_protocollo_versioni_precedente", table_name="protocollo_versioni", schema=SCHEMA)
    op.drop_index("ix_protocollo_versioni_protocollo_stato_validita", table_name="protocollo_versioni", schema=SCHEMA)
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE tpo.protocollo_versioni DROP CONSTRAINT ex_protocollo_versioni_approvate_validita")
        for name in ("ck_protocollo_versioni_lifecycle", "ck_protocollo_versioni_validita", "ck_protocollo_versioni_harvest_lead", "ck_protocollo_versioni_quantita", "ck_protocollo_versioni_durate", "ck_protocollo_versioni_public_id"):
            op.drop_constraint(name, "protocollo_versioni", schema=SCHEMA, type_="check")
        op.execute("ALTER TABLE tpo.protocollo_versioni ADD CONSTRAINT ck_protocollo_versioni_validita CHECK (valida_al IS NULL OR valida_al >= valida_dal)")
        op.execute("ALTER TABLE tpo.protocollo_versioni ADD CONSTRAINT ex_protocollo_versioni_validita EXCLUDE USING gist (protocollo_id WITH =, daterange(valida_dal, valida_al, '[)') WITH &&)")
    op.drop_index("uq_protocollo_versioni_public_id", table_name="protocollo_versioni", schema=SCHEMA)
    for name in reversed(("public_id", "stato_approvazione", "idratazione_ore", "orario_semina_previsto", "orario_raccolta_target", "germinazione_giorni", "crescita_luce_giorni", "ciclo_produttivo_nominale_giorni", "grammi_seme_per_set", "resa_attesa", "resa_unita_misura", "granularita_produttiva", "harvest_min_lead_giorni", "harvest_max_lead_giorni", "buffer_temporale_minuti", "provenance", "approvata_at", "approvata_by", "ritirata_at", "ritirata_by")):
        op.drop_column("protocollo_versioni", name, schema=SCHEMA)
    if bind.dialect.name == "postgresql":
        for enum in reversed(NEW_ENUMS):
            enum.drop(bind, checkfirst=True)
