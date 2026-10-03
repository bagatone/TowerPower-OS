"""CONSUMO_LOTTO: unita' di tracciabilita' dei lotti (SET) invece dell'unita'
del MOVIMENTO CARICO.

Problema verificato sui dati reali (3/10/2026): i CARICO storici di Afila e
Cilantro sono in GRAM (311 g, 622 g, 204 g), ma ogni CARICO e' legato a una
RACCOLTA che e' per costruzione in SET (ck_raccolte_uom_set: 1, 2, 1, 1 SET) e
le CONSEGNE scaricano in SET. La 0036 collegava consumo e CARICO solo a parita'
di unita' del movimento, quindi quei lotti non erano mai selezionabili.

Regola introdotta: l'unita' di tracciabilita' (TU) di un CARICO e' l'unita'
della sua RACCOLTA, se il CARICO ne ha una; altrimenti l'unita' del CARICO
stesso. La capacita' di un lotto e' la quantita' della RACCOLTA (in SET), non il
peso in grammi. consumi_lotto.quantita e' sempre espressa nella TU del CARICO.
Nessun fattore di conversione e' inventato: grammi e SET della stessa RACCOLTA
sono gia' entrambi registrati.

- Il controllo di bound (fn_check_consumo_lotto_bounds) confronta consumi e
  capacita' in TU; lo SCARICO deve essere nella TU del CARICO.
- Backfill storico ricalcolato con la stessa regola: per ogni VARIETA+UNITA di
  SCARICO la quantita' storica non ancora attribuita viene pre-consumata dai
  CARICO piu' vecchi con TU uguale (FIFO), come BACKFILL_STORICO (nessuna
  CONSEGNA specifica, nessuna bolla retroattiva).
- Eventuali righe BACKFILL create dalla 0036 su CARICO con RACCOLTA in unita'
  diversa (grammi confrontati con SET) vengono rimosse prima del ricalcolo.

Rettifica di giacenza (3/10/2026, ``tpo movimento rettifica-giacenza``): uno
STOCK puo' contenere merce che fisicamente non esiste piu' (venduta o uscita
senza che l'uscita sia mai stata registrata). Non si altera lo storico: si
scrive un nuovo MOVIMENTO SCARICO con origine_tipo 'RETTIFICA_GIACENZA' e un
CONSUMO_LOTTO dello stesso tipo, cosi' il lotto non resta "disponibile" per
una bolla futura. Questa migrazione aggiunge:

- il valore 'RETTIFICA_GIACENZA' a consumo_lotto_tipo (le espressioni
  usano il cast a testo perche' un nuovo valore di enum non e' utilizzabile
  nella stessa transazione in cui viene aggiunto);
- la coerenza tipo/scarico del nuovo tipo e l'unicita' per (scarico, carico)
  (un indice parziale sul valore di enum non e' possibile: il cast non e'
  IMMUTABLE);
- il nuovo scope di idempotenza MOVIMENTO_RETTIFICA_GIACENZA_V1 sulla tabella
  di authority tpo.movimento_carico_requests.

Ordine manuale (``tpo ordine registra-manuale``): gli ORDINI MANUALI (vendite
extra, richieste fuori programma) non hanno chiave idempotente sulla tabella
ordini (il CHECK ck_ordini_tipo_creazione_metadati la vieta). Questa migrazione
aggiunge tpo.ordine_manuale_requests, tabella di reservation/idempotenza
immutabile come le altre authority, con FK 1:1 verso l'ORDINE risultante.

Revision ID: 20261003_0037
Revises: 20261002_0036
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261003_0037"
down_revision: str | Sequence[str] | None = "20261002_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BOUNDS_FUNCTION_TU = r"""
CREATE OR REPLACE FUNCTION tpo.fn_check_consumo_lotto_bounds(target_carico bigint, target_scarico bigint) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  carico_tipo tpo.movimento_type; carico_dir tpo.movimento_direction;
  carico_var bigint; carico_uom tpo.unit_of_measure; carico_qty numeric(20,6);
  carico_raccolta bigint; tu_uom tpo.unit_of_measure; capacita numeric(20,6);
  scarico_tipo tpo.movimento_type; scarico_dir tpo.movimento_direction;
  scarico_var bigint; scarico_uom tpo.unit_of_measure; scarico_qty numeric(20,6);
  carico_consumed numeric; scarico_spiegato numeric;
