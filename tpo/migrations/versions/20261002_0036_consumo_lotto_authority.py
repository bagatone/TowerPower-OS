"""Crea l'autorità CONSUMO_LOTTO: collega ogni MOVIMENTO SCARICO (uscita per
CONSEGNA) ai MOVIMENTI CARICO (ingressi da RACCOLTA) da cui la quantità e'
realmente stata prelevata, in ordine FIFO per data di carico, preservando le
componenti di origine `AAA-GGMM-L` senza fonderle (vedi
docs/architecture/RACCOLTA_AUTHORITY_FREEZE.md §12 e
docs/architecture/CONSUMO_LOTTO_AUTHORITY_FREEZE.md).

Backfill storico incluso in questa stessa migrazione (puro calcolo
aritmetico su dati reali gia' committati, nessun dato inventato): per ogni
VARIETA+UNITA, la quantita' totale gia' scaricata PRIMA di questa migrazione
viene "pre-consumata" dai CARICO piu' vecchi (FIFO), come riga
tipo_consumo='BACKFILL_STORICO' con movimento_scarico_id=NULL -- non
attribuita a nessuna CONSEGNA specifica (nessuna bolla retroattiva), serve
solo a correggere il residuo dei lotti vecchi cosi' che una CONSEGNA futura
non possa mai erroneamente "ripescare" quantita' di un CARICO che in realta'
era gia' stato consumato prima che questo meccanismo esistesse.

Revision ID: 20261002_0036
Revises: 20260919_0035
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261002_0036"
down_revision: str | Sequence[str] | None = "20260919_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

consumo_lotto_tipo = postgresql.ENUM(
    "CONSEGNA", "BACKFILL_STORICO", name="consumo_lotto_tipo", schema=SCHEMA, create_type=False
)
NEW_ENUMS = (consumo_lotto_tipo,)

CHECK_TIPO_COERENTE = (
    "(tipo_consumo = 'CONSEGNA' AND movimento_scarico_id IS NOT NULL) OR "
    "(tipo_consumo = 'BACKFILL_STORICO' AND movimento_scarico_id IS NULL)"
)

FUNCTIONS_SQL = r"""
CREATE FUNCTION tpo.fn_check_consumo_lotto_bounds(target_carico bigint, target_scarico bigint) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  carico_tipo tpo.movimento_type; carico_dir tpo.movimento_direction;
  carico_var bigint; carico_uom tpo.unit_of_measure; carico_qty numeric(20,6);
  scarico_tipo tpo.movimento_type; scarico_dir tpo.movimento_direction;
  scarico_var bigint; scarico_uom tpo.unit_of_measure; scarico_qty numeric(20,6);
  carico_consumed numeric; scarico_spiegato numeric;
BEGIN
  SELECT tipo, direzione, varieta_id, unita_misura, quantita
    INTO carico_tipo, carico_dir, carico_var, carico_uom, carico_qty
    FROM tpo.movimenti_magazzino WHERE id = target_carico;
  IF carico_tipo IS NULL OR carico_tipo <> 'CARICO' OR carico_dir <> 'POSITIVO' THEN
    RAISE EXCEPTION 'ct_consumi_lotto_carico_tipo violated for movimento %', target_carico;
  END IF;
  SELECT COALESCE(SUM(quantita), 0) INTO carico_consumed
    FROM tpo.consumi_lotto WHERE movimento_carico_id = target_carico;
  IF carico_consumed > carico_qty THEN
    RAISE EXCEPTION 'ct_consumi_lotto_carico_bounds violated for movimento %', target_carico;
  END IF;
  IF target_scarico IS NOT NULL THEN
    SELECT tipo, direzione, varieta_id, unita_misura, quantita
      INTO scarico_tipo, scarico_dir, scarico_var, scarico_uom, scarico_qty
      FROM tpo.movimenti_magazzino WHERE id = target_scarico;
    IF scarico_tipo IS NULL OR scarico_tipo <> 'SCARICO' OR scarico_dir <> 'NEGATIVO' THEN
      RAISE EXCEPTION 'ct_consumi_lotto_scarico_tipo violated for movimento %', target_scarico;
    END IF;
    IF scarico_var <> carico_var OR scarico_uom <> carico_uom THEN
      RAISE EXCEPTION 'ct_consumi_lotto_varieta_unita_coerente violated (carico=%, scarico=%)', target_carico, target_scarico;
    END IF;
    SELECT COALESCE(SUM(quantita), 0) INTO scarico_spiegato
      FROM tpo.consumi_lotto WHERE movimento_scarico_id = target_scarico;
    IF scarico_spiegato > scarico_qty THEN
      RAISE EXCEPTION 'ct_consumi_lotto_scarico_bounds violated for movimento %', target_scarico;
    END IF;
  END IF;
END;
$$;

