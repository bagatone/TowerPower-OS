# RECTIFY FATTURA AUTHORITY V1 FREEZE

## 1. Scope

Implementa `RectifyFattura` — la rettifica per singola riga di una `FATTURA`
già emessa, riservata ma non implementata da `FATTURA_AUTHORITY_FREEZE.md`
§16 (Owner Decision D7). Punto 5 della sequenza pre-gestionale
(`GESTIONALE_TPO_ROADMAP.md` §8), naturale seguito di
Pagamento/Incasso (punto 4, `FINANZE_AZIENDALI_AUTHORITY_FREEZE.md`).

## 2. Prior-art gate

- `FATTURA_AUTHORITY_FREEZE.md` §16 (Owner Decision D7, già approvata):
  una rettifica è una **nuova** FATTURA, con proprio `numero_fattura` dalla
  stessa serie annuale (§6), riferimento `rettifica_di` verso l'originale
  (mai mutato), righe non vincolate 1:1 a `RIGA_CONSEGNA`. Questo freeze
  implementa esattamente quella riserva, senza riaprirla.
- Schema attuale (`20260903_0026_fattura_emissione.py`): `tpo.fatture` ha
  già `rettifica_di` (colonna, FK, check anti-auto-riferimento) — **nessuna
  modifica richiesta lì**. `tpo.righe_fattura` ha `riga_consegna_id NOT
  NULL UNIQUE` e `quantita > 0` — **entrambi vanno allentati** per
  ospitare righe rettificative (§4).
- `AUTHORITY_REGISTRY.yaml`: nessuna voce `RIGA_FATTURA` o
  `FATTURA_RETTIFICA` esiste — nessun conflitto.
- Precedente strutturale diretto per idempotenza/reservation/audit:
  `fattura_emissione_requests` (stesso schema, nuovo scope
  `FATTURA_RETTIFICA_V1`); per la coerenza rettifica-originale:
  `fn_incassi_rettifica_coerente` (self-riferimento vietato, niente
  rettifica-di-rettifica concatenata, campo di corrispondenza verificato).

## 3. Owner Decisions (confermate)

- **D8 — Copertura**: una rettifica corregge **una o più righe
  specifiche** della fattura originale, non necessariamente l'intera
  fattura (Owner-confermato).
- **D9 — Convenzione importi**: l'operatore dichiara direttamente la
  `quantita` di rettifica (con segno, tipicamente negativa per una
  riduzione); `importo_netto`/`importo_igic` restano **writer-computed**
  come `quantita × prezzo_unitario` (stesso invariante di
  `RIGA_FATTURA` ordinaria, §11) — non c'è un secondo calcolo di
  differenza nascosto nel writer (Owner-confermato).
- **D10 — Tracciabilità riga**: ogni riga rettificativa porta un
  riferimento esplicito alla `RIGA_FATTURA` originale che corregge, non
  solo il riferimento a livello di `FATTURA` (Owner-confermato).

## 4. Modello e scelte derivate

```text
FATTURA (rettifica_di=NULL)         FATTURA (rettifica_di='2026/0001')
  └─ RIGA_FATTURA (riga_consegna_id=X)   └─ RIGA_FATTURA (rettifica_riga_fattura_id=<riga originale>)
```

- `prezzo_unitario`/`aliquota_igic` di una riga rettificativa sono
  **copiati dalla riga originale che corregge**, non ri-letti da
  `LISTINO_VARIETA` alla data di rettifica: la rettifica corregge un
  errore sulla stessa transazione già fatturata, non fattura una nuova
  vendita a prezzo corrente. Se il listino è cambiato nel frattempo, la
  rettifica non lo riflette — corregge l'importo che fu effettivamente
  dichiarato.
- `varieta_id` della riga rettificativa è anch'esso copiato dalla riga
  originale (stessa variet à, mai diversa — non si "cambia prodotto" con
  una rettifica).
- `cliente_id` della FATTURA rettificativa deve coincidere con quello
  della FATTURA originale (verificato dal writer e da un trigger di
  coerenza) — una rettifica non cambia cliente.
- La FATTURA rettificativa non copre alcuna `CONSEGNA` (nessuna riga in
  `fatture_consegne`): le sue righe non derivano da consegne, derivano da
  righe fattura originali.
- `data_emissione`/`scadenza` della FATTURA rettificativa sono
  writer-owned, calcolate esattamente come per l'emissione ordinaria
  (§11: `CURRENT_DATE` e `data_emissione + cliente.termini_pagamento_giorni`).
- Una riga fattura originale può essere referenziata da **una sola**
  rettifica (niente doppia correzione della stessa riga — se serve
  un'ulteriore correzione, si corregge la riga rettificativa già
  emessa... ma le rettifiche-di-rettifiche sono vietate, §6 — quindi in
  pratica: una riga corretta una volta è "chiusa"; un secondo errore sulla
  stessa riga richiede una rettifica della fattura rettificativa, che
  però è vietata da questo freeze. Accettato come limite noto di V1,
  coerente con lo stesso limite già accettato per RACCOLTA/INCASSO/USCITA
  CORREZIONE.).

## 5. Schema (migrazione additiva)

`tpo.righe_fattura` (ALTER, retrocompatibile — ogni riga esistente ha
`rettifica_riga_fattura_id IS NULL` e soddisfa già i vincoli allentati):

