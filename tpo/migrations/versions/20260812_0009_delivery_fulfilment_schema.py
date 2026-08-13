"""Materialize the Delivery Fulfilment physical contract.

Revision ID: 20260812_0009
Revises: 20260811_0008
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260812_0009"
down_revision: str | Sequence[str] | None = "20260811_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

unit_of_measure = postgresql.ENUM(
    "SET", "GRAM", "UNIT", name="unit_of_measure", schema=SCHEMA, create_type=False
)


FUNCTIONS_SQL = r"""
CREATE FUNCTION tpo.fn_consegne_ordini_cliente_coerente() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM tpo.consegne c JOIN tpo.ordini o ON o.id = NEW.ordine_id
    WHERE c.id = NEW.consegna_id AND c.cliente_id = o.cliente_id
  ) THEN RAISE EXCEPTION 'ct_consegne_ordini_cliente_coerente violated'; END IF;
  RETURN NEW;
END;
$$;

CREATE FUNCTION tpo.fn_consegne_cliente_coerente_ordini() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM tpo.consegne_ordini co JOIN tpo.ordini o ON o.id = co.ordine_id
    WHERE co.consegna_id = NEW.id AND o.cliente_id <> NEW.cliente_id
  ) THEN RAISE EXCEPTION 'ct_consegne_cliente_coerente_ordini violated'; END IF;
  RETURN NEW;
END;
$$;

CREATE FUNCTION tpo.fn_ordini_cliente_coerente_consegne() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM tpo.consegne_ordini co JOIN tpo.consegne c ON c.id = co.consegna_id
    WHERE co.ordine_id = NEW.id AND c.cliente_id <> NEW.cliente_id
  ) THEN RAISE EXCEPTION 'ct_ordini_cliente_coerente_consegne violated'; END IF;
  RETURN NEW;
END;
$$;

CREATE FUNCTION tpo.fn_righe_consegna_rettifica_coerente() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original tpo.righe_consegna%ROWTYPE;
BEGIN
  IF NEW.rettifica_riga_consegna_id IS NULL THEN RETURN NEW; END IF;
  IF NEW.id = NEW.rettifica_riga_consegna_id THEN
    RAISE EXCEPTION 'ct_righe_consegna_rettifica_coerente self reference';
  END IF;
  SELECT * INTO original FROM tpo.righe_consegna WHERE id = NEW.rettifica_riga_consegna_id;
  IF NOT FOUND OR original.rettifica_riga_consegna_id IS NOT NULL
     OR original.consegna_id = NEW.consegna_id
     OR NOT EXISTS (SELECT 1 FROM tpo.consegne WHERE id=original.consegna_id AND stato='CONSEGNATA')
     OR original.riga_ordine_id <> NEW.riga_ordine_id
     OR original.varieta_id <> NEW.varieta_id
     OR original.unita_misura <> NEW.unita_misura THEN
    RAISE EXCEPTION 'ct_righe_consegna_rettifica_coerente violated';
  END IF;
  RETURN NEW;
END;
$$;

CREATE FUNCTION tpo.fn_check_fulfilment_bounds(target_line bigint) RETURNS void LANGUAGE plpgsql AS $$
DECLARE ordered numeric(20,6); delivered numeric;
BEGIN
  SELECT quantita INTO ordered FROM tpo.righe_ordine WHERE id = target_line;
  IF NOT FOUND THEN RETURN; END IF;
  SELECT COALESCE(sum(rc.quantita) FILTER (WHERE c.stato = 'CONSEGNATA'), 0)
    INTO delivered FROM tpo.righe_consegna rc JOIN tpo.consegne c ON c.id=rc.consegna_id
    WHERE rc.riga_ordine_id=target_line;
  IF delivered < 0 OR delivered > ordered THEN
    RAISE EXCEPTION 'ct_righe_consegna_fulfilment_bounds violated for order line %', target_line;
  END IF;
END;
$$;

