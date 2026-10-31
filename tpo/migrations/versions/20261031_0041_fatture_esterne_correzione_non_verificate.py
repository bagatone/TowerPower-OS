"""REGISTRO FATTURE ESTERNE: le righe NON verificate su un documento si possono correggere (31/10/2026).

Revision ID: 20261031_0041
Revises: 20261031_0040

Il registro del 31/10 era stato compilato da ChatGPT e alcune righe non coincidono con i PDF (es. TP-2026-007: registro
53,50 EUR, documento 80,25 EUR). La 0040 rendeva definitiva ogni riga: troppo rigida per dati ancora da verificare.
Regola nuova (solo trigger, nessuna colonna): una riga la cui `fonte` comincia con "registro del 31/10 compilato da ChatGPT"
(= NON verificata) si puo' correggere in numero, data, cliente_nome, stato, imponibile, igic, totale, ma SOLO cambiando
nello stesso UPDATE la `fonte` con quella del documento che la verifica (da quel momento la riga e' definitiva come prima).
Righe gia' verificate, `tipo`, `rettifica_di`, `created_*` e i collegamenti alle consegne restano immutabili.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261031_0041"
down_revision: str | Sequence[str] | None = "20261031_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NUOVA = r"""
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
  END IF;
  RAISE EXCEPTION 'tr_fatture_esterne_protect: una fattura verificata e'' definitiva (modificabili solo cliente_id, anomalia, note, fonte)';
END $$;
"""

VECCHIA = r"""
CREATE OR REPLACE FUNCTION tpo.fn_fatture_esterne_protect() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'UPDATE'
     AND NEW.id = OLD.id AND NEW.numero = OLD.numero AND NEW.data_emissione = OLD.data_emissione
     AND NEW.cliente_nome = OLD.cliente_nome AND NEW.imponibile IS NOT DISTINCT FROM OLD.imponibile
     AND NEW.igic IS NOT DISTINCT FROM OLD.igic AND NEW.totale = OLD.totale AND NEW.tipo = OLD.tipo
     AND NEW.stato = OLD.stato AND NEW.rettifica_di IS NOT DISTINCT FROM OLD.rettifica_di
     AND NEW.created_at = OLD.created_at AND NEW.created_by = OLD.created_by THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'tr_fatture_esterne_protect: una fattura registrata e'' definitiva (modificabili solo cliente_id, anomalia, note)';
END $$;
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(NUOVA)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(VECCHIA)
