"""RIGA_ORDINE: rinuncia al residuo di una riga mai consegnata (20/10/2026, richiesta di Matteo).

Revision ID: 20261020_0039
Revises: 20261010_0038

Un ordine PARZIALMENTE_EVASO il cui residuo non e' piu' dovuto si chiudeva abbassando la quantita' ordinata a quella
consegnata (``order_residual_closure``). Per una riga MAI consegnata la quantita' non puo' diventare 0
(``ck_righe_ordine_quantita_positive``) e le letture del dominio pretendono quantita' positive: l'ordine restava
bloccato (es. Bahia Real: segnaposto di Rabano mai dovuto).

Soluzione piu' piccola e senza perdita di informazione: la quantita' ordinata NON cambia; si aggiunge
``righe_ordine.quantita_rinunciata`` = parte del residuo dichiarata non piu' dovuta. Una riga e' "completa" quando
consegnato + rinunciato = ordinato. Cambia solo ``fn_check_ordine_fulfilment_state`` (stessa semantica di prima con
rinunciata = 0, quindi nulla cambia per gli ordini esistenti). Le letture di domanda considerano solo APERTO e
PARZIALMENTE_EVASO, quindi un ordine EVASO con una riga rinunciata non genera nessuna domanda.

Il downgrade rifiuta se esiste una rinuncia registrata (non si perde l'informazione).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261020_0039"
down_revision: str | Sequence[str] | None = "20261010_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SCHEMA = "tpo"

FUNCTION_NEW = r"""
CREATE OR REPLACE FUNCTION tpo.fn_check_ordine_fulfilment_state(target_order bigint) RETURNS void LANGUAGE plpgsql AS $$
DECLARE actual tpo.ordine_state; line_count bigint; zero_count bigint; full_count bigint;
BEGIN
  SELECT stato INTO actual FROM tpo.ordini WHERE id=target_order;
  IF NOT FOUND THEN RETURN; END IF;
  SELECT count(*), count(*) FILTER (WHERE delivered=0 AND waived=0),
         count(*) FILTER (WHERE delivered+waived=ordered)
    INTO line_count, zero_count, full_count
  FROM (
    SELECT ro.quantita ordered, ro.quantita_rinunciata waived,
           COALESCE(sum(rc.quantita) FILTER (WHERE c.stato='CONSEGNATA'),0) delivered
    FROM tpo.righe_ordine ro LEFT JOIN tpo.righe_consegna rc ON rc.riga_ordine_id=ro.id
    LEFT JOIN tpo.consegne c ON c.id=rc.consegna_id WHERE ro.ordine_id=target_order
    GROUP BY ro.id, ro.quantita, ro.quantita_rinunciata
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
"""

FUNCTION_OLD = r"""
CREATE OR REPLACE FUNCTION tpo.fn_check_ordine_fulfilment_state(target_order bigint) RETURNS void LANGUAGE plpgsql AS $$
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
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.add_column(
        "righe_ordine",
        sa.Column("quantita_rinunciata", sa.Numeric(20, 6), nullable=False, server_default="0"),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_righe_ordine_quantita_rinunciata_range", "righe_ordine",
        "quantita_rinunciata >= 0 AND quantita_rinunciata <= quantita", schema=SCHEMA,
    )
    op.execute(FUNCTION_NEW)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM tpo.righe_ordine WHERE quantita_rinunciata > 0)")).scalar_one():
        raise RuntimeError("esistono rinunce al residuo registrate: il downgrade ne perderebbe l'informazione")
    op.execute(FUNCTION_OLD)
    op.drop_constraint("ck_righe_ordine_quantita_rinunciata_range", "righe_ordine", schema=SCHEMA, type_="check")
    op.drop_column("righe_ordine", "quantita_rinunciata", schema=SCHEMA)