CREATE FUNCTION tpo.fn_righe_consegna_fulfilment_bounds() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP <> 'INSERT' THEN PERFORM tpo.fn_check_fulfilment_bounds(OLD.riga_ordine_id); END IF;
  IF TG_OP <> 'DELETE' AND (TG_OP = 'INSERT' OR NEW.riga_ordine_id IS DISTINCT FROM OLD.riga_ordine_id) THEN
    PERFORM tpo.fn_check_fulfilment_bounds(NEW.riga_ordine_id);
  END IF;
  RETURN NULL;
END;
$$;

CREATE FUNCTION tpo.fn_consegne_fulfilment_bounds() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_line bigint;
BEGIN
  FOR target_line IN SELECT DISTINCT riga_ordine_id FROM tpo.righe_consegna WHERE consegna_id=NEW.id
  LOOP PERFORM tpo.fn_check_fulfilment_bounds(target_line); END LOOP;
  RETURN NULL;
END;
$$;

CREATE FUNCTION tpo.fn_check_ordine_fulfilment_state(target_order bigint) RETURNS void LANGUAGE plpgsql AS $$
DECLARE actual tpo.ordine_state; line_count bigint; zero_count bigint; full_count bigint;
BEGIN
  SELECT stato INTO actual FROM tpo.ordini WHERE id=target_order;
  IF NOT FOUND THEN RETURN; END IF;
  SELECT count(*), count(*) FILTER (WHERE delivered=0), count(*) FILTER (WHERE delivered=ordered)
    INTO line_count, zero_count, full_count
  FROM (
    SELECT ro.quantita ordered, COALESCE(sum(rc.quantita) FILTER (WHERE c.stato='CONSEGNATA'),0) delivered
    FROM tpo.righe_ordine ro LEFT JOIN tpo.righe_consegna rc ON rc.riga_ordine_id=ro.id
    LEFT JOIN tpo.consegne c ON c.id=rc.consegna_id WHERE ro.ordine_id=target_order
    GROUP BY ro.id, ro.quantita
  ) totals;
  IF actual='ANNULLATO' THEN
    IF zero_count<>line_count THEN RAISE EXCEPTION 'ct_ordini_fulfilment_state: cancelled order has fulfilment'; END IF;
  ELSIF zero_count=line_count THEN
    IF actual<>'APERTO' THEN RAISE EXCEPTION 'ct_ordini_fulfilment_state: expected APERTO'; END IF;
  ELSIF full_count=line_count THEN
    IF actual<>'EVASO' THEN RAISE EXCEPTION 'ct_ordini_fulfilment_state: expected EVASO'; END IF;
  ELSIF actual<>'PARZIALMENTE_EVASO' THEN
    RAISE EXCEPTION 'ct_ordini_fulfilment_state: expected PARZIALMENTE_EVASO';
  END IF;
END;
$$;

CREATE FUNCTION tpo.fn_righe_consegna_order_state() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP <> 'INSERT' THEN PERFORM tpo.fn_check_ordine_fulfilment_state(OLD.ordine_id); END IF;
  IF TG_OP <> 'DELETE' AND (TG_OP='INSERT' OR NEW.ordine_id IS DISTINCT FROM OLD.ordine_id) THEN
    PERFORM tpo.fn_check_ordine_fulfilment_state(NEW.ordine_id);
  END IF;
  RETURN NULL;
END;
$$;

CREATE FUNCTION tpo.fn_consegne_order_state() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_order bigint;
BEGIN
  FOR target_order IN SELECT ordine_id FROM tpo.consegne_ordini WHERE consegna_id=NEW.id
  LOOP PERFORM tpo.fn_check_ordine_fulfilment_state(target_order); END LOOP;
  RETURN NULL;
END;
$$;

CREATE FUNCTION tpo.fn_ordini_fulfilment_state() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN PERFORM tpo.fn_check_ordine_fulfilment_state(NEW.id); RETURN NULL; END;
$$;

