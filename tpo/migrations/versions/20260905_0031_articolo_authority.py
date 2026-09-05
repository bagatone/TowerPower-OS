"""Articolo Authority V1 (ARTICOLO_AUTHORITY_FREEZE.md).

Revision ID: 20260905_0031
Revises: 20260905_0030

Congela ARTICOLO come Configuration distinta da VARIETA (materiali della
catena: substrati, fertilizzante, packaging, ecc. -- non i semi) ed estende
MOVIMENTO_MAGAZZINO/STOCK a operare anche su un ARTICOLO. Design additivo che
non tocca la forma di tpo.stock/tpo.raccolte/tpo.consegne: STOCK_ARTICOLI vive
in una tabella parallela con la stessa forma di STOCK. tpo.movimenti_magazzino
riceve varieta_id nullable (rilassamento: tutte le righe esistenti hanno gia'
un valore), una nuova colonna articolo_id nullable + FK, un nuovo CHECK XOR
risorsa e una nuova FK composita verso stock_articoli -- stesso precedente
strutturale della FK composita di 20260905_0030
(uq_movimenti_magazzino_id_public_id): una FK composita richiede un vincolo
UNIQUE che copra esattamente le colonne referenziate, qui gia' fornito da
UNIQUE(articolo_id, unita_misura) su stock_articoli. La FK composita esistente
(varieta_id, unita_misura) -> stock(varieta_id, unita_misura) non richiede
modifiche: con varieta_id NULL su una riga ARTICOLO, Postgres non la verifica
su quella riga (semantica MATCH SIMPLE per FK composite con colonne NULL).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0031"
down_revision: str | Sequence[str] | None = "20260905_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

UOM = postgresql.ENUM("SET", "GRAM", "UNIT", name="unit_of_measure", schema=SCHEMA, create_type=False)

MOVIMENTI_MAGAZZINO_RISORSA_XOR = (
    "(varieta_id IS NOT NULL AND articolo_id IS NULL) OR "
    "(varieta_id IS NULL AND articolo_id IS NOT NULL)"
)

# Precedenti strutturali diretti: tpo.raccolte/tpo.raccolta_recording_requests
# (20260830_0022_raccolta_authority.py) per la forma Register+reservation con
# public_id/PermanentId; tpo.stock (20260810_0004) per la forma di
# STOCK_ARTICOLI; tpo.movimento_carico_requests (20260905_0030) per la forma
# della reservation di un MOVIMENTO (1:1 risultato-richiesta, a differenza del
# commissioning di ARTICOLO dove la richiesta referenzia l'entita' stessa).
TRIGGERS_SQL = r"""
CREATE FUNCTION tpo.protect_articolo_constitutive_authority()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.denominazione IS DISTINCT FROM OLD.denominazione
     OR NEW.unita_misura IS DISTINCT FROM OLD.unita_misura
  THEN
    RAISE EXCEPTION 'Articolo constitutive authority is immutable';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER protect_articolo_constitutive_authority
BEFORE UPDATE ON tpo.articoli
FOR EACH ROW EXECUTE FUNCTION tpo.protect_articolo_constitutive_authority();

CREATE FUNCTION tpo.protect_articolo_commissioning_request()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
     AND NEW.operation_scope=OLD.operation_scope
     AND NEW.idempotency_key=OLD.idempotency_key
     AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
     AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
     AND OLD.articolo_id IS NULL AND OLD.result_public_id IS NULL
     AND NEW.articolo_id IS NOT NULL AND NEW.result_public_id IS NOT NULL THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Articolo commissioning request authority is immutable';
END $$;
CREATE TRIGGER protect_articolo_commissioning_request
BEFORE UPDATE OR DELETE ON tpo.articolo_commissioning_requests
FOR EACH ROW EXECUTE FUNCTION tpo.protect_articolo_commissioning_request();

CREATE FUNCTION tpo.protect_movimento_articolo_request()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
     AND NEW.operation_scope=OLD.operation_scope
     AND NEW.idempotency_key=OLD.idempotency_key
     AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
     AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
     AND OLD.movimento_id IS NULL AND OLD.result_public_id IS NULL
     AND NEW.movimento_id IS NOT NULL AND NEW.result_public_id IS NOT NULL THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Movimento articolo request authority is immutable';
