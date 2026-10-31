"""REGISTRO FATTURE ESTERNE: annullo con rettificativa + prezzo per SET per cliente (31/10/2026).

Revision ID: 20261031_0042
Revises: 20261031_0041

1. Annullo: una FATTURA EMESSA passa ad ANNULLATA solo se esiste una RETTIFICATIVA che la richiama (rettifica_di = numero)
   di importo opposto; tutto il resto della riga resta immutabile. Le consegne di una fattura ANNULLATA tornano fatturabili:
   il vincolo UNIQUE(consegna_id) diventa un controllo che considera solo le fatture EMESSE (i collegamenti restano
   immutabili: la storia dell'annullo si conserva).
2. tpo.dati_fiscali_cliente.prezzo_set_fattura: prezzo per SET applicato in fattura quando e' diverso dal listino
   (es. supplemento per la distanza di consegna). NULL = listino. Il listino TPO resta uno per varieta'.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261031_0042"
down_revision: str | Sequence[str] | None = "20261031_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROTECT_NUOVA = r"""
CREATE OR REPLACE FUNCTION tpo.fn_fatture_esterne_protect() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.id = OLD.id AND NEW.numero = OLD.numero AND NEW.data_emissione = OLD.data_emissione
       AND NEW.cliente_nome = OLD.cliente_nome AND NEW.imponibile IS NOT DISTINCT FROM OLD.imponibile
       AND NEW.igic IS NOT DISTINCT FROM OLD.igic AND NEW.totale = OLD.totale AND NEW.tipo = OLD.tipo
       AND NEW.stato = OLD.stato AND NEW.rettifica_di IS NOT DISTINCT FROM OLD.rettifica_di
       AND NEW.created_at = OLD.created_at AND NEW.created_by = OLD.created_by THEN
      RETURN NEW;      -- consentiti cliente_id, anomalia, note, fonte
    END IF;
    IF OLD.fonte LIKE 'registro del 31/10 compilato da ChatGPT%'
       AND NEW.fonte IS NOT NULL AND NEW.fonte NOT LIKE 'registro del 31/10 compilato da ChatGPT%'
       AND NEW.id = OLD.id AND NEW.tipo = OLD.tipo AND NEW.rettifica_di IS NOT DISTINCT FROM OLD.rettifica_di
       AND NEW.created_at = OLD.created_at AND NEW.created_by = OLD.created_by THEN
      RETURN NEW;      -- riga non verificata, corretta con il documento (fonte nuova)
    END IF;
    IF OLD.tipo = 'FATTURA' AND OLD.stato = 'EMESSA' AND NEW.stato = 'ANNULLATA'
       AND NEW.id = OLD.id AND NEW.numero = OLD.numero AND NEW.data_emissione = OLD.data_emissione
       AND NEW.cliente_nome = OLD.cliente_nome AND NEW.imponibile IS NOT DISTINCT FROM OLD.imponibile
       AND NEW.igic IS NOT DISTINCT FROM OLD.igic AND NEW.totale = OLD.totale AND NEW.tipo = OLD.tipo
       AND NEW.rettifica_di IS NOT DISTINCT FROM OLD.rettifica_di
       AND NEW.created_at = OLD.created_at AND NEW.created_by = OLD.created_by
       AND EXISTS (SELECT 1 FROM tpo.fatture_esterne r WHERE r.tipo = 'RETTIFICATIVA' AND r.rettifica_di = OLD.numero
                   AND r.totale = -OLD.totale) THEN
      RETURN NEW;      -- annullo: serve la rettificativa di importo opposto
    END IF;
  END IF;
  RAISE EXCEPTION 'tr_fatture_esterne_protect: una fattura verificata e'' definitiva (modificabili solo cliente_id, anomalia, note, fonte; annullo solo con rettificativa)';
