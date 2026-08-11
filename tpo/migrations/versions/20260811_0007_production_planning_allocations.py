"""Create typed allocations and canonical replanning snapshot lists.

Revision ID: 20260811_0007
Revises: 20260811_0006
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260811_0007"
down_revision: str | Sequence[str] | None = "20260811_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

unit_of_measure = postgresql.ENUM("SET", "GRAM", "UNIT", name="unit_of_measure", schema=SCHEMA, create_type=False)
semina_state = postgresql.ENUM("AVVIATA", "GERMINAZIONE", "LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA", "CHIUSA", name="semina_state", schema=SCHEMA, create_type=False)
allocation_type = postgresql.ENUM("DOMANDA", "STOCK", "PRODUZIONE_IN_CORSO", "RACCOLTA", name="allocation_type", schema=SCHEMA, create_type=False)
planning_allocation_state = postgresql.ENUM("ATTIVA", "CONSUMATA", "RILASCIATA", "SOSTITUITA", "INVALIDA", name="planning_allocation_state", schema=SCHEMA, create_type=False)


def _fk(local: str, remote: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([local], [f"{SCHEMA}.{remote}"], name=name, onupdate="RESTRICT", ondelete="RESTRICT")


def _create_dense_trigger(table: str) -> None:
    function = f"fn_{table}_dense"
    trigger = f"ct_{table}_dense"
    op.execute(f"""
CREATE FUNCTION tpo.{function}() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_id bigint; target_ids bigint[]; checked_ids bigint[] := ARRAY[]::bigint[]; item_count bigint; maximum_position integer;
BEGIN
  IF TG_OP = 'INSERT' THEN target_ids := ARRAY[NEW.snapshot_id];
  ELSIF TG_OP = 'DELETE' THEN target_ids := ARRAY[OLD.snapshot_id];
  ELSE target_ids := ARRAY[OLD.snapshot_id, NEW.snapshot_id];
  END IF;
  FOREACH target_id IN ARRAY target_ids LOOP
    IF target_id IS NULL OR target_id = ANY(checked_ids) THEN CONTINUE; END IF;
    checked_ids := array_append(checked_ids, target_id);
    SELECT count(*), max(posizione) INTO item_count, maximum_position
      FROM tpo.{table} WHERE snapshot_id = target_id;
    IF item_count > 0 AND (maximum_position <> item_count OR EXISTS (
        SELECT 1 FROM generate_series(1, item_count::integer) AS expected(posizione)
        LEFT JOIN tpo.{table} actual ON actual.snapshot_id=target_id AND actual.posizione=expected.posizione
        WHERE actual.posizione IS NULL)) THEN
      RAISE EXCEPTION '{trigger}: positions must be dense 1..N for snapshot %', target_id;
    END IF;
  END LOOP;
  RETURN NULL;
