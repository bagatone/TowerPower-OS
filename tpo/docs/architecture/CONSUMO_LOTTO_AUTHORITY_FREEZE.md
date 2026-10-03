# CONSUMO_LOTTO — Freeze (2/10/2026)

## 1. Perché

Matteo (2/10/2026): vuole una bolla di consegna per ogni CONSEGNA, con i
codici di tracciabilità di origine, e una fattura che resta un riferimento a
una o più bolle — passo necessario per rendere il sistema di fatturazione
realmente usabile. La seconda parte ("fattura = somma di bolle") è già
l'architettura reale: `EmitFattura.consegna_ids` è una tuple non vuota di
CONSEGNA, `tpo fattura emetti` non accetta mai importi liberi
(`application/fattura_emissione/models.py`). "Bolla" coincide quindi con
l'entità CONSEGNA già governata (`tpo.consegne` + `tpo.righe_consegna`,
`public_id CON-######`): non è una nuova entità commerciale da inventare, è
il documento/rendering di quella che già esiste.

Manca invece — e questo Freeze riguarda solo questo — la parte "con i
codici di tracciabilità": oggi `tpo.stock` ha chiave primaria
`(varieta_id, unita_misura)` (migrazione 20260919_0035), nessuna dimensione
di lotto. Una CONSEGNA scarica stock aggregato per VARIETÀ; non esiste
alcun collegamento tra la quantità uscita e il/i MOVIMENTO CARICO (dunque
la/le SEMINA/semine, dunque il/i codice/i `AAA-GGMM-L`) da cui è realmente
arrivata. Era già previsto e dichiarato fuori perimetro in
`RACCOLTA_AUTHORITY_FREEZE.md §12`: *"STOCK provenance, ASSEGNAZIONE,
CONSEGNA, BOLLA e FATTURA dovranno preservare le componenti di origine
`AAA-GGMM-L` senza fonderle. Una consegna aggregata può contenere più
codici, ma ogni quantità conserva la propria origine."* Questo Freeze
costruisce esattamente quel pezzo mancante: CONSUMO_LOTTO.

## 2. Owner Decisions (Matteo, 2/10/2026)

- **D1 — Criterio di consumo**: FIFO per data di carico (il MOVIMENTO
  CARICO più vecchio per quella VARIETÀ+UNITÀ si consuma per primo).
  Automatico, nessuna scelta manuale ad ogni consegna.
- **D2 — Consegne storiche già committate** (es. El Callao e Azul y Sal del
  18/9, Fatto 21): restano senza dettaglio di lotto. Nessuna bolla
  retroattiva con codici per quelle. Il meccanismo vale da ora in avanti.
- **D3 — Split su più lotti**: ammesso ed esplicito. Se una riga di
  consegna attraversa più MOVIMENTI CARICO, la bolla (quando esisterà, fase
  2) elenca ogni codice coinvolto con la sua quantità esatta — mai un solo
  codice "arrotondato".
- **D4 (implicita, coerente con D2)**: la CONSEGNA non deve mai bloccarsi
  per un gap di tracciabilità. STOCK e RIGHE_ORDINE restano l'autorità
  commerciale, invariata. Se la provenienza tracciabile disponibile non
  basta a spiegare l'intera quantità scaricata, il sistema non inventa un
  lotto e non blocca la consegna: quella parte resta semplicemente senza
  codice di origine.

## 3. Modello

Nuova tabella `tpo.consumi_lotto` (nessun `public_id`, è un dettaglio
interno di una CONSEGNA già pubblica, stesso trattamento di
`tpo.righe_consegna`):

```text
movimento_carico_id    -> tpo.movimenti_magazzino (tipo=CARICO, direzione=POSITIVO)
movimento_scarico_id   -> tpo.movimenti_magazzino (tipo=SCARICO, direzione=NEGATIVO) | NULL
tipo_consumo           -> 'CONSEGNA' (richiede movimento_scarico_id) | 'BACKFILL_STORICO' (richiede NULL)
quantita               -> numeric(20,6) > 0
```

Vincoli (trigger differito `ct_consumi_lotto_bounds`, stesso stile di
`fn_check_fulfilment_bounds` già usato per RIGHE_CONSEGNA/ORDINI):

- il CARICO referenziato deve essere davvero `tipo='CARICO'` e
  `direzione='POSITIVO'`;
- la somma dei consumi su un CARICO non può mai superare la sua quantità
  reale (non si può consumare più di quanto quel lotto abbia davvero
  portato in stock) — vale sia per consumo ordinario che per backfill;
- quando `tipo_consumo='CONSEGNA'`, lo SCARICO referenziato deve essere
  davvero `tipo='SCARICO'`/`direzione='NEGATIVO'`, stessa VARIETÀ+UNITÀ del
  CARICO, e la somma dei consumi su quello SCARICO non può superare la sua
  quantità (bound, non obbligo di spiegazione totale — coerente con D4).