- `riga_consegna_id`: `NOT NULL` → **nullable**.
- nuova colonna `rettifica_riga_fattura_id BIGINT NULL`, FK verso
  `tpo.righe_fattura.id` (RESTRICT/RESTRICT).
- `ck_righe_fattura_quantita_positive` (`quantita > 0`) →
  `ck_righe_fattura_ordinaria_o_rettifica`:
  `(rettifica_riga_fattura_id IS NULL AND riga_consegna_id IS NOT NULL AND quantita > 0)
   OR (rettifica_riga_fattura_id IS NOT NULL AND riga_consegna_id IS NULL AND quantita <> 0)`.
- `ix_righe_fattura_rettifica_riga_fattura_id` su
  `rettifica_riga_fattura_id`.
- Trigger `fn_righe_fattura_rettifica_coerente` (constraint trigger,
  deferred), stesso pattern di `fn_incassi_rettifica_coerente`: vieta
  auto-riferimento, vieta rettifica-di-rettifica concatenata (l'originale
  referenziato non può avere a sua volta `rettifica_riga_fattura_id`
  valorizzato), verifica che `varieta_id` coincida con l'originale.
- Trigger `fn_fatture_rettifica_cliente_coerente` (constraint trigger,
  deferred) su `tpo.fatture`: quando `rettifica_di IS NOT NULL`, verifica
  che `cliente_id` coincida con quello della fattura originale.

Nuova tabella `tpo.fattura_rettifica_requests` — stesso schema di
`fattura_emissione_requests`, scope `FATTURA_RETTIFICA_V1`.

## 6. Comando applicativo

```text
RectifyFattura(
    rettifica_di: NumeroFattura,             # fattura originale
    righe: tuple[RettificaRigaFattura, ...],  # 1..N righe da correggere
    authority: RectifyFatturaAuthority(actor, reason, correlation_id, idempotency_key),
) -> RectifyFatturaResult

RettificaRigaFattura(
    posizione_originale: int,   # `posizione` della RIGA_FATTURA originale da correggere
    quantita: Decimal,          # con segno, non zero (D9)
)
```

`cliente_id`, `varieta_id`, `prezzo_unitario`, `aliquota_igic` per ogni
riga sono risolti dal writer dalla riga originale referenziata (mai input
del chiamante, §4). `numero_fattura`, `data_emissione`, `scadenza`,
`importo_netto`/`importo_igic`, `totale_netto`/`totale_igic`/`totale` sono
writer-owned (stesso schema di classificazione campi di
`FATTURA_AUTHORITY_FREEZE.md` §11).

Fallimenti tipizzati: fattura originale inesistente; posizione originale
inesistente per quella fattura; posizione originale già rettificata; la
fattura originale è essa stessa una rettifica (niente rettifica-di-rettifica,
verificato sia dal writer sia dal trigger); quantità di rettifica zero.

## 7. Idempotenza e audit

Stesso pattern di `EmitFattura` (§12-13 di `FATTURA_AUTHORITY_FREEZE.md`):
reservation table dedicata, hash del payload canonico su
(`rettifica_di`, l'insieme esatto di (`posizione_originale`, `quantita`)),
stessa transazione singola per reservation + numerazione + insert +
audit. Audit: `tpo.audit_eventi`, `entity_type='FATTURA'`,
`entity_public_id` = il nuovo `numero_fattura` della rettifica,
`operation='CORRECTION'`.

## 8. Fuori scope (deferred)

- Rettifica dell'intera fattura in un colpo solo senza specificare righe
  — non richiesta (D8): una rettifica "totale" si ottiene comunque
  specificando tutte le righe con `quantita` pari all'opposto
  dell'originale.
- Rettifica-di-rettifica (correggere una riga già rettificativa) — stesso
  limite già accettato per RACCOLTA/INCASSO/USCITA CORREZIONE.
- Qualunque guardia sul totale cumulativo (fattura in negativo dopo
  rettifiche) — nessun vincolo, stesso principio di
  `FINANZE_AZIENDALI_AUTHORITY_FREEZE.md` Owner Decision D3 (non
  richiesto qui esplicitamente ma nessun precedente lo impone).
- `PAGAMENTO`/`INCASSO`/`ALLOCAZIONE DEL PAGAMENTO` — invariati, fuori
  scope (`FATTURA_AUTHORITY_FREEZE.md` §17).
- Qualunque rappresentazione PDF/print della fattura rettificativa.

## 9. Implementazione

Dominio: nessun nuovo identifier (`NumeroFattura` già esiste e viene
riusato — la rettifica è comunque una `FATTURA`). Applicazione:
`src/tpo_core/application/fattura_rettifica/{models,ports,service,errors}.py`.
Infrastruttura: `src/tpo_core/infrastructure/postgresql/fattura_rettifica.py`
(stesso schema reserve-or-replay di `PostgreSQLFatturaEmissioneWriter`).
CLI: `fattura rettifica` (nuovo sottocomando in `cli/fattura.py` o nuovo
`cli/fattura_rettifica.py`, coerente con lo stile esistente). Test:
dominio/applicazione/CLI/integrazione PostgreSQL reale, stesso livello di
copertura di ogni altro boundary di questo progetto.