END $$;
CREATE TRIGGER protect_movimento_articolo_request
BEFORE UPDATE OR DELETE ON tpo.movimento_articolo_requests
FOR EACH ROW EXECUTE FUNCTION tpo.protect_movimento_articolo_request();
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "articoli",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("public_id", sa.Text(), nullable=False, unique=True),
        sa.Column("denominazione", sa.Text(), nullable=False),
        sa.Column("unita_misura", UOM, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.CheckConstraint("btrim(denominazione)<>''", name="ck_articoli_denominazione_not_blank"),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_articoli_created_by_not_blank"),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_articoli_public_id_format", "articoli", "public_id ~ '^ART-[0-9]{6,}$'", schema=SCHEMA,
    )
    with op.batch_alter_table("articoli", schema=SCHEMA) as batch:
        batch.create_unique_constraint("uq_articoli_id_public_id", ["id", "public_id"])

    op.create_table(
        "stock_articoli",
        sa.Column("articolo_id", sa.BigInteger(), primary_key=True),
        sa.Column("disponibile", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("unita_misura", UOM, nullable=False),
        sa.Column("ultimo_movimento_id", sa.BigInteger()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["articolo_id"], [f"{SCHEMA}.articoli.id"], onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["ultimo_movimento_id"], [f"{SCHEMA}.movimenti_magazzino.id"],
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("articolo_id", "unita_misura", name="uq_stock_articoli_articolo_unita"),
        sa.CheckConstraint("disponibile >= 0", name="ck_stock_articoli_disponibile_nonnegative"),
        sa.CheckConstraint("version >= 0", name="ck_stock_articoli_version_nonnegative"),
        schema=SCHEMA,
    )
    op.create_index("ix_stock_articoli_updated_at", "stock_articoli", ["updated_at"], schema=SCHEMA)

    with op.batch_alter_table("movimenti_magazzino", schema=SCHEMA) as batch:
        batch.alter_column("varieta_id", existing_type=sa.BigInteger(), nullable=True)
        batch.add_column(sa.Column("articolo_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_movimenti_magazzino_articolo_id", "movimenti_magazzino", "articoli",
        ["articolo_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA,
        onupdate="RESTRICT", ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_movimenti_magazzino_risorsa_xor", "movimenti_magazzino",
        MOVIMENTI_MAGAZZINO_RISORSA_XOR, schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_movimenti_magazzino_articolo_stock", "movimenti_magazzino", "stock_articoli",
        ["articolo_id", "unita_misura"], ["articolo_id", "unita_misura"],
        source_schema=SCHEMA, referent_schema=SCHEMA, onupdate="RESTRICT", ondelete="RESTRICT",
    )

    hash_check = "canonical_payload_hash ~ '^[0-9a-f]{64}$'"
    op.create_table(
        "articolo_commissioning_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("articolo_id", sa.BigInteger()),
        sa.Column("result_public_id", sa.Text()),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["articolo_id", "result_public_id"],
            [f"{SCHEMA}.articoli.id", f"{SCHEMA}.articoli.public_id"],
            onupdate="RESTRICT", ondelete="RESTRICT",
            name="fk_articolo_commissioning_authoritative_result",
            deferrable=True, initially="DEFERRED",
        ),
        sa.UniqueConstraint("operation_scope", "idempotency_key", name="uq_articolo_commissioning_request_key"),
        sa.UniqueConstraint("articolo_id", name="uq_articolo_commissioning_articolo"),
        sa.UniqueConstraint("result_public_id", name="uq_articolo_commissioning_result"),
        sa.CheckConstraint("operation_scope='ARTICOLO_COMMISSIONING_V1'", name="ck_articolo_commissioning_scope"),
        sa.CheckConstraint("btrim(idempotency_key)<>''", name="ck_articolo_commissioning_key"),
        sa.CheckConstraint(hash_check, name="ck_articolo_commissioning_hash"),
        sa.CheckConstraint(
            "(outcome='RESERVED' AND articolo_id IS NULL AND result_public_id IS NULL) OR "
            "(outcome='COMMITTED' AND articolo_id IS NOT NULL AND result_public_id IS NOT NULL)",
            name="ck_articolo_commissioning_outcome",
        ),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_articolo_commissioning_actor"),
        schema=SCHEMA,
    )
    op.create_index("ix_articolo_commissioning_result", "articolo_commissioning_requests", ["result_public_id"], schema=SCHEMA)

    op.create_table(
        "movimento_articolo_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("operation_scope", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("canonical_payload_hash", sa.Text(), nullable=False),
        sa.Column("movimento_id", sa.BigInteger()),
        sa.Column("result_public_id", sa.Text()),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["movimento_id", "result_public_id"],
            [f"{SCHEMA}.movimenti_magazzino.id", f"{SCHEMA}.movimenti_magazzino.public_id"],
            onupdate="RESTRICT", ondelete="RESTRICT",
            name="fk_movimento_articolo_authoritative_result",
            deferrable=True, initially="DEFERRED",
        ),
        sa.UniqueConstraint("operation_scope", "idempotency_key", name="uq_movimento_articolo_request_key"),
        sa.UniqueConstraint("movimento_id", name="uq_movimento_articolo_movimento"),
        sa.UniqueConstraint("result_public_id", name="uq_movimento_articolo_result"),
        sa.CheckConstraint("operation_scope='MOVIMENTO_ARTICOLO_V1'", name="ck_movimento_articolo_scope"),
        sa.CheckConstraint("btrim(idempotency_key)<>''", name="ck_movimento_articolo_key"),
        sa.CheckConstraint(hash_check, name="ck_movimento_articolo_hash"),
        sa.CheckConstraint(
            "(outcome='RESERVED' AND movimento_id IS NULL AND result_public_id IS NULL) OR "
            "(outcome='COMMITTED' AND movimento_id IS NOT NULL AND result_public_id IS NOT NULL)",
            name="ck_movimento_articolo_outcome",
        ),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_movimento_articolo_actor"),
        schema=SCHEMA,
    )
    op.create_index("ix_movimento_articolo_result", "movimento_articolo_requests", ["result_public_id"], schema=SCHEMA)

    op.execute(sa.text(
        """INSERT INTO tpo.id_sequences
           (sequence_name,identifier_type,prefix,next_value,version,updated_at,updated_by)
           VALUES ('ARTICOLO_ID','ArticoloId','ART',1,0,CURRENT_TIMESTAMP,
                   'migration-20260905-0031')"""
    ))

    op.execute(TRIGGERS_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not context.is_offline_mode():
        for table in ("articoli", "movimento_articolo_requests", "articolo_commissioning_requests"):
            count = bind.execute(sa.text(f"SELECT count(*) FROM tpo.{table}")).scalar_one()
            if count:
                raise RuntimeError(
                    f"cannot downgrade: governed ARTICOLO authority history exists in tpo.{table}"
                )

    op.execute("""
DROP TRIGGER protect_movimento_articolo_request ON tpo.movimento_articolo_requests;
DROP FUNCTION tpo.protect_movimento_articolo_request();
DROP TRIGGER protect_articolo_commissioning_request ON tpo.articolo_commissioning_requests;
DROP FUNCTION tpo.protect_articolo_commissioning_request();
DROP TRIGGER protect_articolo_constitutive_authority ON tpo.articoli;
DROP FUNCTION tpo.protect_articolo_constitutive_authority();
""")

    op.execute(sa.text(
        "DELETE FROM tpo.id_sequences WHERE sequence_name='ARTICOLO_ID' "
        "AND identifier_type='ArticoloId' AND prefix='ART' AND next_value=1 AND version=0"
    ))

    op.drop_index("ix_movimento_articolo_result", table_name="movimento_articolo_requests", schema=SCHEMA)
    op.drop_table("movimento_articolo_requests", schema=SCHEMA)
    op.drop_index("ix_articolo_commissioning_result", table_name="articolo_commissioning_requests", schema=SCHEMA)
    op.drop_table("articolo_commissioning_requests", schema=SCHEMA)

    op.drop_constraint("fk_movimenti_magazzino_articolo_stock", "movimenti_magazzino", schema=SCHEMA, type_="foreignkey")
    op.drop_constraint("ck_movimenti_magazzino_risorsa_xor", "movimenti_magazzino", schema=SCHEMA, type_="check")
    op.drop_constraint("fk_movimenti_magazzino_articolo_id", "movimenti_magazzino", schema=SCHEMA, type_="foreignkey")
    with op.batch_alter_table("movimenti_magazzino", schema=SCHEMA) as batch:
        batch.drop_column("articolo_id")
        batch.alter_column("varieta_id", existing_type=sa.BigInteger(), nullable=False)

    op.drop_index("ix_stock_articoli_updated_at", table_name="stock_articoli", schema=SCHEMA)
    op.drop_table("stock_articoli", schema=SCHEMA)

    with op.batch_alter_table("articoli", schema=SCHEMA) as batch:
        batch.drop_constraint("uq_articoli_id_public_id", type_="unique")
    op.drop_table("articoli", schema=SCHEMA)
