"""REGISTRO FATTURE ESTERNE + dati fiscali cliente (31/10/2026, richiesta di Matteo).

Revision ID: 20261031_0040
Revises: 20261020_0039

Le fatture di Tower Power sono state emesse FUORI da TPO (PDF TP-2026-NNN) e il sistema non le conosce. Questa migrazione
aggiunge solo il registro per riportarle dentro, senza toccare `tpo.fatture` (emissione governata) ne' la sua numerazione:

  - tpo.dati_fiscali_cliente: ragione sociale, CIF/NIF e indirizzo del cliente (Configuration mutabile, 1 riga per cliente).
  - tpo.fatture_esterne: una riga per documento (fattura o rettificativa) con numero come scritto sul PDF. Il numero NON e'
    unico: il registro storico ha numeri duplicati (005/006/008) che vanno registrati cosi' come sono e segnalati in
    `anomalia`, non corretti di nascosto. Unicita': (numero, data_emissione, cliente_nome).
    Importi: totale obbligatorio; imponibile/IGIC solo se verificati sul documento (altrimenti NULL).
    Si possono modificare solo `cliente_id`, `anomalia` e `note` (trigger); il resto e' definitivo.
  - tpo.fatture_esterne_consegne: quali CONSEGNE copre una fattura. Una consegna e' coperta da una sola fattura
    (UNIQUE): le fatture ANNULLATE non si collegano a consegne.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261031_0040"
down_revision: str | Sequence[str] | None = "20261020_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

TRIGGERS_SQL = r"""
CREATE FUNCTION tpo.fn_fatture_esterne_protect() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE'
     AND NEW.id = OLD.id AND NEW.numero = OLD.numero AND NEW.data_emissione = OLD.data_emissione
     AND NEW.cliente_nome = OLD.cliente_nome AND NEW.imponibile IS NOT DISTINCT FROM OLD.imponibile
     AND NEW.igic IS NOT DISTINCT FROM OLD.igic AND NEW.totale = OLD.totale AND NEW.tipo = OLD.tipo
     AND NEW.stato = OLD.stato AND NEW.rettifica_di IS NOT DISTINCT FROM OLD.rettifica_di
     AND NEW.created_at = OLD.created_at AND NEW.created_by = OLD.created_by THEN
    RETURN NEW;      -- consentiti solo cliente_id, anomalia, note, fonte
  END IF;
  RAISE EXCEPTION 'tr_fatture_esterne_protect: una fattura registrata e'' definitiva (modificabili solo cliente_id, anomalia, note)';
END $$;
CREATE TRIGGER tr_fatture_esterne_protect BEFORE UPDATE OR DELETE ON tpo.fatture_esterne
FOR EACH ROW EXECUTE FUNCTION tpo.fn_fatture_esterne_protect();