END;
$$
""")
    op.execute(f"CREATE CONSTRAINT TRIGGER {trigger} AFTER INSERT OR UPDATE OR DELETE ON tpo.{table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tpo.{function}()")


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table("allocazioni",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True), sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("allocation_type", allocation_type, nullable=False), sa.Column("riga_piano_semina_id", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False), sa.Column("unita_misura", unit_of_measure, nullable=False),
        sa.Column("state", planning_allocation_state, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False), sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        _fk("riga_piano_semina_id", "righe_piano_semina.id", "allocazioni_riga_piano_semina_id_fkey"),
        sa.UniqueConstraint("public_id", name="uq_allocazioni_public_id"),
        sa.CheckConstraint("public_id ~ '^ALL-[0-9]{6,}$'", name="ck_allocazioni_public_id").ddl_if(dialect="postgresql"),
        sa.CheckConstraint("quantity>0", name="ck_allocazioni_quantity"), sa.CheckConstraint("version>=0", name="ck_allocazioni_version"),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_allocazioni_created_by"), sa.CheckConstraint("btrim(updated_by)<>''", name="ck_allocazioni_updated_by"), schema=SCHEMA)
    op.create_index("ix_allocazioni_riga_piano_state", "allocazioni", ["riga_piano_semina_id", "state"], schema=SCHEMA)
    op.create_index("ix_allocazioni_type_state", "allocazioni", ["allocation_type", "state"], schema=SCHEMA)

    children = (
        ("allocazioni_domanda", "allocazioni_domanda_pkey", "riga_ordine_id", "righe_ordine.id", "allocazioni_domanda_allocation_id_fkey", "allocazioni_domanda_riga_ordine_id_fkey", "ix_allocazioni_domanda_riga_ordine"),
        ("allocazioni_stock", "pk_allocazioni_stock", "stock_varieta_id", "stock.varieta_id", "fk_allocazioni_stock_allocation", "fk_allocazioni_stock_stock_varieta", "ix_allocazioni_stock_stock_varieta"),
        ("allocazioni_produzione_in_corso", "pk_allocazioni_produzione_in_corso", "semina_id", "semine.id", "fk_allocazioni_produzione_in_corso_allocation", "fk_allocazioni_produzione_in_corso_semina", "ix_allocazioni_produzione_in_corso_semina"),
        ("allocazioni_raccolta", "pk_allocazioni_raccolta", "raccolta_id", "raccolte.id", "fk_allocazioni_raccolta_allocation", "fk_allocazioni_raccolta_raccolta", "ix_allocazioni_raccolta_raccolta"),
    )
    for table, pk, source, remote, parent_fk, source_fk, index in children:
        op.create_table(table, sa.Column("allocation_id", sa.BigInteger(), nullable=False), sa.Column(source, sa.BigInteger(), nullable=False), sa.PrimaryKeyConstraint("allocation_id", name=pk), _fk("allocation_id", "allocazioni.id", parent_fk), _fk(source, remote, source_fk), schema=SCHEMA)
        op.create_index(index, table, [source], schema=SCHEMA)

    op.create_table("replanning_snapshot_stock",
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False), sa.Column("posizione", sa.Integer(), nullable=False),
        sa.Column("stock_resource_public_id", sa.Text(), nullable=False), sa.Column("variety_public_id", sa.Text(), nullable=False),
        sa.Column("eligible_quantity", sa.Numeric(20, 6), nullable=False), sa.Column("allocated_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("allocable_residual", sa.Numeric(20, 6), nullable=False), sa.Column("resource_version", sa.BigInteger(), nullable=False),
        sa.Column("readiness_code", sa.Text(), nullable=False), sa.PrimaryKeyConstraint("snapshot_id", "posizione", name="pk_replanning_snapshot_stock"),
        _fk("snapshot_id", "replanning_snapshots.id", "fk_replanning_snapshot_stock_snapshot"), _fk("stock_resource_public_id", "varieta.public_id", "fk_replanning_snapshot_stock_resource"), _fk("variety_public_id", "varieta.public_id", "fk_replanning_snapshot_stock_variety"),
        sa.UniqueConstraint("snapshot_id", "stock_resource_public_id", name="uq_replanning_snapshot_stock_resource"),
        sa.CheckConstraint("posizione>0", name="ck_replanning_snapshot_stock_posizione"), sa.CheckConstraint("eligible_quantity>=0 AND allocated_quantity>=0 AND allocable_residual>=0 AND allocable_residual=eligible_quantity-allocated_quantity", name="ck_replanning_snapshot_stock_quantities"), sa.CheckConstraint("resource_version>=0", name="ck_replanning_snapshot_stock_version"), sa.CheckConstraint("btrim(readiness_code)<>''", name="ck_replanning_snapshot_stock_readiness"), schema=SCHEMA)
    op.create_index("ix_replanning_snapshot_stock_resource", "replanning_snapshot_stock", ["stock_resource_public_id"], schema=SCHEMA)

    op.create_table("replanning_snapshot_semine",
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False), sa.Column("posizione", sa.Integer(), nullable=False),
        sa.Column("semina_public_id", sa.Text(), nullable=False), sa.Column("variety_public_id", sa.Text(), nullable=False), sa.Column("protocol_version_public_id", sa.Text(), nullable=False),
        sa.Column("expected_useful_quantity", sa.Numeric(20, 6), nullable=False), sa.Column("allocated_quantity", sa.Numeric(20, 6), nullable=False), sa.Column("allocable_residual", sa.Numeric(20, 6), nullable=False),
        sa.Column("harvest_window_start", sa.DateTime(timezone=True), nullable=False), sa.Column("harvest_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("semina_state", semina_state, nullable=False), sa.Column("semina_version", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_id", "posizione", name="pk_replanning_snapshot_semine"), _fk("snapshot_id", "replanning_snapshots.id", "fk_replanning_snapshot_semine_snapshot"), _fk("semina_public_id", "semine.public_id", "fk_replanning_snapshot_semine_semina"), _fk("variety_public_id", "varieta.public_id", "fk_replanning_snapshot_semine_variety"), _fk("protocol_version_public_id", "protocollo_versioni.public_id", "fk_replanning_snapshot_semine_protocol"),
        sa.UniqueConstraint("snapshot_id", "semina_public_id", name="uq_replanning_snapshot_semine_semina"), sa.CheckConstraint("posizione>0", name="ck_replanning_snapshot_semine_posizione"), sa.CheckConstraint("expected_useful_quantity>=0 AND allocated_quantity>=0 AND allocable_residual>=0 AND allocable_residual=expected_useful_quantity-allocated_quantity", name="ck_replanning_snapshot_semine_quantities"), sa.CheckConstraint("harvest_window_end>harvest_window_start", name="ck_replanning_snapshot_semine_window"), sa.CheckConstraint("semina_version>=0", name="ck_replanning_snapshot_semine_version"), schema=SCHEMA)
    op.create_index("ix_replanning_snapshot_semine_semina", "replanning_snapshot_semine", ["semina_public_id"], schema=SCHEMA)

    op.create_table("replanning_snapshot_allocazioni",
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False), sa.Column("posizione", sa.Integer(), nullable=False), sa.Column("allocation_public_id", sa.Text(), nullable=False), sa.Column("allocation_type", allocation_type, nullable=False), sa.Column("source_public_id", sa.Text(), nullable=False), sa.Column("destination_order_line_public_id", sa.Text(), nullable=False), sa.Column("allocated_quantity", sa.Numeric(20, 6), nullable=False), sa.Column("unita_misura", unit_of_measure, nullable=False), sa.Column("allocation_state", planning_allocation_state, nullable=False), sa.Column("allocation_version", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_id", "posizione", name="pk_replanning_snapshot_allocazioni"), _fk("snapshot_id", "replanning_snapshots.id", "fk_replanning_snapshot_allocazioni_snapshot"), _fk("allocation_public_id", "allocazioni.public_id", "fk_replanning_snapshot_allocazioni_allocation"), _fk("destination_order_line_public_id", "righe_ordine.public_id", "fk_replanning_snapshot_allocazioni_destination"),
        sa.UniqueConstraint("snapshot_id", "allocation_public_id", name="uq_replanning_snapshot_allocazioni_allocation"), sa.CheckConstraint("posizione>0", name="ck_replanning_snapshot_allocazioni_posizione"), sa.CheckConstraint("allocated_quantity>0", name="ck_replanning_snapshot_allocazioni_quantity"), sa.CheckConstraint("allocation_version>=0", name="ck_replanning_snapshot_allocazioni_version"), sa.CheckConstraint("btrim(source_public_id)<>''", name="ck_replanning_snapshot_allocazioni_source"), schema=SCHEMA)
    op.create_index("ix_replanning_snapshot_allocazioni_allocation", "replanning_snapshot_allocazioni", ["allocation_public_id"], schema=SCHEMA); op.create_index("ix_replanning_snapshot_allocazioni_destination", "replanning_snapshot_allocazioni", ["destination_order_line_public_id"], schema=SCHEMA)

    if bind.dialect.name == "postgresql":
        op.execute("""
