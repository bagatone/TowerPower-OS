"""RectifyFattura V1 — rettifica per singola riga di una FATTURA emessa.

Revision ID: 20260905_0029
Revises: 20260904_0028

Autorità: docs/architecture/RECTIFY_FATTURA_AUTHORITY_FREEZE.md, che implementa
la riserva già approvata in FATTURA_AUTHORITY_FREEZE.md §16 (Owner Decision D7):
una rettifica è una nuova FATTURA (propria numero_fattura, stessa serie
annuale, riferimento rettifica_di verso l'originale mai mutato). Le sue righe
correggono righe specifiche della fattura originale (Owner Decision D8), non
sono vincolate a una RIGA_CONSEGNA.

Migrazione additiva e retrocompatibile: ogni riga esistente di tpo.righe_fattura
ha rettifica_riga_fattura_id IS NULL e soddisfa già i vincoli allentati qui
sotto (nessun dato esistente viola i nuovi CHECK).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa

revision: str = "20260905_0029"
down_revision: str | Sequence[str] | None = "20260904_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

TRIGGERS_SQL = r"""
CREATE FUNCTION tpo.fn_righe_fattura_rettifica_coerente() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  original tpo.righe_fattura%ROWTYPE;
  original_fattura_rettifica_di text;
  new_fattura_rettifica_di text;
  original_fattura_numero text;
BEGIN
  IF NEW.rettifica_riga_fattura_id IS NULL THEN RETURN NEW; END IF;
  IF NEW.id = NEW.rettifica_riga_fattura_id THEN
    RAISE EXCEPTION 'ct_righe_fattura_rettifica_coerente self reference';
  END IF;
  SELECT * INTO original FROM tpo.righe_fattura WHERE id = NEW.rettifica_riga_fattura_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'ct_righe_fattura_rettifica_coerente violated: original not found';
  END IF;
  IF original.rettifica_riga_fattura_id IS NOT NULL THEN
    RAISE EXCEPTION 'ct_righe_fattura_rettifica_coerente violated: chained correction';
  END IF;
  IF original.varieta_id <> NEW.varieta_id THEN
    RAISE EXCEPTION 'ct_righe_fattura_rettifica_coerente violated: varieta mismatch';
  END IF;
  SELECT f.rettifica_di, f.numero_fattura INTO original_fattura_rettifica_di, original_fattura_numero
    FROM tpo.fatture f WHERE f.id = original.fattura_id;
  IF original_fattura_rettifica_di IS NOT NULL THEN
    RAISE EXCEPTION 'ct_righe_fattura_rettifica_coerente violated: original fattura is itself a correction';
  END IF;
  SELECT f2.rettifica_di INTO new_fattura_rettifica_di FROM tpo.fatture f2 WHERE f2.id = NEW.fattura_id;
  IF new_fattura_rettifica_di IS NULL OR new_fattura_rettifica_di <> original_fattura_numero THEN
    RAISE EXCEPTION 'ct_righe_fattura_rettifica_coerente violated: fattura rettifica_di mismatch';
  END IF;
  RETURN NEW;
END;
$$;
CREATE CONSTRAINT TRIGGER ct_righe_fattura_rettifica_coerente
AFTER INSERT ON tpo.righe_fattura
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tpo.fn_righe_fattura_rettifica_coerente();

CREATE FUNCTION tpo.fn_fatture_rettifica_cliente_coerente() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original_cliente_id bigint;
BEGIN
  IF NEW.rettifica_di IS NULL THEN RETURN NEW; END IF;
  SELECT cliente_id INTO original_cliente_id FROM tpo.fatture WHERE numero_fattura = NEW.rettifica_di;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'ct_fatture_rettifica_cliente_coerente violated: original not found';
  END IF;
  IF original_cliente_id <> NEW.cliente_id THEN
    RAISE EXCEPTION 'ct_fatture_rettifica_cliente_coerente violated: cliente mismatch';
  END IF;
  RETURN NEW;
END;
$$;
CREATE CONSTRAINT TRIGGER ct_fatture_rettifica_cliente_coerente
AFTER INSERT ON tpo.fatture
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tpo.fn_fatture_rettifica_cliente_coerente();

CREATE FUNCTION tpo.fn_fattura_rettifica_request_protect() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
     AND NEW.operation_scope=OLD.operation_scope
     AND NEW.idempotency_key=OLD.idempotency_key
     AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
     AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
     AND OLD.fattura_id IS NULL AND NEW.fattura_id IS NOT NULL THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'tr_fattura_rettifica_request_protect violated';
