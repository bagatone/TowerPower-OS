"""Create authoritative pre-commit replanning disposition sets.

Revision ID: 20260822_0014
Revises: 20260815_0013
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260822_0014"
down_revision: str | Sequence[str] | None = "20260815_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "tpo"

CAUSES = (
    "DEMAND_REDUCED", "DEMAND_CANCELLED", "DEMAND_COVERED_ELSEWHERE",
    "REALLOCATION_REQUIRED", "REVISION_REPLACEMENT", "SOURCE_UNUSABLE",
    "SEEDING_FAILED", "HARVEST_UNAVAILABLE", "STOCK_QUANTITY_INVALIDATED",
    "DATA_CORRUPTION_CONFIRMED", "MANUAL_INVALIDATION_AUTHORIZED",
)


def upgrade() -> None:
    op.create_table(
        "replanning_disposition_sets",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("decision_set_key", sa.Text(), nullable=False),
        sa.Column("previous_plan_revision_id", sa.BigInteger(), nullable=False),
        sa.Column("order_line_id", sa.BigInteger(), nullable=False),
        sa.Column("replanning_reason_code", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True)),
        sa.Column("authorized_by", sa.Text()),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["previous_plan_revision_id"], [f"{SCHEMA}.piano_produzione_revisioni.id"],
            name="replanning_disposition_sets_previous_revision_fkey",
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_line_id"], [f"{SCHEMA}.righe_ordine.id"],
            name="replanning_disposition_sets_order_line_fkey",
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("decision_set_key", name="uq_replanning_disposition_sets_key"),
        sa.UniqueConstraint(
            "previous_plan_revision_id", "order_line_id", "correlation_id",
            name="uq_replanning_disposition_sets_scope_correlation",
        ),
        sa.CheckConstraint(
            "decision_set_key ~ '^[0-9a-f]{64}$'",
            name="ck_replanning_disposition_sets_key",
        ).ddl_if(dialect="postgresql"),
        sa.CheckConstraint("state IN ('DRAFT','AUTHORIZED')",
                           name="ck_replanning_disposition_sets_state"),
        sa.CheckConstraint(
            "(state='DRAFT' AND authorized_at IS NULL AND authorized_by IS NULL) OR "
            "(state='AUTHORIZED' AND authorized_at IS NOT NULL AND authorized_by IS NOT NULL "
            "AND btrim(authorized_by)<>'')",
            name="ck_replanning_disposition_sets_authorization",
        ),
        sa.CheckConstraint(
            "btrim(correlation_id)<>'' AND btrim(replanning_reason_code)<>'' "
            "AND btrim(provenance)<>'' AND btrim(created_by)<>''",
            name="ck_replanning_disposition_sets_texts",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_replanning_disposition_sets_scope",
                    "replanning_disposition_sets",
                    ["previous_plan_revision_id", "order_line_id", "state"],
                    schema=SCHEMA)

    combination = (
        "(target_disposition='RILASCIATA' AND source_usability='REUSABLE' AND "
        "disposition_cause IN ('DEMAND_REDUCED','DEMAND_CANCELLED','DEMAND_COVERED_ELSEWHERE')) OR "
        "(target_disposition='SOSTITUITA' AND source_usability='TRANSFERABLE_ONLY' AND "
        "disposition_cause IN ('REALLOCATION_REQUIRED','REVISION_REPLACEMENT')) OR "
        "(target_disposition='INVALIDA' AND source_usability='UNUSABLE' AND "
        "disposition_cause IN ('SOURCE_UNUSABLE','SEEDING_FAILED','HARVEST_UNAVAILABLE',"
        "'STOCK_QUANTITY_INVALIDATED','DATA_CORRUPTION_CONFIRMED','MANUAL_INVALIDATION_AUTHORIZED'))"
    )
    op.create_table(
        "replanning_disposition_decisions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("disposition_set_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("allocation_id", sa.BigInteger(), nullable=False),
        sa.Column("expected_allocation_version", sa.BigInteger(), nullable=False),
        sa.Column("disposition_cause", sa.Text(), nullable=False),
        sa.Column("source_usability", sa.Text(), nullable=False),
        sa.Column("observed_remaining_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("consumed_quantity_delta", sa.Numeric(20, 6), nullable=False),
        sa.Column("target_disposition", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["disposition_set_id"], [f"{SCHEMA}.replanning_disposition_sets.id"],
            name="replanning_disposition_decisions_set_fkey",
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["allocation_id"], [f"{SCHEMA}.allocazioni.id"],
            name="replanning_disposition_decisions_allocation_fkey",
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("disposition_set_id", "allocation_id",
                            name="uq_replanning_disposition_decisions_allocation"),
        sa.UniqueConstraint("disposition_set_id", "position",
                            name="uq_replanning_disposition_decisions_position"),
        sa.CheckConstraint("position>0", name="ck_replanning_disposition_decisions_position"),
        sa.CheckConstraint("expected_allocation_version>=0",
                           name="ck_replanning_disposition_decisions_version"),
        sa.CheckConstraint(
            "observed_remaining_quantity>0 AND consumed_quantity_delta>=0 "
            "AND consumed_quantity_delta<observed_remaining_quantity",
            name="ck_replanning_disposition_decisions_quantities",
        ),
        sa.CheckConstraint(combination,
                           name="ck_replanning_disposition_decisions_combination"),
        sa.CheckConstraint("btrim(reason)<>'' AND btrim(provenance)<>''",
                           name="ck_replanning_disposition_decisions_texts"),
        schema=SCHEMA,
    )
    op.create_index("ix_replanning_disposition_decisions_set_allocation",
                    "replanning_disposition_decisions",
                    ["disposition_set_id", "allocation_id"], schema=SCHEMA)

    op.create_table(
        "replanning_disposition_replacements",
        sa.Column("disposition_decision_id", sa.BigInteger(), primary_key=True),
        sa.Column("replacement_allocation_slot_key", sa.Text(), nullable=False),
        sa.Column("destination_planning_line_slot_key", sa.Text(), nullable=False),
        sa.Column("allocation_type", sa.Text(), nullable=False),
        sa.Column("source_public_id", sa.Text(), nullable=False),
        sa.Column("destination_order_line_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("unita_misura", sa.Text(), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["disposition_decision_id"], [f"{SCHEMA}.replanning_disposition_decisions.id"],
            name="replanning_disposition_replacements_decision_fkey",
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["destination_order_line_id"], [f"{SCHEMA}.righe_ordine.id"],
            name="replanning_disposition_replacements_order_line_fkey",
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("replacement_allocation_slot_key",
                            name="uq_replanning_disposition_replacements_slot"),
        sa.CheckConstraint("quantity>0",
                           name="ck_replanning_disposition_replacements_quantity"),
        sa.CheckConstraint("allocation_type IN ('DOMANDA','STOCK','PRODUZIONE_IN_CORSO','RACCOLTA')",
                           name="ck_replanning_disposition_replacements_type"),
        sa.CheckConstraint("unita_misura IN ('SET','GRAM','UNIT')",
                           name="ck_replanning_disposition_replacements_uom"),
        sa.CheckConstraint(
            "btrim(replacement_allocation_slot_key)<>'' AND "
            "btrim(destination_planning_line_slot_key)<>'' AND "
            "btrim(source_public_id)<>'' AND btrim(provenance)<>''",
            name="ck_replanning_disposition_replacements_texts",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_replanning_disposition_replacements_destination_slot",
                    "replanning_disposition_replacements",
                    ["destination_planning_line_slot_key"], schema=SCHEMA)

    with op.batch_alter_table("replanning_snapshots", schema=SCHEMA) as batch:
        batch.add_column(sa.Column("disposition_set_key", sa.Text()))
        batch.create_foreign_key(
            "replanning_snapshots_disposition_set_key_fkey",
            "replanning_disposition_sets", ["disposition_set_key"],
            ["decision_set_key"], referent_schema=SCHEMA,
            onupdate="RESTRICT", ondelete="RESTRICT",
        )
    op.create_index("uq_replanning_snapshots_disposition_set_key",
                    "replanning_snapshots", ["disposition_set_key"], unique=True,
                    schema=SCHEMA,
                    postgresql_where=sa.text("disposition_set_key IS NOT NULL"),
                    sqlite_where=sa.text("disposition_set_key IS NOT NULL"))

    if op.get_bind().dialect.name == "postgresql":
        op.execute(_POSTGRESQL_TRIGGERS)


_POSTGRESQL_TRIGGERS = r"""
CREATE FUNCTION tpo.fn_replanning_disposition_set_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.state='AUTHORIZED' THEN
    RAISE EXCEPTION 'authorized replanning disposition set is immutable';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tr_replanning_disposition_set_immutable