CREATE FUNCTION tpo.fn_allocazioni_exactly_one_child() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_id bigint; target_ids bigint[]; checked_ids bigint[] := ARRAY[]::bigint[]; target_type tpo.allocation_type; total_children integer; matching_children integer;
BEGIN
  IF TG_TABLE_NAME = 'allocazioni' THEN
    IF TG_OP = 'INSERT' THEN target_ids := ARRAY[NEW.id];
    ELSIF TG_OP = 'DELETE' THEN target_ids := ARRAY[OLD.id];
    ELSE target_ids := ARRAY[OLD.id, NEW.id];
    END IF;
  ELSE
    IF TG_OP = 'INSERT' THEN target_ids := ARRAY[NEW.allocation_id];
    ELSIF TG_OP = 'DELETE' THEN target_ids := ARRAY[OLD.allocation_id];
    ELSE target_ids := ARRAY[OLD.allocation_id, NEW.allocation_id];
    END IF;
  END IF;
  FOREACH target_id IN ARRAY target_ids LOOP
    IF target_id IS NULL OR target_id = ANY(checked_ids) THEN CONTINUE; END IF;
    checked_ids := array_append(checked_ids, target_id);
    SELECT allocation_type INTO target_type FROM tpo.allocazioni WHERE id=target_id;
    IF target_type IS NULL THEN CONTINUE; END IF;
    SELECT (SELECT count(*) FROM tpo.allocazioni_domanda WHERE allocation_id=target_id) + (SELECT count(*) FROM tpo.allocazioni_stock WHERE allocation_id=target_id) + (SELECT count(*) FROM tpo.allocazioni_produzione_in_corso WHERE allocation_id=target_id) + (SELECT count(*) FROM tpo.allocazioni_raccolta WHERE allocation_id=target_id) INTO total_children;
    matching_children := CASE target_type WHEN 'DOMANDA' THEN (SELECT count(*) FROM tpo.allocazioni_domanda WHERE allocation_id=target_id) WHEN 'STOCK' THEN (SELECT count(*) FROM tpo.allocazioni_stock WHERE allocation_id=target_id) WHEN 'PRODUZIONE_IN_CORSO' THEN (SELECT count(*) FROM tpo.allocazioni_produzione_in_corso WHERE allocation_id=target_id) WHEN 'RACCOLTA' THEN (SELECT count(*) FROM tpo.allocazioni_raccolta WHERE allocation_id=target_id) END;
    IF total_children<>1 OR matching_children<>1 THEN RAISE EXCEPTION 'ct_allocazioni_exactly_one_child violated for allocation %', target_id; END IF;
  END LOOP;
  RETURN NULL;