Il writer (`PostgreSQLDeliveryFulfilmentWriter._consume_lots`, chiamato
dentro la stessa transazione del fulfilment, subito dopo il MOVIMENTO
SCARICO e l'aggiornamento STOCK) seleziona i CARICO disponibili per quella
VARIETÀ+UNITÀ in ordine FIFO (`FOR UPDATE` per serializzare consegne
concorrenti sulla stessa varietà, nessun lotto nuovo rischio), calcola il
residuo di ciascuno (`quantita - somma consumi già registrati`), e consuma
in ordine finché la quantità richiesta è spiegata o i CARICO finiscono.

## 4. Backfill storico (dentro la stessa migrazione 20261002_0036)

Problema reale da risolvere all'attivazione, non ignorabile: i MOVIMENTI
CARICO già esistenti in produzione (da raccolte reali già registrate) non
hanno mai avuto consumi registrati, ma una parte della loro quantità è già
stata fisicamente consegnata prima che questo meccanismo esistesse. Senza
correggerlo, il FIFO di una consegna futura potrebbe "ripescare" quantità
di un lotto vecchio che in realtà è già esaurito — producendo un codice di
tracciabilità sbagliato su una bolla NUOVA (non su una vecchia: questo è
diverso e più grave di D2).

Corretto con un calcolo puro sui dati reali già committati, zero dati
inventati: per ogni VARIETÀ+UNITÀ, la quantità totale già scaricata PRIMA
di questa migrazione viene "pre-consumata" dai CARICO più vecchi (stesso
ordine FIFO), come riga `tipo_consumo='BACKFILL_STORICO'`,
`movimento_scarico_id=NULL` — mai attribuita a una CONSEGNA specifica
(coerente con D2: nessuna bolla retroattiva), serve solo a correggere il
residuo. Eseguito dentro `upgrade()` con un blocco `DO $$ ... $$` in puro
SQL/plpgsql, verificabile riga per riga in
`migrations/versions/20261002_0036_consumo_lotto_authority.py`.

## 5. Cosa è stato toccato

- **Nuovo**: `migrations/versions/20261002_0036_consumo_lotto_authority.py`
  — tabella, vincoli, trigger, backfill.
- **Modificato**: `src/tpo_core/infrastructure/postgresql/
  delivery_fulfilment_writer.py` — aggiunto `_consume_lots`, chiamato una
  volta per riga di consegna ordinaria (non per le rettifiche commerciali,
  fuori perimetro qui). Nessuna firma pubblica cambiata: `models.py`,
  `ports.py`, `service.py`, `cli/delivery.py` sono invariati.
- **Nuovo**: 4 test in `tests/infrastructure/postgresql/
  test_delivery_fulfilment_writer.py` — FIFO sceglie il più vecchio, split
  su più lotti, assenza di CARICO non blocca la consegna, il vincolo
  differito rifiuta un sovra-consumo scritto direttamente in SQL.

## 6. Verificato, non assunto

- `tpo.movimenti_magazzino` oggi produce CARICO solo da
  `movimento carica-raccolta` (1:1 con una RACCOLTA, dunque una SEMINA,
  dunque un codice) — nessun writer crea RETTIFICA. Confermato leggendo
  `infrastructure/postgresql/movimento_carico.py` e con una ricerca vuota
  su `'RETTIFICA'` tra i writer. Se in futuro nascerà un movimento
  POSITIVO non da RACCOLTA (una vera RETTIFICA), questo meccanismo non lo
  tratterà mai come fonte tracciabile — per costruzione, FIFO seleziona
  solo `tipo='CARICO'` — e si comporterà come un gap di provenienza
  gestito da D4, non come un'invenzione.
- I test esistenti seminano `tpo.stock` direttamente senza MOVIMENTI CARICO
  (nessuna regressione: D4 garantisce che l'assenza di CARICO non blocchi
  nulla — verificato esplicitamente con un test dedicato).

## 7. Fuori perimetro (fase 2, non qui)

- Il documento bolla vero e proprio (PDF o altro) che legge
  `consumi_lotto` → `movimento_carico_id` → (quando esisterà, RACCOLTA →
  SEMINA → codice) e lo stampa per cliente/data/riga.
- Una query/report "dettaglio provenienza di una CONSEGNA" per uso
  immediato prima che esista la bolla vera.
- Qualunque esposizione CLI del dettaglio lotto (oggi `tpo delivery fulfil`
  resta silenzioso su questo, come prima).
- Un test di migrazione dedicato che simuli dati storici pre-esistenti e
  verifichi il backfill end-to-end (oggi verificato solo per lettura
  diretta del codice SQL, non con un test automatico — da aggiungere).

## 8. Prossimo passo

1. Matteo: `git diff` per rivedere le 3 modifiche, poi
   `alembic upgrade head` su un database di test/locale, poi
   `pytest tests/infrastructure/postgresql/test_delivery_fulfilment_writer.py -q`.
2. Se verde: stesso ciclo su Supabase reale (`alembic upgrade head`) —
   nessuna riga "bolla" da costruire ancora, questo è solo il fondamento.
3. Solo dopo, fase 2: documento bolla.

## 9. Addendum 3/10/2026 — D5: giacenza senza origine tracciabile

Verificato sui dati reali (script `2026-10-03_check_consumo_lotto.py`): i
CARICO storici di Afila e Cilantro sono in GRAM (933 e 408), lo STOCK in
GRAM e' congelato a 0, e la giacenza attuale e' in SET (Afila 2, Cilantro 1)
senza alcun MOVIMENTO CARICO in SET. Senza correzione, il primo CARICO in SET
futuro avrebbe fatto attribuire al suo codice consegne fisicamente servite
da quella giacenza senza origine -- un codice sbagliato su una bolla.

- **D5**: la giacenza senza CARICO e' piu' vecchia di qualsiasi CARICO futuro:
  in FIFO si consuma per prima e non viene attribuita a nessun codice (resta
  "senza origine", come D2/D4). Calcolata a runtime in `_consume_lots`:
  giacenza prima dello scarico - residuo di tutti i CARICO della VARIETA+UNITA.
- Il backfill della 0036 sui dati reali di oggi non fa nulla (nessun CARICO
  in SET): resta valido per il caso generale ma non sa distinguere giacenza
  senza origine pre-esistente; limite noto, irrilevante sul database attuale.
- Test aggiunto: `test_real_postgresql_consumo_lotto_untraced_opening_stock_is_consumed_first`.