BEFORE UPDATE OR DELETE ON tpo.replanning_disposition_sets
FOR EACH ROW EXECUTE FUNCTION tpo.fn_replanning_disposition_set_immutable();

CREATE FUNCTION tpo.fn_replanning_disposition_child_mutable() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_id bigint; parent_state text;
BEGIN
  parent_id := CASE WHEN TG_OP='DELETE' THEN OLD.disposition_set_id ELSE NEW.disposition_set_id END;
  SELECT state INTO parent_state FROM tpo.replanning_disposition_sets WHERE id=parent_id;
  IF parent_state='AUTHORIZED' THEN
    RAISE EXCEPTION 'authorized replanning disposition children are immutable';
  END IF;
  RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER tr_replanning_disposition_decision_mutable
BEFORE INSERT OR UPDATE OR DELETE ON tpo.replanning_disposition_decisions
FOR EACH ROW EXECUTE FUNCTION tpo.fn_replanning_disposition_child_mutable();

CREATE FUNCTION tpo.fn_replanning_disposition_replacement_mutable() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE decision_id bigint; parent_state text;
BEGIN
  decision_id := CASE WHEN TG_OP='DELETE' THEN OLD.disposition_decision_id ELSE NEW.disposition_decision_id END;
  SELECT s.state INTO parent_state FROM tpo.replanning_disposition_decisions d
  JOIN tpo.replanning_disposition_sets s ON s.id=d.disposition_set_id WHERE d.id=decision_id;
  IF parent_state='AUTHORIZED' THEN
    RAISE EXCEPTION 'authorized replanning disposition replacements are immutable';
  END IF;
  RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER tr_replanning_disposition_replacement_mutable
