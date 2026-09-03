"""Fattura Emission Boundary V1 persistence.

Revision ID: 20260903_0026
Revises: 20260903_0025
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0026"
down_revision: str | Sequence[str] | None = "20260903_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

unit_of_measure = postgresql.ENUM(
    "SET", "GRAM", "UNIT", name="unit_of_measure", schema=SCHEMA, create_type=False,
)

TRIGGERS_SQL = """
CREATE FUNCTION tpo.fn_fatture_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'tr_fatture_immutable violated'; END;
$$;
CREATE TRIGGER tr_fatture_immutable
BEFORE UPDATE OR DELETE ON tpo.fatture
FOR EACH ROW EXECUTE FUNCTION tpo.fn_fatture_immutable();

CREATE FUNCTION tpo.fn_fatture_consegne_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'tr_fatture_consegne_immutable violated'; END;
$$;
CREATE TRIGGER tr_fatture_consegne_immutable
BEFORE UPDATE OR DELETE ON tpo.fatture_consegne
FOR EACH ROW EXECUTE FUNCTION tpo.fn_fatture_consegne_immutable();

CREATE FUNCTION tpo.fn_righe_fattura_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'tr_righe_fattura_immutable violated'; END;
$$;
CREATE TRIGGER tr_righe_fattura_immutable
BEFORE UPDATE OR DELETE ON tpo.righe_fattura
FOR EACH ROW EXECUTE FUNCTION tpo.fn_righe_fattura_immutable();

CREATE FUNCTION tpo.fn_fattura_emissione_request_protect() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
     AND NEW.operation_scope=OLD.operation_scope
     AND NEW.idempotency_key=OLD.idempotency_key
     AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
     AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
     AND OLD.fattura_id IS NULL AND NEW.fattura_id IS NOT NULL THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'tr_fattura_emissione_request_protect violated';