CREATE FUNCTION tpo.fn_consegne_effective_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.stato='CONSEGNATA' THEN RAISE EXCEPTION 'tr_consegne_effective_immutable violated'; END IF;
  RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE FUNCTION tpo.fn_consegne_ordini_effective_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM tpo.consegne WHERE id=OLD.consegna_id AND stato='CONSEGNATA') THEN
    RAISE EXCEPTION 'tr_consegne_ordini_effective_immutable violated';
  END IF;
  RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE FUNCTION tpo.fn_righe_consegna_effective_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM tpo.consegne WHERE id=OLD.consegna_id AND stato='CONSEGNATA') THEN
    RAISE EXCEPTION 'tr_righe_consegna_effective_immutable violated';
  END IF;
  RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END;
$$;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if context.is_offline_mode():
        op.execute("""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM tpo.consegne WHERE stato = 'CONSEGNATA') THEN
    RAISE EXCEPTION 'historical delivery fulfilment commissioning required';
  END IF;
END;
$$
""")
    elif bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM tpo.consegne WHERE stato = 'CONSEGNATA')")
    ).scalar_one():
        raise RuntimeError("historical delivery fulfilment commissioning required")
    op.create_unique_constraint(
        "uq_righe_ordine_fulfilment_key", "righe_ordine",
        ["id", "ordine_id", "varieta_id", "unita_misura"], schema=SCHEMA,
    )
    op.create_table(
        "consegne_ordini",
        sa.Column("consegna_id", sa.BigInteger(), nullable=False),
        sa.Column("ordine_id", sa.BigInteger(), nullable=False),
        sa.Column("posizione", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("consegna_id", "ordine_id", name="pk_consegne_ordini"),
        sa.UniqueConstraint("consegna_id", "posizione", name="uq_consegne_ordini_consegna_posizione"),
        sa.CheckConstraint("posizione > 0", name="ck_consegne_ordini_posizione_positive"),
        sa.ForeignKeyConstraint(["consegna_id"], ["tpo.consegne.id"], name="fk_consegne_ordini_consegna", onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ordine_id"], ["tpo.ordini.id"], name="fk_consegne_ordini_ordine", onupdate="RESTRICT", ondelete="RESTRICT"),
        schema=SCHEMA,
    )
    op.create_index("ix_consegne_ordini_ordine_id", "consegne_ordini", ["ordine_id"], schema=SCHEMA)
    op.create_table(
        "righe_consegna",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("consegna_id", sa.BigInteger(), nullable=False),
        sa.Column("ordine_id", sa.BigInteger(), nullable=False),
        sa.Column("riga_ordine_id", sa.BigInteger(), nullable=False),
        sa.Column("posizione", sa.Integer(), nullable=False),
        sa.Column("varieta_id", sa.BigInteger(), nullable=False),
        sa.Column("quantita", sa.Numeric(20, 6), nullable=False),
        sa.Column("unita_misura", unit_of_measure, nullable=False),
        sa.Column("rettifica_riga_consegna_id", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_righe_consegna"),
        sa.UniqueConstraint("consegna_id", "posizione", name="uq_righe_consegna_consegna_posizione"),
        sa.UniqueConstraint("id", "consegna_id", name="uq_righe_consegna_id_consegna"),
        sa.CheckConstraint("posizione > 0", name="ck_righe_consegna_posizione_positive"),
        sa.CheckConstraint("quantita <> 0", name="ck_righe_consegna_quantita_nonzero"),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_righe_consegna_created_by_not_blank"),
        sa.CheckConstraint("(rettifica_riga_consegna_id IS NULL AND quantita > 0) OR rettifica_riga_consegna_id IS NOT NULL", name="ck_righe_consegna_ordinary_or_correction"),
        sa.ForeignKeyConstraint(["consegna_id", "ordine_id"], ["tpo.consegne_ordini.consegna_id", "tpo.consegne_ordini.ordine_id"], name="fk_righe_consegna_consegna_ordine", onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["riga_ordine_id", "ordine_id", "varieta_id", "unita_misura"], ["tpo.righe_ordine.id", "tpo.righe_ordine.ordine_id", "tpo.righe_ordine.varieta_id", "tpo.righe_ordine.unita_misura"], name="fk_righe_consegna_riga_ordine", onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["varieta_id"], ["tpo.varieta.id"], name="fk_righe_consegna_varieta", onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rettifica_riga_consegna_id"], ["tpo.righe_consegna.id"], name="fk_righe_consegna_rettifica", onupdate="RESTRICT", ondelete="RESTRICT"),
        schema=SCHEMA,
    )
    for name, columns in (
        ("ix_righe_consegna_consegna_id", ["consegna_id"]),
        ("ix_righe_consegna_ordine_id", ["ordine_id"]),
        ("ix_righe_consegna_riga_ordine_id", ["riga_ordine_id"]),
        ("ix_righe_consegna_rettifica_id", ["rettifica_riga_consegna_id"]),
        ("ix_righe_consegna_riga_ordine_consegna", ["riga_ordine_id", "consegna_id"]),
    ):
        op.create_index(name, "righe_consegna", columns, schema=SCHEMA)
    op.add_column("movimenti_magazzino", sa.Column("riga_consegna_id", sa.BigInteger()), schema=SCHEMA)
    op.create_foreign_key("fk_movimenti_magazzino_riga_consegna_consegna", "movimenti_magazzino", "righe_consegna", ["riga_consegna_id", "consegna_id"], ["id", "consegna_id"], source_schema=SCHEMA, referent_schema=SCHEMA, onupdate="RESTRICT", ondelete="RESTRICT")
    op.create_index("ix_movimenti_magazzino_riga_consegna_id", "movimenti_magazzino", ["riga_consegna_id"], schema=SCHEMA)
    op.drop_constraint("ck_movimenti_magazzino_origine_references", "movimenti_magazzino", schema=SCHEMA, type_="check")
    op.create_check_constraint("ck_movimenti_magazzino_origine_references", "movimenti_magazzino", "(origine_tipo = 'RACCOLTA' AND raccolta_id IS NOT NULL AND consegna_id IS NULL AND riga_consegna_id IS NULL) OR (origine_tipo = 'CONSEGNA' AND consegna_id IS NOT NULL AND riga_consegna_id IS NOT NULL AND raccolta_id IS NULL) OR (origine_tipo NOT IN ('RACCOLTA', 'CONSEGNA') AND raccolta_id IS NULL AND consegna_id IS NULL AND riga_consegna_id IS NULL)", schema=SCHEMA)
    op.execute(FUNCTIONS_SQL)
    triggers = (
            "CREATE CONSTRAINT TRIGGER ct_consegne_ordini_cliente_coerente AFTER INSERT OR UPDATE ON tpo.consegne_ordini DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tpo.fn_consegne_ordini_cliente_coerente()",
            "CREATE CONSTRAINT TRIGGER ct_consegne_cliente_coerente_ordini AFTER UPDATE OF cliente_id ON tpo.consegne DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tpo.fn_consegne_cliente_coerente_ordini()",
            "CREATE CONSTRAINT TRIGGER ct_ordini_cliente_coerente_consegne AFTER UPDATE OF cliente_id ON tpo.ordini DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tpo.fn_ordini_cliente_coerente_consegne()",
            "CREATE CONSTRAINT TRIGGER ct_righe_consegna_rettifica_coerente AFTER INSERT OR UPDATE ON tpo.righe_consegna DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tpo.fn_righe_consegna_rettifica_coerente()",
            "CREATE CONSTRAINT TRIGGER ct_righe_consegna_fulfilment_bounds AFTER INSERT OR UPDATE OR DELETE ON tpo.righe_consegna DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tpo.fn_righe_consegna_fulfilment_bounds()",
            "CREATE CONSTRAINT TRIGGER ct_consegne_fulfilment_bounds AFTER UPDATE OF stato ON tpo.consegne DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tpo.fn_consegne_fulfilment_bounds()",
            "CREATE CONSTRAINT TRIGGER ct_righe_consegna_order_state AFTER INSERT OR UPDATE OR DELETE ON tpo.righe_consegna DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tpo.fn_righe_consegna_order_state()",
            "CREATE CONSTRAINT TRIGGER ct_consegne_order_state AFTER UPDATE OF stato ON tpo.consegne DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tpo.fn_consegne_order_state()",
            "CREATE CONSTRAINT TRIGGER ct_ordini_fulfilment_state AFTER UPDATE OF stato ON tpo.ordini DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tpo.fn_ordini_fulfilment_state()",
    )
    for statement in triggers:
        op.execute(statement)
    op.execute("CREATE TRIGGER tr_consegne_effective_immutable BEFORE UPDATE OR DELETE ON tpo.consegne FOR EACH ROW EXECUTE FUNCTION tpo.fn_consegne_effective_immutable()")
    op.execute("CREATE TRIGGER tr_consegne_ordini_effective_immutable BEFORE UPDATE OR DELETE ON tpo.consegne_ordini FOR EACH ROW EXECUTE FUNCTION tpo.fn_consegne_ordini_effective_immutable()")
    op.execute("CREATE TRIGGER tr_righe_consegna_effective_immutable BEFORE UPDATE OR DELETE ON tpo.righe_consegna FOR EACH ROW EXECUTE FUNCTION tpo.fn_righe_consegna_effective_immutable()")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if bind.dialect.name == "postgresql":
        for table, trigger in (
            ("righe_consegna", "tr_righe_consegna_effective_immutable"),
            ("consegne_ordini", "tr_consegne_ordini_effective_immutable"),
            ("consegne", "tr_consegne_effective_immutable"),
            ("ordini", "ct_ordini_fulfilment_state"),
            ("consegne", "ct_consegne_order_state"),
            ("righe_consegna", "ct_righe_consegna_order_state"),
            ("consegne", "ct_consegne_fulfilment_bounds"),
            ("righe_consegna", "ct_righe_consegna_fulfilment_bounds"),
            ("righe_consegna", "ct_righe_consegna_rettifica_coerente"),
            ("ordini", "ct_ordini_cliente_coerente_consegne"),
            ("consegne", "ct_consegne_cliente_coerente_ordini"),
            ("consegne_ordini", "ct_consegne_ordini_cliente_coerente"),
        ):
            op.execute(f"DROP TRIGGER {trigger} ON tpo.{table}")
        for function in (
            "fn_righe_consegna_effective_immutable", "fn_consegne_ordini_effective_immutable",
            "fn_consegne_effective_immutable", "fn_ordini_fulfilment_state",
            "fn_consegne_order_state", "fn_righe_consegna_order_state",
            "fn_check_ordine_fulfilment_state", "fn_consegne_fulfilment_bounds",
            "fn_righe_consegna_fulfilment_bounds", "fn_check_fulfilment_bounds",
            "fn_righe_consegna_rettifica_coerente", "fn_ordini_cliente_coerente_consegne",
            "fn_consegne_cliente_coerente_ordini", "fn_consegne_ordini_cliente_coerente",
        ):
            signature = "bigint" if function in {"fn_check_ordine_fulfilment_state", "fn_check_fulfilment_bounds"} else ""
            op.execute(f"DROP FUNCTION tpo.{function}({signature})")
    op.drop_constraint("ck_movimenti_magazzino_origine_references", "movimenti_magazzino", schema=SCHEMA, type_="check")
    op.create_check_constraint("ck_movimenti_magazzino_origine_references", "movimenti_magazzino", "(origine_tipo = 'RACCOLTA' AND raccolta_id IS NOT NULL AND consegna_id IS NULL) OR (origine_tipo = 'CONSEGNA' AND consegna_id IS NOT NULL AND raccolta_id IS NULL) OR (origine_tipo NOT IN ('RACCOLTA', 'CONSEGNA') AND raccolta_id IS NULL AND consegna_id IS NULL)", schema=SCHEMA)
    op.drop_index("ix_movimenti_magazzino_riga_consegna_id", table_name="movimenti_magazzino", schema=SCHEMA)
    op.drop_constraint("fk_movimenti_magazzino_riga_consegna_consegna", "movimenti_magazzino", schema=SCHEMA, type_="foreignkey")
    op.drop_column("movimenti_magazzino", "riga_consegna_id", schema=SCHEMA)
    op.drop_table("righe_consegna", schema=SCHEMA)
    op.drop_table("consegne_ordini", schema=SCHEMA)
    op.drop_constraint("uq_righe_ordine_fulfilment_key", "righe_ordine", schema=SCHEMA, type_="unique")
