"""Raccolta Correzione Authority V1 (RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md).

Revision ID: 20260903_0027
Revises: 20260903_0026
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa

revision: str = "20260903_0027"
down_revision: str | Sequence[str] | None = "20260903_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

# Precedente strutturale diretto: fn_righe_consegna_rettifica_coerente() e
# ck_righe_consegna_ordinary_or_correction in
# migrations/versions/20260812_0009_delivery_fulfilment_schema.py. A differenza di
# righe_consegna (che vive dentro una CONSEGNA contenitore), RACCOLTA è essa stessa
# l'unità pubblica: la rettifica riceve un proprio RAC-* dalla stessa sequenza
# RACCOLTA_ID (RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md §4).
TRIGGERS_SQL = r"""
CREATE FUNCTION tpo.fn_raccolte_rettifica_coerente() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original tpo.raccolte%ROWTYPE;
BEGIN
  IF NEW.rettifica_raccolta_id IS NULL THEN RETURN NEW; END IF;
  IF NEW.id = NEW.rettifica_raccolta_id THEN
    RAISE EXCEPTION 'ct_raccolte_rettifica_coerente self reference';
  END IF;
  SELECT * INTO original FROM tpo.raccolte WHERE id = NEW.rettifica_raccolta_id;
  IF NOT FOUND OR original.rettifica_raccolta_id IS NOT NULL
     OR original.semina_id <> NEW.semina_id
     OR original.unita_misura <> NEW.unita_misura THEN
    RAISE EXCEPTION 'ct_raccolte_rettifica_coerente violated';
  END IF;
  RETURN NEW;
END;
$$;
CREATE CONSTRAINT TRIGGER ct_raccolte_rettifica_coerente
AFTER INSERT ON tpo.raccolte
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tpo.fn_raccolte_rettifica_coerente();

CREATE FUNCTION tpo.fn_check_raccolta_net_quantity(target_raccolta bigint) RETURNS void LANGUAGE plpgsql AS $$
DECLARE net numeric(20,6);
BEGIN
  SELECT quantita INTO net FROM tpo.raccolte WHERE id = target_raccolta;
  IF NOT FOUND THEN RETURN; END IF;
  SELECT net + COALESCE(sum(quantita),0) INTO net
    FROM tpo.raccolte WHERE rettifica_raccolta_id = target_raccolta;
  IF net < 0 THEN
    RAISE EXCEPTION 'ct_raccolte_net_quantity_nonnegative violated for raccolta %', target_raccolta;
  END IF;
END;
$$;
CREATE FUNCTION tpo.fn_raccolte_net_quantity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.rettifica_raccolta_id IS NOT NULL THEN
    PERFORM tpo.fn_check_raccolta_net_quantity(NEW.rettifica_raccolta_id);
  END IF;
  RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER ct_raccolte_z_net_quantity_nonnegative
AFTER INSERT ON tpo.raccolte
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION tpo.fn_raccolte_net_quantity();

CREATE FUNCTION tpo.protect_raccolta_correzione_request()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
     AND NEW.operation_scope=OLD.operation_scope
     AND NEW.idempotency_key=OLD.idempotency_key
     AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
     AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
     AND OLD.raccolta_id IS NULL AND OLD.result_public_id IS NULL
     AND NEW.raccolta_id IS NOT NULL AND NEW.result_public_id IS NOT NULL THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Raccolta correzione request authority is immutable';
