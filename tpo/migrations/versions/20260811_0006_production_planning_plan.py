"""Create Production Planning snapshots, plans, rows, resources, and sowing links.

Revision ID: 20260811_0006
Revises: 20260811_0005
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0006"
down_revision: str | Sequence[str] | None = "20260811_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

unit_of_measure = postgresql.ENUM("SET", "GRAM", "UNIT", name="unit_of_measure", schema=SCHEMA, create_type=False)
ordine_state = postgresql.ENUM("APERTO", "PARZIALMENTE_EVASO", "EVASO", "ANNULLATO", name="ordine_state", schema=SCHEMA, create_type=False)
quantitative_buffer_policy_type = postgresql.ENUM("NONE", "PERCENTAGE", "ABSOLUTE_SET", name="quantitative_buffer_policy_type", schema=SCHEMA, create_type=False)
replanning_reason_code = postgresql.ENUM("DEMAND_CHANGED", "DELIVERY_CHANGED", "STOCK_CHANGED", "IN_PROGRESS_CHANGED", "HARVEST_RESULT_CHANGED", "PROTOCOL_CHANGED", "PLAN_LATE", "MANUAL_REPLAN_AUTHORIZED", name="replanning_reason_code", schema=SCHEMA, create_type=False)
riga_piano_semina_state = postgresql.ENUM("PIANIFICATA", "PRONTA", "AVVIATA", "SODDISFATTA", "ANNULLATA", "SOSTITUITA", "TARDIVA", name="riga_piano_semina_state", schema=SCHEMA, create_type=False)


def _fk(local: str | list[str], remote: str | list[str], name: str) -> sa.ForeignKeyConstraint:
    local_columns = [local] if isinstance(local, str) else local
    remote_columns = [remote] if isinstance(remote, str) else remote
    return sa.ForeignKeyConstraint(local_columns, [f"{SCHEMA}.{item}" for item in remote_columns], name=name, onupdate="RESTRICT", ondelete="RESTRICT")


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "replanning_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("order_line_public_id", sa.Text(), nullable=False), sa.Column("order_public_id", sa.Text(), nullable=False),
        sa.Column("order_state", ordine_state, nullable=False), sa.Column("order_version", sa.BigInteger(), nullable=False),
        sa.Column("order_line_version", sa.BigInteger(), nullable=False), sa.Column("ordered_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("delivered_quantity", sa.Numeric(20, 6), nullable=False), sa.Column("commercial_residual_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False), sa.Column("variety_public_id", sa.Text(), nullable=False),
        sa.Column("protocol_version_public_id", sa.Text(), nullable=False), sa.Column("protocol_version_number", sa.Integer(), nullable=False),
        sa.Column("protocol_valid_from", sa.Date(), nullable=False), sa.Column("protocol_valid_to", sa.Date()),
        sa.Column("policy_set_code", sa.Text(), nullable=False), sa.Column("planning_policy_version", sa.Integer(), nullable=False),
        sa.Column("quantitative_buffer_policy_type", quantitative_buffer_policy_type, nullable=False),
        sa.Column("quantitative_buffer_policy_value", sa.Numeric(20, 6)), sa.Column("temporal_buffer_minutes", sa.Integer(), nullable=False),
        sa.Column("production_granularity", sa.Numeric(20, 6), nullable=False),
        sa.Column("previous_plan_revision_public_id", sa.Text(), nullable=False), sa.Column("previous_plan_revision_version", sa.BigInteger(), nullable=False),
        sa.Column("replanning_reason_code", replanning_reason_code, nullable=False), sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("canonical_hash", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.UniqueConstraint("canonical_hash", name="uq_replanning_snapshots_canonical_hash"),
        sa.CheckConstraint("canonical_hash ~ '^[0-9a-f]{64}$'", name="ck_replanning_snapshots_canonical_hash").ddl_if(dialect="postgresql"),
        sa.CheckConstraint("order_version>=0 AND order_line_version>=0 AND previous_plan_revision_version>=0", name="ck_replanning_snapshots_versions"),
        sa.CheckConstraint("ordered_quantity>0 AND delivered_quantity>=0 AND commercial_residual_quantity>=0 AND commercial_residual_quantity=ordered_quantity-delivered_quantity AND delivered_quantity<=ordered_quantity AND production_granularity>0", name="ck_replanning_snapshots_quantities"),
        sa.CheckConstraint("protocol_valid_to IS NULL OR protocol_valid_to>protocol_valid_from", name="ck_replanning_snapshots_protocol_validity"),
        sa.CheckConstraint("(quantitative_buffer_policy_type='NONE' AND quantitative_buffer_policy_value IS NULL) OR (quantitative_buffer_policy_type<>'NONE' AND quantitative_buffer_policy_value>=0)", name="ck_replanning_snapshots_buffer"),
        sa.CheckConstraint("btrim(order_line_public_id)<>'' AND btrim(order_public_id)<>'' AND btrim(variety_public_id)<>'' AND btrim(protocol_version_public_id)<>'' AND btrim(policy_set_code)<>'' AND btrim(previous_plan_revision_public_id)<>'' AND canonical_text<>'' AND btrim(created_by)<>''", name="ck_replanning_snapshots_texts"), schema=SCHEMA,
    )
    for name, columns in (("ix_replanning_snapshots_hash", ["canonical_hash"]), ("ix_replanning_snapshots_order_line", ["order_line_public_id"]), ("ix_replanning_snapshots_previous_revision", ["previous_plan_revision_public_id"])):
        op.create_index(name, "replanning_snapshots", columns, schema=SCHEMA)

    op.create_table("piani_produzione",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True), sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("current_revision_id", sa.BigInteger()), sa.Column("stato_complessivo", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_by", sa.Text(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("public_id", name="uq_piani_produzione_public_id"),
        sa.CheckConstraint("public_id ~ '^PP-[0-9]{6,}$'", name="ck_piani_produzione_public_id").ddl_if(dialect="postgresql"),
        sa.CheckConstraint("btrim(stato_complessivo)<>''", name="ck_piani_produzione_stato"),
        sa.CheckConstraint("btrim(created_by)<>'' AND btrim(updated_by)<>''", name="ck_piani_produzione_actors"),
        sa.CheckConstraint("version>=0", name="ck_piani_produzione_version"),
        sa.CheckConstraint("updated_at>=created_at", name="ck_piani_produzione_updated"), schema=SCHEMA)
    op.create_index("uq_piani_produzione_current_revision", "piani_produzione", ["current_revision_id"], unique=True, schema=SCHEMA, postgresql_where=sa.text("current_revision_id IS NOT NULL"), sqlite_where=sa.text("current_revision_id IS NOT NULL"))
    op.create_index("ix_piani_produzione_stato", "piani_produzione", ["stato_complessivo"], schema=SCHEMA)

    op.create_table("piano_produzione_revisioni",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True), sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("piano_produzione_id", sa.BigInteger(), nullable=False), sa.Column("planning_run_id", sa.BigInteger(), nullable=False),
        sa.Column("numero_revisione", sa.Integer(), nullable=False), sa.Column("revisione_precedente_id", sa.BigInteger()),
        sa.Column("policy_version_id", sa.BigInteger(), nullable=False), sa.Column("business_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replanning_reason_code", replanning_reason_code), sa.Column("revision_request_key", sa.Text(), nullable=False),
        sa.Column("replanning_snapshot_id", sa.BigInteger()), sa.Column("sostituita_at", sa.DateTime(timezone=True)),
        sa.Column("sostituita_by", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Text(), nullable=False), sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        _fk("piano_produzione_id", "piani_produzione.id", "piano_produzione_revisioni_piano_produzione_id_fkey"),
        _fk("planning_run_id", "production_planning_runs.id", "piano_produzione_revisioni_planning_run_id_fkey"),
        _fk("policy_version_id", "production_planning_policy_versions.id", "piano_produzione_revisioni_policy_version_id_fkey"),
        _fk("revisione_precedente_id", "piano_produzione_revisioni.id", "piano_produzione_revisioni_revisione_precedente_id_fkey"),
        _fk("replanning_snapshot_id", "replanning_snapshots.id", "piano_produzione_revisioni_replanning_snapshot_id_fkey"),
        sa.UniqueConstraint("public_id", name="uq_piano_produzione_revisioni_public_id"),
        sa.UniqueConstraint("piano_produzione_id", "numero_revisione", name="uq_piano_produzione_revisioni_piano_numero"),
        sa.UniqueConstraint("revisione_precedente_id", name="uq_piano_produzione_revisioni_precedente"),
        sa.UniqueConstraint("revision_request_key", name="uq_piano_produzione_revisioni_request_key"),
        sa.UniqueConstraint("piano_produzione_id", "id", name="uq_piano_produzione_revisioni_piano_id"),
        sa.CheckConstraint("public_id ~ '^RVP-[0-9]{6,}$'", name="ck_piano_produzione_revisioni_public_id").ddl_if(dialect="postgresql"),
        sa.CheckConstraint("numero_revisione>0", name="ck_piano_produzione_revisioni_numero"),
        sa.CheckConstraint("version>=0", name="ck_piano_produzione_revisioni_version"),
        sa.CheckConstraint("(numero_revisione=1 AND revisione_precedente_id IS NULL AND replanning_reason_code IS NULL AND replanning_snapshot_id IS NULL) OR (numero_revisione>1 AND revisione_precedente_id IS NOT NULL AND replanning_reason_code IS NOT NULL AND replanning_snapshot_id IS NOT NULL)", name="ck_piano_produzione_revisioni_kind"),
        sa.CheckConstraint("revision_request_key ~ '^[0-9a-f]{64}$'", name="ck_piano_produzione_revisioni_request_key").ddl_if(dialect="postgresql"),
        sa.CheckConstraint("(sostituita_at IS NULL AND sostituita_by IS NULL) OR (sostituita_at IS NOT NULL AND sostituita_by IS NOT NULL AND btrim(sostituita_by)<>'')", name="ck_piano_produzione_revisioni_sostituzione"), schema=SCHEMA)
    op.create_index("uq_piano_produzione_revisioni_replanning_snapshot", "piano_produzione_revisioni", ["replanning_snapshot_id"], unique=True, schema=SCHEMA, postgresql_where=sa.text("replanning_snapshot_id IS NOT NULL"), sqlite_where=sa.text("replanning_snapshot_id IS NOT NULL"))
    for name, cols in (("ix_piano_produzione_revisioni_run", ["planning_run_id"]), ("ix_piano_produzione_revisioni_policy", ["policy_version_id"]), ("ix_piano_produzione_revisioni_piano_numero_desc", ["piano_produzione_id", sa.text("numero_revisione DESC")]), ("ix_piano_produzione_revisioni_precedente", ["revisione_precedente_id"]), ("ix_piano_produzione_revisioni_request_key", ["revision_request_key"])):
        op.create_index(name, "piano_produzione_revisioni", cols, schema=SCHEMA)
    if bind.dialect.name == "postgresql":
        op.create_foreign_key("piani_produzione_current_revision_id_fkey", "piani_produzione", "piano_produzione_revisioni", ["id", "current_revision_id"], ["piano_produzione_id", "id"], source_schema=SCHEMA, referent_schema=SCHEMA, onupdate="RESTRICT", ondelete="RESTRICT", deferrable=True, initially="DEFERRED")

    rps_columns = [
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True), sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("piano_revisione_id", sa.BigInteger(), nullable=False), sa.Column("riga_ordine_id", sa.BigInteger(), nullable=False),
        sa.Column("varieta_id", sa.BigInteger(), nullable=False), sa.Column("cultivar_id", sa.BigInteger(), nullable=False),
        sa.Column("cultivar_uso_id", sa.BigInteger(), nullable=False), sa.Column("protocollo_versione_id", sa.BigInteger(), nullable=False),
        sa.Column("ordine_version_attesa", sa.BigInteger(), nullable=False), sa.Column("riga_ordine_version_attesa", sa.BigInteger(), nullable=False),
        sa.Column("varieta_public_id_snapshot", sa.Text(), nullable=False), sa.Column("cultivar_snapshot", sa.Text(), nullable=False), sa.Column("uso_produttivo_snapshot", sa.Text(), nullable=False),
    ]
    for name in ("domanda_originaria", "quantita_consegnata_snapshot", "domanda_residua_commerciale", "copertura_stock", "copertura_produzione_in_corso", "copertura_raccolta_allocata", "deficit_produttivo"):
        rps_columns.append(sa.Column(name, sa.Numeric(20, 6), nullable=False))
    rps_columns.extend([sa.Column("buffer_quantitativo_tipo", quantitative_buffer_policy_type, nullable=False), sa.Column("buffer_quantitativo_valore", sa.Numeric(20, 6))])
    for name in ("buffer_quantitativo_calcolato", "quantita_pre_granularita", "granularita_produttiva", "quantita_produttiva_autorizzata"):
        rps_columns.append(sa.Column(name, sa.Numeric(20, 6), nullable=False))
    rps_columns.extend([sa.Column("quantita_avviata", sa.Numeric(20, 6), nullable=False, server_default="0"), sa.Column("quantita_residua_da_avviare", sa.Numeric(20, 6), nullable=False), sa.Column("resa_attesa", sa.Numeric(20, 6), nullable=False), sa.Column("resa_unita_misura", unit_of_measure, nullable=False), sa.Column("grammi_seme_richiesti", sa.Numeric(20, 6), nullable=False), sa.Column("unita_domanda", unit_of_measure, nullable=False), sa.Column("data_consegna", sa.Date(), nullable=False), sa.Column("harvest_window_start", sa.Date(), nullable=False), sa.Column("harvest_window_end", sa.Date(), nullable=False), sa.Column("harvest_target_at", sa.DateTime(timezone=True), nullable=False), sa.Column("sowing_at", sa.DateTime(timezone=True), nullable=False), sa.Column("light_at", sa.DateTime(timezone=True), nullable=False), sa.Column("hydration_at", sa.DateTime(timezone=True), nullable=False), sa.Column("timezone", sa.Text(), nullable=False), sa.Column("orario_semina_snapshot", sa.Time(), nullable=False), sa.Column("orario_raccolta_snapshot", sa.Time(), nullable=False), sa.Column("buffer_temporale_minuti", sa.Integer(), nullable=False), sa.Column("stato", riga_piano_semina_state, nullable=False), sa.Column("planning_key", sa.Text(), nullable=False), sa.Column("provenance", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("created_by", sa.Text(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_by", sa.Text(), nullable=False), sa.Column("version", sa.BigInteger(), nullable=False, server_default="0")])
    op.create_table("righe_piano_semina", *rps_columns,
        _fk("piano_revisione_id", "piano_produzione_revisioni.id", "righe_piano_semina_piano_revisione_id_fkey"), _fk("riga_ordine_id", "righe_ordine.id", "righe_piano_semina_riga_ordine_id_fkey"), _fk("varieta_id", "varieta.id", "righe_piano_semina_varieta_id_fkey"), _fk("cultivar_id", "cultivar.id", "righe_piano_semina_cultivar_id_fkey"), _fk("cultivar_uso_id", "cultivar_usi.id", "righe_piano_semina_cultivar_uso_id_fkey"), _fk("protocollo_versione_id", "protocollo_versioni.id", "righe_piano_semina_protocollo_versione_id_fkey"),
        sa.UniqueConstraint("public_id", name="uq_righe_piano_semina_public_id"), sa.UniqueConstraint("piano_revisione_id", "riga_ordine_id", name="uq_righe_piano_semina_revisione_riga"), sa.UniqueConstraint("piano_revisione_id", "planning_key", name="uq_righe_piano_semina_revisione_planning_key"),
        sa.CheckConstraint("public_id ~ '^RPS-[0-9]{6,}$'", name="ck_righe_piano_semina_public_id").ddl_if(dialect="postgresql"), sa.CheckConstraint("planning_key ~ '^[0-9a-f]{64}$'", name="ck_righe_piano_semina_planning_key").ddl_if(dialect="postgresql"),
        sa.CheckConstraint("ordine_version_attesa>=0 AND riga_ordine_version_attesa>=0 AND version>=0", name="ck_righe_piano_semina_versions"),
        sa.CheckConstraint("domanda_originaria>0 AND quantita_consegnata_snapshot>=0 AND domanda_residua_commerciale>=0 AND copertura_stock>=0 AND copertura_produzione_in_corso>=0 AND copertura_raccolta_allocata>=0 AND deficit_produttivo>=0 AND buffer_quantitativo_calcolato>=0 AND quantita_pre_granularita>=0 AND granularita_produttiva>0 AND quantita_produttiva_autorizzata>=0 AND quantita_avviata>=0 AND quantita_residua_da_avviare>=0 AND resa_attesa>0 AND grammi_seme_richiesti>0", name="ck_righe_piano_semina_quantities"),
        sa.CheckConstraint("quantita_consegnata_snapshot<=domanda_originaria AND domanda_residua_commerciale=domanda_originaria-quantita_consegnata_snapshot", name="ck_righe_piano_semina_commercial_residual"),
        sa.CheckConstraint("copertura_stock+copertura_produzione_in_corso+copertura_raccolta_allocata<=domanda_residua_commerciale AND deficit_produttivo=domanda_residua_commerciale-copertura_stock-copertura_produzione_in_corso-copertura_raccolta_allocata", name="ck_righe_piano_semina_coverages"),
        sa.CheckConstraint("(buffer_quantitativo_tipo='NONE' AND buffer_quantitativo_valore IS NULL AND buffer_quantitativo_calcolato=0) OR (buffer_quantitativo_tipo<>'NONE' AND buffer_quantitativo_valore IS NOT NULL AND buffer_quantitativo_valore>=0)", name="ck_righe_piano_semina_buffer"),
        sa.CheckConstraint("quantita_avviata<=quantita_produttiva_autorizzata AND quantita_residua_da_avviare=quantita_produttiva_autorizzata-quantita_avviata", name="ck_righe_piano_semina_started_quantity"),
        sa.CheckConstraint("harvest_window_end>=harvest_window_start", name="ck_righe_piano_semina_window"), sa.CheckConstraint("hydration_at<=sowing_at AND sowing_at<=light_at AND light_at<=harvest_target_at", name="ck_righe_piano_semina_timeline"), sa.CheckConstraint("timezone='Atlantic/Canary'", name="ck_righe_piano_semina_timezone"),
        sa.CheckConstraint("btrim(varieta_public_id_snapshot)<>'' AND btrim(cultivar_snapshot)<>'' AND btrim(uso_produttivo_snapshot)<>'' AND btrim(provenance)<>'' AND btrim(created_by)<>'' AND btrim(updated_by)<>''", name="ck_righe_piano_semina_texts"), schema=SCHEMA)
    for name, cols in (("ix_righe_piano_semina_revisione", ["piano_revisione_id"]), ("ix_righe_piano_semina_riga_ordine", ["riga_ordine_id"]), ("ix_righe_piano_semina_varieta", ["varieta_id"]), ("ix_righe_piano_semina_cultivar", ["cultivar_id"]), ("ix_righe_piano_semina_cultivar_uso", ["cultivar_uso_id"]), ("ix_righe_piano_semina_protocollo", ["protocollo_versione_id"]), ("ix_righe_piano_semina_stato_sowing", ["stato", "sowing_at"]), ("ix_righe_piano_semina_stato_harvest", ["stato", "harvest_target_at"]), ("ix_righe_piano_semina_data_consegna", ["data_consegna"])):
        op.create_index(name, "righe_piano_semina", cols, schema=SCHEMA)

    op.create_table("risorse_seme_pianificate", sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True), sa.Column("riga_piano_semina_id", sa.BigInteger(), nullable=False), sa.Column("cultivar_uso_id", sa.BigInteger(), nullable=False), sa.Column("protocollo_versione_id", sa.BigInteger(), nullable=False), sa.Column("grammi_richiesti", sa.Numeric(20, 6), nullable=False), sa.Column("grammi_seme_per_set", sa.Numeric(20, 6), nullable=False), sa.Column("unita_misura", unit_of_measure, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("created_by", sa.Text(), nullable=False), _fk("riga_piano_semina_id", "righe_piano_semina.id", "risorse_seme_pianificate_riga_piano_semina_id_fkey"), _fk("cultivar_uso_id", "cultivar_usi.id", "risorse_seme_pianificate_cultivar_uso_id_fkey"), _fk("protocollo_versione_id", "protocollo_versioni.id", "risorse_seme_pianificate_protocollo_versione_id_fkey"), sa.UniqueConstraint("riga_piano_semina_id", name="uq_risorse_seme_pianificate_riga"), sa.CheckConstraint("grammi_richiesti>0 AND grammi_seme_per_set>0", name="ck_risorse_seme_pianificate_grammi"), sa.CheckConstraint("unita_misura='GRAM'", name="ck_risorse_seme_pianificate_uom"), sa.CheckConstraint("btrim(created_by)<>''", name="ck_risorse_seme_pianificate_created_by"), schema=SCHEMA)
    op.create_index("ix_risorse_seme_pianificate_cultivar_uso", "risorse_seme_pianificate", ["cultivar_uso_id"], schema=SCHEMA); op.create_index("ix_risorse_seme_pianificate_protocollo", "risorse_seme_pianificate", ["protocollo_versione_id"], schema=SCHEMA)
    op.create_table("righe_piano_semina_semine", sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True), sa.Column("riga_piano_semina_id", sa.BigInteger(), nullable=False), sa.Column("semina_id", sa.BigInteger(), nullable=False), sa.Column("quantita_avviata", sa.Numeric(20, 6), nullable=False), sa.Column("unita_misura", unit_of_measure, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("created_by", sa.Text(), nullable=False), _fk("riga_piano_semina_id", "righe_piano_semina.id", "righe_piano_semina_semine_riga_piano_semina_id_fkey"), _fk("semina_id", "semine.id", "righe_piano_semina_semine_semina_id_fkey"), sa.UniqueConstraint("riga_piano_semina_id", "semina_id", name="uq_righe_piano_semina_semine_riga_semina"), sa.UniqueConstraint("semina_id", name="uq_righe_piano_semina_semine_semina"), sa.CheckConstraint("quantita_avviata>0", name="ck_righe_piano_semina_semine_quantita"), sa.CheckConstraint("unita_misura='SET'", name="ck_righe_piano_semina_semine_uom"), sa.CheckConstraint("btrim(created_by)<>''", name="ck_righe_piano_semina_semine_created_by"), schema=SCHEMA)
    for name, cols in (("ix_righe_piano_semina_semine_riga", ["riga_piano_semina_id"]), ("ix_righe_piano_semina_semine_semina", ["semina_id"]), ("ix_righe_piano_semina_semine_riga_created", ["riga_piano_semina_id", "created_at"])):
        op.create_index(name, "righe_piano_semina_semine", cols, schema=SCHEMA)


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("righe_piano_semina_semine", schema=SCHEMA); op.drop_table("risorse_seme_pianificate", schema=SCHEMA); op.drop_table("righe_piano_semina", schema=SCHEMA)
    if bind.dialect.name == "postgresql": op.drop_constraint("piani_produzione_current_revision_id_fkey", "piani_produzione", schema=SCHEMA, type_="foreignkey")
    op.drop_table("piano_produzione_revisioni", schema=SCHEMA); op.drop_table("piani_produzione", schema=SCHEMA); op.drop_table("replanning_snapshots", schema=SCHEMA)