CREATE FUNCTION tpo.fn_consumi_lotto_bounds() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  PERFORM tpo.fn_check_consumo_lotto_bounds(NEW.movimento_carico_id, NEW.movimento_scarico_id);
  RETURN NEW;
END;
$$;
"""

BACKFILL_SQL = r"""
DO $$
DECLARE
  rec RECORD;
  carico RECORD;
  restante numeric(20,6);
  presa numeric(20,6);
BEGIN
  FOR rec IN
    SELECT varieta_id, unita_misura, COALESCE(SUM(quantita), 0) AS totale_scaricato
    FROM tpo.movimenti_magazzino WHERE tipo = 'SCARICO'
    GROUP BY varieta_id, unita_misura
  LOOP
    restante := rec.totale_scaricato;
    IF restante <= 0 THEN CONTINUE; END IF;
    FOR carico IN
      SELECT id, quantita FROM tpo.movimenti_magazzino
      WHERE tipo = 'CARICO' AND varieta_id = rec.varieta_id AND unita_misura = rec.unita_misura
      ORDER BY data_movimento ASC, id ASC
    LOOP
      IF restante <= 0 THEN EXIT; END IF;
      presa := LEAST(carico.quantita, restante);
      INSERT INTO tpo.consumi_lotto
        (movimento_carico_id, movimento_scarico_id, tipo_consumo, quantita, created_at, created_by)
      VALUES (carico.id, NULL, 'BACKFILL_STORICO', presa, now(), 'migration-20261002-0036-backfill-storico');
      restante := restante - presa;
    END LOOP;
  END LOOP;
END;
$$;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum in NEW_ENUMS:
            enum.create(bind, checkfirst=True)

    op.create_table(
        "consumi_lotto",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("movimento_carico_id", sa.BigInteger(), nullable=False),
        sa.Column("movimento_scarico_id", sa.BigInteger()),
        sa.Column("tipo_consumo", consumo_lotto_tipo, nullable=False),
        sa.Column("quantita", sa.Numeric(20, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["movimento_carico_id"], [f"{SCHEMA}.movimenti_magazzino.id"], name="fk_consumi_lotto_carico", onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["movimento_scarico_id"], [f"{SCHEMA}.movimenti_magazzino.id"], name="fk_consumi_lotto_scarico", onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.CheckConstraint("quantita > 0", name="ck_consumi_lotto_quantita_positive"),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_consumi_lotto_created_by_not_blank"),
        sa.CheckConstraint(CHECK_TIPO_COERENTE, name="ck_consumi_lotto_tipo_coerente"),
        schema=SCHEMA,
    )
    op.create_index("ix_consumi_lotto_movimento_carico_id", "consumi_lotto", ["movimento_carico_id"], schema=SCHEMA)
    op.create_index("ix_consumi_lotto_movimento_scarico_id", "consumi_lotto", ["movimento_scarico_id"], schema=SCHEMA)
    op.create_index(
        "uq_consumi_lotto_consegna_unica", "consumi_lotto",
        ["movimento_scarico_id", "movimento_carico_id"], unique=True,
        postgresql_where=sa.text("tipo_consumo = 'CONSEGNA'"), schema=SCHEMA,
    )
    op.create_index(
        "uq_consumi_lotto_backfill_unico", "consumi_lotto",
        ["movimento_carico_id"], unique=True,
        postgresql_where=sa.text("tipo_consumo = 'BACKFILL_STORICO'"), schema=SCHEMA,
    )

    if bind.dialect.name == "postgresql":
        op.execute(FUNCTIONS_SQL)
        op.execute(
            "CREATE CONSTRAINT TRIGGER ct_consumi_lotto_bounds AFTER INSERT ON tpo.consumi_lotto "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION tpo.fn_consumi_lotto_bounds()"
        )
        op.execute(BACKFILL_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER ct_consumi_lotto_bounds ON tpo.consumi_lotto")
        op.execute("DROP FUNCTION tpo.fn_consumi_lotto_bounds()")
        op.execute("DROP FUNCTION tpo.fn_check_consumo_lotto_bounds(bigint, bigint)")
    op.drop_index("uq_consumi_lotto_backfill_unico", table_name="consumi_lotto", schema=SCHEMA)
    op.drop_index("uq_consumi_lotto_consegna_unica", table_name="consumi_lotto", schema=SCHEMA)
    op.drop_index("ix_consumi_lotto_movimento_scarico_id", table_name="consumi_lotto", schema=SCHEMA)
    op.drop_index("ix_consumi_lotto_movimento_carico_id", table_name="consumi_lotto", schema=SCHEMA)
    op.drop_table("consumi_lotto", schema=SCHEMA)
    if bind.dialect.name == "postgresql":
        for enum in reversed(NEW_ENUMS):
            enum.drop(bind, checkfirst=True)