END $$;
CREATE TRIGGER protect_raccolta_correzione_request
BEFORE UPDATE OR DELETE ON tpo.raccolta_correzione_requests
FOR EACH ROW EXECUTE FUNCTION tpo.protect_raccolta_correzione_request();
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Additiva e retro-compatibile: le RACCOLTE esistenti hanno già
    # rettifica_raccolta_id NULL (colonna appena aggiunta) e quantita > 0, quindi
    # soddisfano banalmente il nuovo vincolo composito senza backfill.
    op.add_column(
        "raccolte", sa.Column("rettifica_raccolta_id", sa.BigInteger()), schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_raccolte_rettifica", "raccolte", "raccolte",
        ["rettifica_raccolta_id"], ["id"],
        source_schema=SCHEMA, referent_schema=SCHEMA,
        onupdate="RESTRICT", ondelete="RESTRICT",
    )
    op.create_index(
        "ix_raccolte_rettifica_raccolta_id", "raccolte", ["rettifica_raccolta_id"],
        schema=SCHEMA,
    )
    op.drop_constraint(
        "ck_raccolte_quantita_positive", "raccolte", schema=SCHEMA, type_="check",
    )
    op.create_check_constraint(
        "ck_raccolte_ordinary_or_correction", "raccolte",
        "(rettifica_raccolta_id IS NULL AND quantita > 0) OR "
        "(rettifica_raccolta_id IS NOT NULL AND quantita <> 0)",
        schema=SCHEMA,
    )

    op.create_table(
        "raccolta_correzione_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("raccolta_id", sa.BigInteger()),
        sa.Column("result_public_id", sa.Text()),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["raccolta_id", "result_public_id"],
            ["tpo.raccolte.id", "tpo.raccolte.public_id"],
            onupdate="RESTRICT", ondelete="RESTRICT",
            name="fk_raccolta_correzione_authoritative_result",
            deferrable=True, initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "operation_scope", "idempotency_key",
            name="uq_raccolta_correzione_request_key",
        ),
        sa.UniqueConstraint("raccolta_id", name="uq_raccolta_correzione_raccolta"),
        sa.UniqueConstraint("result_public_id", name="uq_raccolta_correzione_result"),
        sa.CheckConstraint(
            "operation_scope='RACCOLTA_CORREZIONE_V1'",
            name="ck_raccolta_correzione_scope",
        ),
        sa.CheckConstraint("btrim(idempotency_key)<>''", name="ck_raccolta_correzione_key"),
        sa.CheckConstraint(
            "canonical_payload_hash ~ '^[0-9a-f]{64}$'", name="ck_raccolta_correzione_hash",
        ),
        sa.CheckConstraint(
            "(outcome='RESERVED' AND raccolta_id IS NULL AND result_public_id IS NULL) OR "
            "(outcome='COMMITTED' AND raccolta_id IS NOT NULL AND result_public_id IS NOT NULL)",
            name="ck_raccolta_correzione_outcome",
        ),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_raccolta_correzione_actor"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_raccolta_correzione_result", "raccolta_correzione_requests",
        ["result_public_id"], schema=SCHEMA,
    )

    op.execute(TRIGGERS_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not context.is_offline_mode():
        corrections = bind.execute(
            sa.text("SELECT count(*) FROM tpo.raccolte WHERE rettifica_raccolta_id IS NOT NULL")
        ).scalar_one()
        requests = bind.execute(
            sa.text("SELECT count(*) FROM tpo.raccolta_correzione_requests")
        ).scalar_one()
        if corrections or requests:
            raise RuntimeError(
                "cannot downgrade: governed RACCOLTA CORREZIONE authority history exists"
            )

    op.execute("""
DROP TRIGGER protect_raccolta_correzione_request ON tpo.raccolta_correzione_requests;
DROP FUNCTION tpo.protect_raccolta_correzione_request();
DROP TRIGGER ct_raccolte_z_net_quantity_nonnegative ON tpo.raccolte;
DROP FUNCTION tpo.fn_raccolte_net_quantity();
DROP FUNCTION tpo.fn_check_raccolta_net_quantity(bigint);
DROP TRIGGER ct_raccolte_rettifica_coerente ON tpo.raccolte;
DROP FUNCTION tpo.fn_raccolte_rettifica_coerente();
""")

    op.drop_index(
        "ix_raccolta_correzione_result", table_name="raccolta_correzione_requests",
        schema=SCHEMA,
    )
    op.drop_table("raccolta_correzione_requests", schema=SCHEMA)

    op.drop_constraint(
        "ck_raccolte_ordinary_or_correction", "raccolte", schema=SCHEMA, type_="check",
    )
    op.create_check_constraint(
        "ck_raccolte_quantita_positive", "raccolte", "quantita > 0", schema=SCHEMA,
    )
    op.drop_index(
        "ix_raccolte_rettifica_raccolta_id", table_name="raccolte", schema=SCHEMA,
    )
    op.drop_constraint(
        "fk_raccolte_rettifica", "raccolte", schema=SCHEMA, type_="foreignkey",
    )
    op.drop_column("raccolte", "rettifica_raccolta_id", schema=SCHEMA)