BEFORE INSERT OR UPDATE OR DELETE ON tpo.replanning_disposition_replacements
FOR EACH ROW EXECUTE FUNCTION tpo.fn_replanning_disposition_replacement_mutable();

CREATE FUNCTION tpo.fn_replanning_disposition_validate() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE set_id bigint; bad boolean;
BEGIN
  set_id := CASE WHEN TG_TABLE_NAME='replanning_disposition_sets' THEN NEW.id
                 WHEN TG_TABLE_NAME='replanning_disposition_decisions' THEN COALESCE(NEW.disposition_set_id,OLD.disposition_set_id)
                 ELSE (SELECT disposition_set_id FROM tpo.replanning_disposition_decisions
                       WHERE id=COALESCE(NEW.disposition_decision_id,OLD.disposition_decision_id)) END;
  IF (SELECT state FROM tpo.replanning_disposition_sets WHERE id=set_id)='AUTHORIZED' THEN
    SELECT EXISTS (
      SELECT 1 FROM (
        SELECT position,row_number() OVER (ORDER BY a.public_id) AS expected
        FROM tpo.replanning_disposition_decisions d JOIN tpo.allocazioni a ON a.id=d.allocation_id
        WHERE d.disposition_set_id=set_id
      ) q WHERE position<>expected
    ) INTO bad;
    IF bad THEN RAISE EXCEPTION 'replanning disposition positions are not canonical and dense'; END IF;
    SELECT EXISTS (
      SELECT 1 FROM tpo.replanning_disposition_decisions d
      LEFT JOIN tpo.replanning_disposition_replacements r ON r.disposition_decision_id=d.id
      WHERE d.disposition_set_id=set_id
        AND ((d.target_disposition='SOSTITUITA') <> (r.disposition_decision_id IS NOT NULL))
    ) INTO bad;
    IF bad THEN RAISE EXCEPTION 'replanning replacement cardinality mismatch'; END IF;
  END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER ct_replanning_disposition_set_validate
AFTER INSERT OR UPDATE ON tpo.replanning_disposition_sets DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tpo.fn_replanning_disposition_validate();
CREATE CONSTRAINT TRIGGER ct_replanning_disposition_decision_validate
AFTER INSERT OR UPDATE OR DELETE ON tpo.replanning_disposition_decisions DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tpo.fn_replanning_disposition_validate();
CREATE CONSTRAINT TRIGGER ct_replanning_disposition_replacement_validate
AFTER INSERT OR UPDATE OR DELETE ON tpo.replanning_disposition_replacements DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tpo.fn_replanning_disposition_validate();
"""


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        used = bind.execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM tpo.replanning_disposition_sets) OR "
            "EXISTS (SELECT 1 FROM tpo.replanning_snapshots WHERE disposition_set_key IS NOT NULL)"
        )).scalar()
        if used:
            raise RuntimeError("replanning disposition authority exists; downgrade refused")
        for table, trigger in (
            ("replanning_disposition_replacements", "ct_replanning_disposition_replacement_validate"),
            ("replanning_disposition_decisions", "ct_replanning_disposition_decision_validate"),
            ("replanning_disposition_sets", "ct_replanning_disposition_set_validate"),
            ("replanning_disposition_replacements", "tr_replanning_disposition_replacement_mutable"),
            ("replanning_disposition_decisions", "tr_replanning_disposition_decision_mutable"),
            ("replanning_disposition_sets", "tr_replanning_disposition_set_immutable"),
        ):
            op.execute(f"DROP TRIGGER {trigger} ON tpo.{table}")
        op.execute("DROP FUNCTION tpo.fn_replanning_disposition_validate()")
        op.execute("DROP FUNCTION tpo.fn_replanning_disposition_replacement_mutable()")
        op.execute("DROP FUNCTION tpo.fn_replanning_disposition_child_mutable()")
        op.execute("DROP FUNCTION tpo.fn_replanning_disposition_set_immutable()")
    op.drop_index("uq_replanning_snapshots_disposition_set_key",
                  table_name="replanning_snapshots", schema=SCHEMA)
    with op.batch_alter_table("replanning_snapshots", schema=SCHEMA) as batch:
        batch.drop_constraint("replanning_snapshots_disposition_set_key_fkey",
                              type_="foreignkey")
        batch.drop_column("disposition_set_key")
    op.drop_table("replanning_disposition_replacements", schema=SCHEMA)
    op.drop_table("replanning_disposition_decisions", schema=SCHEMA)
    op.drop_table("replanning_disposition_sets", schema=SCHEMA)