END;
$$;
CREATE TRIGGER tr_fattura_rettifica_request_protect
BEFORE UPDATE OR DELETE ON tpo.fattura_rettifica_requests
FOR EACH ROW EXECUTE FUNCTION tpo.fn_fattura_rettifica_request_protect();
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.alter_column("righe_fattura", "riga_consegna_id", nullable=True, schema=SCHEMA)
    op.add_column(
        "righe_fattura", sa.Column("rettifica_riga_fattura_id", sa.BigInteger()), schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_righe_fattura_rettifica", "righe_fattura", "righe_fattura",
        ["rettifica_riga_fattura_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA,
        onupdate="RESTRICT", ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_righe_fattura_rettifica_riga_fattura", "righe_fattura",
        ["rettifica_riga_fattura_id"], schema=SCHEMA,
    )
    op.drop_constraint("ck_righe_fattura_quantita_positive", "righe_fattura", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_righe_fattura_ordinaria_o_rettifica", "righe_fattura",
        "(rettifica_riga_fattura_id IS NULL AND riga_consegna_id IS NOT NULL AND quantita > 0) OR "
        "(rettifica_riga_fattura_id IS NOT NULL AND riga_consegna_id IS NULL AND quantita <> 0)",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_righe_fattura_rettifica_riga_fattura_id", "righe_fattura",
        ["rettifica_riga_fattura_id"], schema=SCHEMA,
    )

    hash_check = "canonical_payload_hash ~ '^[0-9a-f]{64}$'"
    op.create_table(
        "fattura_rettifica_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("fattura_id", sa.BigInteger()),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fattura_id"], [f"{SCHEMA}.fatture.id"],
            name="fk_fattura_rettifica_requests_fattura",
            onupdate="RESTRICT", ondelete="RESTRICT",
            deferrable=True, initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "operation_scope", "idempotency_key", name="uq_fattura_rettifica_request_key",
        ),
        sa.UniqueConstraint("fattura_id", name="uq_fattura_rettifica_request_fattura"),
        sa.CheckConstraint(
            "operation_scope='FATTURA_RETTIFICA_V1'", name="ck_fattura_rettifica_request_scope",
        ),
        sa.CheckConstraint("btrim(idempotency_key)<>''", name="ck_fattura_rettifica_request_key"),
        sa.CheckConstraint(hash_check, name="ck_fattura_rettifica_request_hash"),
        sa.CheckConstraint(
            "(outcome='RESERVED' AND fattura_id IS NULL) OR "
            "(outcome='COMMITTED' AND fattura_id IS NOT NULL)",
            name="ck_fattura_rettifica_request_outcome",
        ),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_fattura_rettifica_request_actor"),
        schema=SCHEMA,
    )

    op.execute(TRIGGERS_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not context.is_offline_mode():
        counts = bind.execute(sa.text(
            "SELECT (SELECT count(*) FROM tpo.fattura_rettifica_requests) + "
            "(SELECT count(*) FROM tpo.righe_fattura WHERE rettifica_riga_fattura_id IS NOT NULL)"
        )).scalar_one()
        if counts:
            raise RuntimeError("cannot downgrade: governed RECTIFY FATTURA authority history exists")

    op.execute("""
DROP TRIGGER tr_fattura_rettifica_request_protect ON tpo.fattura_rettifica_requests;
DROP FUNCTION tpo.fn_fattura_rettifica_request_protect();
DROP TRIGGER ct_fatture_rettifica_cliente_coerente ON tpo.fatture;
DROP FUNCTION tpo.fn_fatture_rettifica_cliente_coerente();
DROP TRIGGER ct_righe_fattura_rettifica_coerente ON tpo.righe_fattura;
DROP FUNCTION tpo.fn_righe_fattura_rettifica_coerente();
""")

    op.drop_table("fattura_rettifica_requests", schema=SCHEMA)
    op.drop_index("ix_righe_fattura_rettifica_riga_fattura_id", table_name="righe_fattura", schema=SCHEMA)
    op.drop_constraint("ck_righe_fattura_ordinaria_o_rettifica", "righe_fattura", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_righe_fattura_quantita_positive", "righe_fattura", "quantita > 0", schema=SCHEMA,
    )
    op.drop_constraint("uq_righe_fattura_rettifica_riga_fattura", "righe_fattura", schema=SCHEMA, type_="unique")
    op.drop_constraint("fk_righe_fattura_rettifica", "righe_fattura", schema=SCHEMA, type_="foreignkey")
    op.drop_column("righe_fattura", "rettifica_riga_fattura_id", schema=SCHEMA)
    op.alter_column("righe_fattura", "riga_consegna_id", nullable=False, schema=SCHEMA)
