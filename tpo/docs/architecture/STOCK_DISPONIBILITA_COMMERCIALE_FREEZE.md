# STOCK — DISPONIBILITÀ COMMERCIALE (PRENOTATO/VENDIBILE) V1 FREEZE

## 1. Scope

Risolve lo `status: CONFLICTING` di `STOCK` in `AUTHORITY_REGISTRY.yaml`
(conflitto: "The PRENOTATO and VENDIBILE projections are not implemented in
Core"; decisione aperta: "Freeze the authoritative commercial availability
read model"). Owner Decision: STOCK resta fisico puro esattamente come già
implementato — nessuna modifica a `tpo.stock`, nessuna nuova colonna,
nessuna nuova tabella persistita. PRENOTATO e VENDIBILE diventano un
**query/application-service a sola lettura**, calcolato on-demand da ORDINI
+ CONSEGNE, mai scritto da nessun writer.

Resta fuori scope: qualunque meccanismo di "prenotazione" come Register o
Fact persistita (`PRENOTAZIONE` in `AUTHORITY_REGISTRY.yaml` resta
`PARTIALLY MIGRATED`/logica, come già descritto in `ORDINI.md` — non viene
promossa a nulla di nuovo qui); qualunque scrittura su `tpo.stock` derivata
da questo calcolo.

## 2. Prior-art gate

- `STOCK.md`: DISPONIBILE e PRENOTATO sono concetti distinti; STOCK aumenta
  solo per processi autorizzati su prodotto fisicamente accertato; regola
  di integrità: STOCK non può andare negativo, e `DISPONIBILE < PRENOTATO`
  deve generare un allarme di integrità ("ALLARME ROSSO / PRIORITÀ
  ASSOLUTA") che **non modifica** STOCK.
- `ORDINI.md`: PRENOTAZIONE appartiene al dominio ORDINI, non è un Register
  autonomo, è "una riserva logica che non tocca lo STOCK fisico"; ciclo di
  vita ORDINE: APERTO → PARZIALMENTE EVASO → EVASO, oppure ANNULLATO.
- `ASSEGNAZIONI.md`: una Riga Ordine può avere zero/una/più Assegnazioni;
  le Assegnazioni sono tracciabilità RACCOLTA↔RIGA_ORDINE, non toccano
  STOCK/PRENOTATO — confermato indipendente da questo freeze (nessuna
  dipendenza incrociata: il calcolo di PRENOTATO qui sotto usa
  `righe_ordine`/`righe_consegna`, mai `assegnazioni_fisiche`).
- Schema esistente (`20260806_0002_order_commit_schema.py`): `righe_ordine`
  ha `ordine_id, posizione, varieta_id, quantita, unita_misura` — **nessuna
  colonna di quantità residua/evasa**. La quantità evasa va aggregata da
  `righe_consegna`.
- Schema esistente (`20260812_0009_delivery_fulfilment_schema.py`):
  `righe_consegna` ha `consegna_id, ordine_id, riga_ordine_id, posizione,
  varieta_id, quantita, unita_misura, rettifica_riga_consegna_id` — il segno
  di `quantita` include già le eventuali rettifiche
  (`ck_righe_consegna_ordinary_or_correction`: le righe ordinarie richiedono
  `quantita > 0`, le righe di correzione ammettono qualunque segno non
  nullo), quindi sommare `quantita` per `riga_ordine_id` basta, senza
  distinguere esplicitamente le correzioni.
- `AUTHORITY_REGISTRY.yaml` — `ORDINE`: stati validi confermati
  `APERTO`/`PARZIALMENTE_EVASO`/`EVASO`/`ANNULLATO` (`ordine_state` enum in
  `20260806_0002_order_commit_schema.py`). Nessun altro stato da
  considerare per l'aggregazione.

## 3. Decisioni tecniche (derivate dalla Owner Decision "read-only")

- Nessuna migrazione. Nessuna nuova tabella. Nessun nuovo comando di
  scrittura. Questo boundary aggiunge **solo un query service** in lettura.
- **PRENOTATO(varieta_id)** = somma, su tutte le `righe_ordine` di quella
  `varieta_id` i cui `ordine.stato` è `APERTO` o `PARZIALMENTE_EVASO` (mai
  `EVASO`/`ANNULLATO` — un ordine evaso non prenota più nulla, uno annullato
  non ha mai prenotato nulla di persistente), di:
  `riga_ordine.quantita − Σ(righe_consegna.quantita per quella riga)`,
  con un pavimento a zero per riga (una riga già completamente evasa non
  contribuisce un residuo negativo). Una `riga_consegna` conta come
  "consegnata" solo se la sua `CONSEGNA` ha `stato='CONSEGNATA'` -- stessa
  definizione di "delivered" già usata dai trigger di coerenza
  `fn_check_fulfilment_bounds`/`fn_check_ordine_fulfilment_state`
  (`20260812_0009_delivery_fulfilment_schema.py`); una `riga_consegna`
  collegata a una CONSEGNA non ancora `CONSEGNATA` (es. `PROGRAMMATA`) non
  riduce ancora PRENOTATO.
- **VENDIBILE(varieta_id)** = `tpo.stock.disponibile − PRENOTATO(varieta_id)`
  per quella `varieta_id` (se non esiste ancora una riga `tpo.stock` per
  quella VARIETA, `disponibile` è trattato come 0). Se negativo, il
  servizio restituisce il segnale di integrità già definito in `STOCK.md`
  ("ALLARME ROSSO") tramite il campo `integrita_allarme` **senza** scrivere
  né modificare `tpo.stock` — è una segnalazione, non una correzione
  automatica.
- Il servizio è idempotente e senza side-effect (nessuna reservation, nessun
  idempotency-key: è una query, non un comando). Nessuna cache/materializzazione
  persistita in V1 — calcolo diretto a ogni chiamata (coerente con i volumi
  di questo progetto; se in futuro servisse una vista materializzata, sarà
  una nuova Owner Decision, non implicita qui).

## 4. Modello

```text
GET DisponibilitaCommerciale(varieta_id) -> DisponibilitaCommercialeResult(
    varieta_id, unita_misura,
    disponibile: Decimal,   # da tpo.stock, invariato
    prenotato: Decimal,     # calcolato, vedi §3
    vendibile: Decimal,     # disponibile - prenotato, può essere negativo
    integrita_allarme: bool # true se vendibile < 0
)
```

Nessun comando associato: è un'unica query a sola lettura, application
service (`src/tpo_core/application/disponibilita_commerciale/`), senza
Authority/idempotency (non è un writer).

## 5. Schema

Nessuna modifica. Nessuna migrazione. Il servizio legge
`tpo.stock`, `tpo.ordini`, `tpo.righe_ordine`, `tpo.righe_consegna` così
come già esistono.

## 6. Fuori scope (deferred)

- Persistenza di PRENOTATO/VENDIBILE come tabella/colonna.
- Qualunque azione automatica sull'allarme di integrità (resta un segnale,
  non un blocco né una correzione).
- Estensione del calcolo ad ARTICOLO/`stock_articoli` (il boundary ARTICOLO
  di questo stesso giro non introduce ordini/righe ordine su ARTICOLO —
  fuori scope anche lì, si veda `ARTICOLO_AUTHORITY_FREEZE.md` §6).
- Un endpoint/CLI pubblico dedicato: in V1 il servizio è consumato
  internamente (test applicativi + eventuale uso futuro da CLI/reportistica);
  l'aggiunta di un comando CLI `tpo stock disponibilita` è deferred a
  richiesta owner futura se serve esposizione diretta.

## 7. Implementazione

`src/tpo_core/application/disponibilita_commerciale/{errors,models,ports,service}.py`
— nessun errore/Authority di scrittura (query pura). Nessuna migrazione
nuova: il servizio usa una nuova classe reader in
`src/tpo_core/infrastructure/postgresql/disponibilita_commerciale.py` (sola
lettura, nessuna transazione di scrittura, nessun lock). Test: applicativo
(validazione del value object risultato) e integrazione PostgreSQL reale
(query contro schema reale, inclusi i casi ordine
APERTO/PARZIALMENTE_EVASO/EVASO/ANNULLATO, rettifica riga consegna, e il
caso `vendibile < 0`).

Aggiornamento `AUTHORITY_REGISTRY.yaml`: `STOCK` passa da `CONFLICTING` a
`FROZEN`, coerente con lo stile già usato per gli altri concetti risolti
in questa sessione; nuova cross-reference in `ORDINE`/`PRENOTAZIONE` verso
questo freeze doc.