END;
$$;
CREATE TRIGGER tr_fattura_emissione_request_protect
BEFORE UPDATE OR DELETE ON tpo.fattura_emissione_requests
FOR EACH ROW EXECUTE FUNCTION tpo.fn_fattura_emissione_request_protect();
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "clienti",
        sa.Column("modalita_fatturazione", sa.Text()),
        schema=SCHEMA,
    )
    op.add_column(
        "clienti",
        sa.Column("termini_pagamento_giorni", sa.Integer()),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_clienti_modalita_fatturazione",
        "clienti",
        "modalita_fatturazione IS NULL OR modalita_fatturazione IN ('A_CONSEGNA','PERIODICA_MENSILE')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_clienti_termini_pagamento_positive",
        "clienti",
        "termini_pagamento_giorni IS NULL OR termini_pagamento_giorni > 0",
        schema=SCHEMA,
    )

    op.create_table(
        "listino_varieta",
        sa.Column("varieta_id", sa.BigInteger(), primary_key=True),
        sa.Column("prezzo_unitario", sa.Numeric(12, 4), nullable=False),
        sa.Column("aliquota_igic", sa.Numeric(5, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["varieta_id"], [f"{SCHEMA}.varieta.id"],
            name="fk_listino_varieta_varieta", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("prezzo_unitario >= 0", name="ck_listino_varieta_prezzo_nonneg"),
        sa.CheckConstraint(
            "aliquota_igic >= 0 AND aliquota_igic <= 100", name="ck_listino_varieta_aliquota_range",
        ),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_listino_varieta_created_by_not_blank"),
        sa.CheckConstraint("btrim(updated_by) <> ''", name="ck_listino_varieta_updated_by_not_blank"),
        schema=SCHEMA,
    )

    op.create_table(
        "fattura_numerazione",
        sa.Column("anno", sa.Integer(), primary_key=True),
        sa.Column("next_value", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint("anno >= 2000", name="ck_fattura_numerazione_anno_valid"),
        sa.CheckConstraint("next_value > 0", name="ck_fattura_numerazione_next_value_positive"),
        sa.CheckConstraint("version >= 0", name="ck_fattura_numerazione_version_nonnegative"),
        schema=SCHEMA,
    )

    op.create_table(
        "fatture",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("numero_fattura", sa.Text(), nullable=False, unique=True),
        sa.Column("cliente_id", sa.BigInteger(), nullable=False),
        sa.Column("data_emissione", sa.Date(), nullable=False),
        sa.Column("scadenza", sa.Date(), nullable=False),
        sa.Column("totale_netto", sa.Numeric(14, 2), nullable=False),
        sa.Column("totale_igic", sa.Numeric(14, 2), nullable=False),
        sa.Column("totale", sa.Numeric(14, 2), nullable=False),
        sa.Column("rettifica_di", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cliente_id"], [f"{SCHEMA}.clienti.id"],
            name="fk_fatture_cliente", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rettifica_di"], [f"{SCHEMA}.fatture.numero_fattura"],
            name="fk_fatture_rettifica_di", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "numero_fattura ~ '^[0-9]{4}/[0-9]{4}$'", name="ck_fatture_numero_format",
        ),
        sa.CheckConstraint(
            "rettifica_di IS NULL OR rettifica_di <> numero_fattura", name="ck_fatture_rettifica_not_self",
        ),
        sa.CheckConstraint(
            "totale = totale_netto + totale_igic", name="ck_fatture_totale_coerente",
        ),
        sa.CheckConstraint("scadenza >= data_emissione", name="ck_fatture_scadenza_not_before_emissione"),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_fatture_created_by_not_blank"),
        schema=SCHEMA,
    )
    op.create_index("ix_fatture_cliente_id", "fatture", ["cliente_id"], schema=SCHEMA)
    op.create_index("ix_fatture_data_emissione", "fatture", ["data_emissione"], schema=SCHEMA)
    op.create_index("ix_fatture_rettifica_di", "fatture", ["rettifica_di"], schema=SCHEMA)

    op.create_table(
        "fatture_consegne",
        sa.Column("fattura_id", sa.BigInteger(), nullable=False),
        sa.Column("consegna_id", sa.BigInteger(), nullable=False),
        sa.Column("posizione", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("fattura_id", "consegna_id", name="pk_fatture_consegne"),
        sa.UniqueConstraint("fattura_id", "posizione", name="uq_fatture_consegne_fattura_posizione"),
        sa.UniqueConstraint("consegna_id", name="uq_fatture_consegne_consegna"),
        sa.CheckConstraint("posizione > 0", name="ck_fatture_consegne_posizione_positive"),
        sa.ForeignKeyConstraint(
            ["fattura_id"], [f"{SCHEMA}.fatture.id"],
            name="fk_fatture_consegne_fattura", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["consegna_id"], [f"{SCHEMA}.consegne.id"],
            name="fk_fatture_consegne_consegna", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "righe_fattura",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("fattura_id", sa.BigInteger(), nullable=False),
        sa.Column("riga_consegna_id", sa.BigInteger(), nullable=False),
        sa.Column("posizione", sa.Integer(), nullable=False),
        sa.Column("varieta_id", sa.BigInteger(), nullable=False),
        sa.Column("quantita", sa.Numeric(20, 6), nullable=False),
        sa.Column("unita_misura", unit_of_measure, nullable=False),
        sa.Column("prezzo_unitario", sa.Numeric(12, 4), nullable=False),
        sa.Column("aliquota_igic", sa.Numeric(5, 2), nullable=False),
        sa.Column("importo_netto", sa.Numeric(14, 2), nullable=False),
        sa.Column("importo_igic", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.UniqueConstraint("fattura_id", "posizione", name="uq_righe_fattura_fattura_posizione"),
        sa.UniqueConstraint("riga_consegna_id", name="uq_righe_fattura_riga_consegna"),
        sa.CheckConstraint("posizione > 0", name="ck_righe_fattura_posizione_positive"),
        sa.CheckConstraint("quantita > 0", name="ck_righe_fattura_quantita_positive"),
        sa.CheckConstraint("prezzo_unitario >= 0", name="ck_righe_fattura_prezzo_nonneg"),
        sa.CheckConstraint(
            "aliquota_igic >= 0 AND aliquota_igic <= 100", name="ck_righe_fattura_aliquota_range",
        ),
        sa.CheckConstraint("btrim(created_by) <> ''", name="ck_righe_fattura_created_by_not_blank"),
        sa.ForeignKeyConstraint(
            ["fattura_id"], [f"{SCHEMA}.fatture.id"],
            name="fk_righe_fattura_fattura", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["riga_consegna_id"], [f"{SCHEMA}.righe_consegna.id"],
            name="fk_righe_fattura_riga_consegna", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["varieta_id"], [f"{SCHEMA}.varieta.id"],
            name="fk_righe_fattura_varieta", onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_righe_fattura_fattura_id", "righe_fattura", ["fattura_id"], schema=SCHEMA)
    op.create_index("ix_righe_fattura_varieta_id", "righe_fattura", ["varieta_id"], schema=SCHEMA)

    hash_check = "canonical_payload_hash ~ '^[0-9a-f]{64}$'"
    op.create_table(
        "fattura_emissione_requests",
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
            name="fk_fattura_emissione_requests_fattura",
            onupdate="RESTRICT", ondelete="RESTRICT",
            deferrable=True, initially="DEFERRED",
        ),
        sa.UniqueConstraint(
            "operation_scope", "idempotency_key", name="uq_fattura_emissione_request_key",
        ),
        sa.UniqueConstraint("fattura_id", name="uq_fattura_emissione_request_fattura"),
        sa.CheckConstraint(
            "operation_scope='FATTURA_EMISSIONE_V1'", name="ck_fattura_emissione_request_scope",
        ),
        sa.CheckConstraint("btrim(idempotency_key)<>''", name="ck_fattura_emissione_request_key"),
        sa.CheckConstraint(hash_check, name="ck_fattura_emissione_request_hash"),
        sa.CheckConstraint(
            "(outcome='RESERVED' AND fattura_id IS NULL) OR "
            "(outcome='COMMITTED' AND fattura_id IS NOT NULL)",
            name="ck_fattura_emissione_request_outcome",
        ),
        sa.CheckConstraint("btrim(created_by)<>''", name="ck_fattura_emissione_request_actor"),
        schema=SCHEMA,
    )

    op.execute(TRIGGERS_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not context.is_offline_mode():
        facts = bind.execute(sa.text("SELECT count(*) FROM tpo.fatture")).scalar_one()
        requests = bind.execute(
            sa.text("SELECT count(*) FROM tpo.fattura_emissione_requests")
        ).scalar_one()
        if facts or requests:
            raise RuntimeError("cannot downgrade: governed FATTURA authority history exists")

    op.execute("""
DROP TRIGGER tr_fattura_emissione_request_protect ON tpo.fattura_emissione_requests;
DROP FUNCTION tpo.fn_fattura_emissione_request_protect();
DROP TRIGGER tr_righe_fattura_immutable ON tpo.righe_fattura;
DROP FUNCTION tpo.fn_righe_fattura_immutable();
DROP TRIGGER tr_fatture_consegne_immutable ON tpo.fatture_consegne;
DROP FUNCTION tpo.fn_fatture_consegne_immutable();
DROP TRIGGER tr_fatture_immutable ON tpo.fatture;
DROP FUNCTION tpo.fn_fatture_immutable();
""")

    op.drop_table("fattura_emissione_requests", schema=SCHEMA)
    op.drop_index("ix_righe_fattura_varieta_id", table_name="righe_fattura", schema=SCHEMA)
    op.drop_index("ix_righe_fattura_fattura_id", table_name="righe_fattura", schema=SCHEMA)
    op.drop_table("righe_fattura", schema=SCHEMA)
    op.drop_table("fatture_consegne", schema=SCHEMA)
    op.drop_index("ix_fatture_rettifica_di", table_name="fatture", schema=SCHEMA)
    op.drop_index("ix_fatture_data_emissione", table_name="fatture", schema=SCHEMA)
    op.drop_index("ix_fatture_cliente_id", table_name="fatture", schema=SCHEMA)
    op.drop_table("fatture", schema=SCHEMA)
    op.drop_table("fattura_numerazione", schema=SCHEMA)
    op.drop_table("listino_varieta", schema=SCHEMA)
    op.drop_constraint("ck_clienti_termini_pagamento_positive", "clienti", schema=SCHEMA, type_="check")
    op.drop_constraint("ck_clienti_modalita_fatturazione", "clienti", schema=SCHEMA, type_="check")
    op.drop_column("clienti", "termini_pagamento_giorni", schema=SCHEMA)
    op.drop_column("clienti", "modalita_fatturazione", schema=SCHEMA)