BEGIN
  SELECT tipo, direzione, varieta_id, unita_misura, quantita, raccolta_id
    INTO carico_tipo, carico_dir, carico_var, carico_uom, carico_qty, carico_raccolta
    FROM tpo.movimenti_magazzino WHERE id = target_carico;
  IF carico_tipo IS NULL OR carico_tipo <> 'CARICO' OR carico_dir <> 'POSITIVO' THEN
    RAISE EXCEPTION 'ct_consumi_lotto_carico_tipo violated for movimento %', target_carico;
  END IF;
  tu_uom := carico_uom;
  capacita := carico_qty;
  IF carico_raccolta IS NOT NULL THEN
    SELECT unita_misura, quantita INTO tu_uom, capacita
      FROM tpo.raccolte WHERE id = carico_raccolta;
  END IF;
  SELECT COALESCE(SUM(quantita), 0) INTO carico_consumed
    FROM tpo.consumi_lotto WHERE movimento_carico_id = target_carico;
  IF carico_consumed > capacita THEN
    RAISE EXCEPTION 'ct_consumi_lotto_carico_bounds violated for movimento %', target_carico;
  END IF;
  IF target_scarico IS NOT NULL THEN
    SELECT tipo, direzione, varieta_id, unita_misura, quantita
      INTO scarico_tipo, scarico_dir, scarico_var, scarico_uom, scarico_qty
      FROM tpo.movimenti_magazzino WHERE id = target_scarico;
    IF scarico_tipo IS NULL OR scarico_tipo <> 'SCARICO' OR scarico_dir <> 'NEGATIVO' THEN
      RAISE EXCEPTION 'ct_consumi_lotto_scarico_tipo violated for movimento %', target_scarico;
    END IF;
    IF scarico_var <> carico_var OR scarico_uom <> tu_uom THEN
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
"""

BOUNDS_FUNCTION_0036 = r"""
CREATE OR REPLACE FUNCTION tpo.fn_check_consumo_lotto_bounds(target_carico bigint, target_scarico bigint) RETURNS void LANGUAGE plpgsql AS $$
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
"""

BACKFILL_TU_SQL = r"""
DO $$
DECLARE
  rec RECORD;
  carico RECORD;
  gia numeric(20,6);
  restante numeric(20,6);
  presa numeric(20,6);
BEGIN
  DELETE FROM tpo.consumi_lotto k
   USING tpo.movimenti_magazzino m, tpo.raccolte r
   WHERE k.movimento_carico_id = m.id AND m.raccolta_id = r.id
     AND k.tipo_consumo = 'BACKFILL_STORICO'
     AND k.created_by = 'migration-20261002-0036-backfill-storico'
     AND r.unita_misura <> m.unita_misura;

  FOR rec IN
    SELECT varieta_id, unita_misura AS uom, COALESCE(SUM(quantita), 0) AS totale_scaricato
    FROM tpo.movimenti_magazzino WHERE tipo = 'SCARICO'
    GROUP BY varieta_id, unita_misura
  LOOP
    SELECT COALESCE(SUM(k.quantita), 0) INTO gia
      FROM tpo.consumi_lotto k
      JOIN tpo.movimenti_magazzino m ON m.id = k.movimento_carico_id
      LEFT JOIN tpo.raccolte r ON r.id = m.raccolta_id
     WHERE m.varieta_id = rec.varieta_id AND COALESCE(r.unita_misura, m.unita_misura) = rec.uom;
    restante := rec.totale_scaricato - gia;
    IF restante <= 0 THEN CONTINUE; END IF;
    FOR carico IN
      SELECT m.id,
             COALESCE(r.quantita, m.quantita)
               - COALESCE((SELECT SUM(k.quantita) FROM tpo.consumi_lotto k
                           WHERE k.movimento_carico_id = m.id), 0) AS residuo
      FROM tpo.movimenti_magazzino m
      LEFT JOIN tpo.raccolte r ON r.id = m.raccolta_id
      WHERE m.tipo = 'CARICO' AND m.varieta_id = rec.varieta_id
        AND COALESCE(r.unita_misura, m.unita_misura) = rec.uom
      ORDER BY m.data_movimento ASC, m.id ASC
    LOOP
      IF restante <= 0 THEN EXIT; END IF;
      CONTINUE WHEN carico.residuo <= 0;
      presa := LEAST(carico.residuo, restante);
      INSERT INTO tpo.consumi_lotto
        (movimento_carico_id, movimento_scarico_id, tipo_consumo, quantita, created_at, created_by)
      VALUES (carico.id, NULL, 'BACKFILL_STORICO', presa, now(), 'migration-20261003-0037-backfill-storico')
      ON CONFLICT (movimento_carico_id) WHERE tipo_consumo = 'BACKFILL_STORICO'
      DO UPDATE SET quantita = tpo.consumi_lotto.quantita + EXCLUDED.quantita;
      restante := restante - presa;
    END LOOP;
  END LOOP;