CREATE FUNCTION tpo.fn_fatture_esterne_consegne_protect() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'tr_fatture_esterne_consegne_protect: il collegamento fattura-consegna e'' definitivo'; END $$;
CREATE TRIGGER tr_fatture_esterne_consegne_protect BEFORE UPDATE OR DELETE ON tpo.fatture_esterne_consegne
FOR EACH ROW EXECUTE FUNCTION tpo.fn_fatture_esterne_consegne_protect();
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "dati_fiscali_cliente",
        sa.Column("cliente_id", sa.BigInteger(), primary_key=True),
        sa.Column("ragione_sociale", sa.Text(), nullable=False),
        sa.Column("cif_nif", sa.Text()),
        sa.Column("indirizzo", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.CheckConstraint("btrim(ragione_sociale) <> ''", name="ck_dati_fiscali_ragione_sociale_not_blank"),
        sa.ForeignKeyConstraint(["cliente_id"], [f"{SCHEMA}.clienti.id"], name="fk_dati_fiscali_cliente",
                                onupdate="RESTRICT", ondelete="RESTRICT"),
        schema=SCHEMA,
    )

    op.create_table(
        "fatture_esterne",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("numero", sa.Text(), nullable=False),
        sa.Column("data_emissione", sa.Date(), nullable=False),
        sa.Column("cliente_id", sa.BigInteger()),
        sa.Column("cliente_nome", sa.Text(), nullable=False),
        sa.Column("imponibile", sa.Numeric(14, 2)),
        sa.Column("igic", sa.Numeric(14, 2)),
        sa.Column("totale", sa.Numeric(14, 2), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False, server_default="FATTURA"),
        sa.Column("stato", sa.Text(), nullable=False, server_default="EMESSA"),
        sa.Column("rettifica_di", sa.Text()),
        sa.Column("anomalia", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("fonte", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.CheckConstraint("btrim(numero) <> ''", name="ck_fatture_esterne_numero_not_blank"),
        sa.CheckConstraint("btrim(cliente_nome) <> ''", name="ck_fatture_esterne_cliente_nome_not_blank"),
        sa.CheckConstraint("tipo IN ('FATTURA','RETTIFICATIVA')", name="ck_fatture_esterne_tipo"),
        sa.CheckConstraint("stato IN ('EMESSA','ANNULLATA')", name="ck_fatture_esterne_stato"),
        sa.CheckConstraint("tipo = 'RETTIFICATIVA' OR totale >= 0", name="ck_fatture_esterne_totale_segno"),
        sa.CheckConstraint("rettifica_di IS NULL OR tipo = 'RETTIFICATIVA'", name="ck_fatture_esterne_rettifica_di_tipo"),
        sa.CheckConstraint(
            "(imponibile IS NULL AND igic IS NULL) OR (imponibile IS NOT NULL AND igic IS NOT NULL "
            "AND imponibile + igic = totale)", name="ck_fatture_esterne_importi_coerenti"),
        sa.UniqueConstraint("numero", "data_emissione", "cliente_nome", name="uq_fatture_esterne_documento"),
        sa.ForeignKeyConstraint(["cliente_id"], [f"{SCHEMA}.clienti.id"], name="fk_fatture_esterne_cliente",
                                onupdate="RESTRICT", ondelete="RESTRICT"),
        schema=SCHEMA,
    )
    op.create_index("ix_fatture_esterne_numero", "fatture_esterne", ["numero"], schema=SCHEMA)
    op.create_index("ix_fatture_esterne_cliente_id", "fatture_esterne", ["cliente_id"], schema=SCHEMA)

    op.create_table(
        "fatture_esterne_consegne",
        sa.Column("fattura_esterna_id", sa.BigInteger(), nullable=False),
        sa.Column("consegna_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("fattura_esterna_id", "consegna_id", name="pk_fatture_esterne_consegne"),
        sa.UniqueConstraint("consegna_id", name="uq_fatture_esterne_consegne_consegna"),
        sa.ForeignKeyConstraint(["fattura_esterna_id"], [f"{SCHEMA}.fatture_esterne.id"],
                                name="fk_fatture_esterne_consegne_fattura", onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["consegna_id"], [f"{SCHEMA}.consegne.id"],
                                name="fk_fatture_esterne_consegne_consegna", onupdate="RESTRICT", ondelete="RESTRICT"),
        schema=SCHEMA,
    )
    op.execute(TRIGGERS_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM tpo.fatture_esterne)")).scalar_one():
        raise RuntimeError("il registro fatture esterne contiene dati: il downgrade li perderebbe")
    op.execute("DROP TRIGGER IF EXISTS tr_fatture_esterne_consegne_protect ON tpo.fatture_esterne_consegne")
    op.execute("DROP TRIGGER IF EXISTS tr_fatture_esterne_protect ON tpo.fatture_esterne")
    op.drop_table("fatture_esterne_consegne", schema=SCHEMA)
    op.drop_table("fatture_esterne", schema=SCHEMA)
    op.drop_table("dati_fiscali_cliente", schema=SCHEMA)
    op.execute("DROP FUNCTION IF EXISTS tpo.fn_fatture_esterne_consegne_protect()")
    op.execute("DROP FUNCTION IF EXISTS tpo.fn_fatture_esterne_protect()")