END;
$$
""")
        for table in ("allocazioni", "allocazioni_domanda", "allocazioni_stock", "allocazioni_produzione_in_corso", "allocazioni_raccolta"):
            op.execute(f"CREATE CONSTRAINT TRIGGER ct_allocazioni_exactly_one_child AFTER INSERT OR UPDATE OR DELETE ON tpo.{table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tpo.fn_allocazioni_exactly_one_child()")
        for table in ("replanning_snapshot_stock", "replanning_snapshot_semine", "replanning_snapshot_allocazioni"):
            _create_dense_trigger(table)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("replanning_snapshot_stock", "replanning_snapshot_semine", "replanning_snapshot_allocazioni"):
            op.execute(f"DROP TRIGGER ct_{table}_dense ON tpo.{table}"); op.execute(f"DROP FUNCTION tpo.fn_{table}_dense()")
        for table in ("allocazioni", "allocazioni_domanda", "allocazioni_stock", "allocazioni_produzione_in_corso", "allocazioni_raccolta"):
            op.execute(f"DROP TRIGGER ct_allocazioni_exactly_one_child ON tpo.{table}")
        op.execute("DROP FUNCTION tpo.fn_allocazioni_exactly_one_child()")
    for table in ("replanning_snapshot_allocazioni", "replanning_snapshot_semine", "replanning_snapshot_stock", "allocazioni_raccolta", "allocazioni_produzione_in_corso", "allocazioni_stock", "allocazioni_domanda", "allocazioni"):
        op.drop_table(table, schema=SCHEMA)