END;
$$;
"""


RETTIFICA_SQL = r"""
-- eventuali eventi differiti del trigger della 0036 (stessa transazione) vanno chiusi prima di ALTER TABLE
SET CONSTRAINTS tpo.ct_consumi_lotto_bounds IMMEDIATE;
ALTER TYPE tpo.consumo_lotto_tipo ADD VALUE IF NOT EXISTS 'RETTIFICA_GIACENZA';
ALTER TABLE tpo.consumi_lotto DROP CONSTRAINT ck_consumi_lotto_tipo_coerente;
ALTER TABLE tpo.consumi_lotto ADD CONSTRAINT ck_consumi_lotto_tipo_coerente CHECK (
  (tipo_consumo::text = 'CONSEGNA' AND movimento_scarico_id IS NOT NULL) OR
  (tipo_consumo::text = 'BACKFILL_STORICO' AND movimento_scarico_id IS NULL) OR
  (tipo_consumo::text = 'RETTIFICA_GIACENZA' AND movimento_scarico_id IS NOT NULL));
CREATE UNIQUE INDEX uq_consumi_lotto_scarico_carico_unico ON tpo.consumi_lotto
  (movimento_scarico_id, movimento_carico_id) WHERE movimento_scarico_id IS NOT NULL;
ALTER TABLE tpo.movimento_carico_requests DROP CONSTRAINT ck_movimento_carico_scope;
ALTER TABLE tpo.movimento_carico_requests ADD CONSTRAINT ck_movimento_carico_scope CHECK (
  operation_scope IN ('MOVIMENTO_CARICO_RACCOLTA_V1', 'MOVIMENTO_RETTIFICA_GIACENZA_V1'));