END $$;
"""

PROTECT_VECCHIA = r"""
CREATE OR REPLACE FUNCTION tpo.fn_fatture_esterne_protect() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.id = OLD.id AND NEW.numero = OLD.numero AND NEW.data_emissione = OLD.data_emissione
       AND NEW.cliente_nome = OLD.cliente_nome AND NEW.imponibile IS NOT DISTINCT FROM OLD.imponibile
       AND NEW.igic IS NOT DISTINCT FROM OLD.igic AND NEW.totale = OLD.totale AND NEW.tipo = OLD.tipo
       AND NEW.stato = OLD.stato AND NEW.rettifica_di IS NOT DISTINCT FROM OLD.rettifica_di
       AND NEW.created_at = OLD.created_at AND NEW.created_by = OLD.created_by THEN
      RETURN NEW;
    END IF;
    IF OLD.fonte LIKE 'registro del 31/10 compilato da ChatGPT%'
       AND NEW.fonte IS NOT NULL AND NEW.fonte NOT LIKE 'registro del 31/10 compilato da ChatGPT%'
       AND NEW.id = OLD.id AND NEW.tipo = OLD.tipo AND NEW.rettifica_di IS NOT DISTINCT FROM OLD.rettifica_di
       AND NEW.created_at = OLD.created_at AND NEW.created_by = OLD.created_by THEN
      RETURN NEW;
    END IF;
  END IF;
  RAISE EXCEPTION 'tr_fatture_esterne_protect: una fattura verificata e'' definitiva (modificabili solo cliente_id, anomalia, note, fonte)';
END $$;
"""

UNICA = r"""
CREATE FUNCTION tpo.fn_fatture_esterne_consegna_unica() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM tpo.fatture_esterne_consegne x JOIN tpo.fatture_esterne f ON f.id = x.fattura_esterna_id
             WHERE x.consegna_id = NEW.consegna_id AND f.tipo = 'FATTURA' AND f.stato = 'EMESSA') THEN
    RAISE EXCEPTION 'tr_fatture_esterne_consegna_unica: la consegna e'' gia'' in una fattura emessa';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER tr_fatture_esterne_consegna_unica BEFORE INSERT ON tpo.fatture_esterne_consegne
FOR EACH ROW EXECUTE FUNCTION tpo.fn_fatture_esterne_consegna_unica();
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.add_column("dati_fiscali_cliente", sa.Column("prezzo_set_fattura", sa.Numeric(12, 4)), schema="tpo")
    op.create_check_constraint("ck_dati_fiscali_prezzo_set_positivo", "dati_fiscali_cliente",
                               "prezzo_set_fattura IS NULL OR prezzo_set_fattura > 0", schema="tpo")
    op.execute(PROTECT_NUOVA)
    op.drop_constraint("uq_fatture_esterne_consegne_consegna", "fatture_esterne_consegne", schema="tpo", type_="unique")
    op.create_index("ix_fatture_esterne_consegne_consegna", "fatture_esterne_consegne", ["consegna_id"], schema="tpo")
    op.execute(UNICA)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM tpo.fatture_esterne WHERE stato = 'ANNULLATA' AND tipo = 'FATTURA' "
                            "AND id IN (SELECT fattura_esterna_id FROM tpo.fatture_esterne_consegne))")).scalar_one():
        raise RuntimeError("esistono fatture annullate con consegne collegate: il downgrade perderebbe la storia dell'annullo")
    op.execute("DROP TRIGGER IF EXISTS tr_fatture_esterne_consegna_unica ON tpo.fatture_esterne_consegne")
    op.execute("DROP FUNCTION IF EXISTS tpo.fn_fatture_esterne_consegna_unica()")
    op.drop_index("ix_fatture_esterne_consegne_consegna", table_name="fatture_esterne_consegne", schema="tpo")
    op.create_unique_constraint("uq_fatture_esterne_consegne_consegna", "fatture_esterne_consegne", ["consegna_id"], schema="tpo")
    op.execute(PROTECT_VECCHIA)
    op.drop_constraint("ck_dati_fiscali_prezzo_set_positivo", "dati_fiscali_cliente", schema="tpo", type_="check")
    op.drop_column("dati_fiscali_cliente", "prezzo_set_fattura", schema="tpo")