"""

ORDINE_MANUALE_SQL = r"""
CREATE TABLE tpo.ordine_manuale_requests (
  id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  idempotency_key text NOT NULL,
  canonical_payload_hash text NOT NULL,
  ordine_id bigint,
  outcome text NOT NULL,
  recorded_at timestamptz NOT NULL,
  created_by text NOT NULL,
  CONSTRAINT uq_ordine_manuale_request_key UNIQUE (idempotency_key),
  CONSTRAINT uq_ordine_manuale_request_ordine UNIQUE (ordine_id),
  CONSTRAINT fk_ordine_manuale_request_ordine FOREIGN KEY (ordine_id)
    REFERENCES tpo.ordini (id) ON UPDATE RESTRICT ON DELETE RESTRICT
    DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT ck_ordine_manuale_request_key CHECK (btrim(idempotency_key) <> ''),
  CONSTRAINT ck_ordine_manuale_request_hash CHECK (canonical_payload_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_ordine_manuale_request_outcome CHECK (
    (outcome = 'RESERVED' AND ordine_id IS NULL) OR
    (outcome = 'COMMITTED' AND ordine_id IS NOT NULL)),
  CONSTRAINT ck_ordine_manuale_request_actor CHECK (btrim(created_by) <> '')
);
CREATE FUNCTION tpo.protect_ordine_manuale_request() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF TG_OP='UPDATE' AND OLD.outcome='RESERVED' AND NEW.outcome='COMMITTED'
     AND NEW.idempotency_key=OLD.idempotency_key
     AND NEW.canonical_payload_hash=OLD.canonical_payload_hash
     AND NEW.recorded_at=OLD.recorded_at AND NEW.created_by=OLD.created_by
     AND OLD.ordine_id IS NULL AND NEW.ordine_id IS NOT NULL THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Ordine manuale request authority is immutable';
END $$;
CREATE TRIGGER protect_ordine_manuale_request
BEFORE UPDATE OR DELETE ON tpo.ordine_manuale_requests
FOR EACH ROW EXECUTE FUNCTION tpo.protect_ordine_manuale_request();
"""

ORDINE_MANUALE_DOWNGRADE_SQL = r"""
SET CONSTRAINTS tpo.fk_movimento_carico_authoritative_result, tpo.fk_ordine_manuale_request_ordine IMMEDIATE;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM tpo.ordine_manuale_requests) THEN
    RAISE EXCEPTION 'cannot downgrade: governed ORDINE MANUALE history exists';
  END IF;
END $$;
DROP TABLE tpo.ordine_manuale_requests;
DROP FUNCTION tpo.protect_ordine_manuale_request();
"""

RETTIFICA_DOWNGRADE_SQL = r"""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM tpo.consumi_lotto WHERE tipo_consumo::text = 'RETTIFICA_GIACENZA')
     OR EXISTS (SELECT 1 FROM tpo.movimento_carico_requests
                WHERE operation_scope = 'MOVIMENTO_RETTIFICA_GIACENZA_V1') THEN
    RAISE EXCEPTION 'cannot downgrade: governed RETTIFICA_GIACENZA history exists';
  END IF;
END $$;
DROP INDEX tpo.uq_consumi_lotto_scarico_carico_unico;
ALTER TABLE tpo.consumi_lotto DROP CONSTRAINT ck_consumi_lotto_tipo_coerente;
ALTER TABLE tpo.consumi_lotto ADD CONSTRAINT ck_consumi_lotto_tipo_coerente CHECK (
  (tipo_consumo = 'CONSEGNA' AND movimento_scarico_id IS NOT NULL) OR
  (tipo_consumo = 'BACKFILL_STORICO' AND movimento_scarico_id IS NULL));
ALTER TABLE tpo.movimento_carico_requests DROP CONSTRAINT ck_movimento_carico_scope;
ALTER TABLE tpo.movimento_carico_requests ADD CONSTRAINT ck_movimento_carico_scope CHECK (
  operation_scope = 'MOVIMENTO_CARICO_RACCOLTA_V1');
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(RETTIFICA_SQL)
    op.execute(ORDINE_MANUALE_SQL)
    op.execute(BOUNDS_FUNCTION_TU)
    op.execute(BACKFILL_TU_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # Rimuove solo cio' che questa migrazione ha creato (righe di backfill
    # proprie) e ripristina il controllo della 0036. Le righe BACKFILL
    # incrementate via ON CONFLICT su righe della 0036 non esistono nei dati
    # reali (la tabella era vuota); se esistessero resterebbero invariate.
    # Il valore di enum 'RETTIFICA_GIACENZA' non e' rimovibile da PostgreSQL e
    # resta (inutilizzato); il downgrade rifiuta se esiste storico di rettifiche.
    op.execute(ORDINE_MANUALE_DOWNGRADE_SQL)
    op.execute(RETTIFICA_DOWNGRADE_SQL)
    op.execute(
        "DELETE FROM tpo.consumi_lotto WHERE tipo_consumo = 'BACKFILL_STORICO' "
        "AND created_by = 'migration-20261003-0037-backfill-storico'"
    )
    op.execute(BOUNDS_FUNCTION_0036)
