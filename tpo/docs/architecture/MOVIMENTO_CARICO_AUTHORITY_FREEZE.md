# MOVIMENTO CARICO (RACCOLTA → STOCK) AUTHORITY V1 FREEZE

## 1. Scope

Implementa la pubblicazione governata di un carico di magazzino (MOVIMENTO
tipo `CARICO`) originato da una `RACCOLTA` reale, con il conseguente
incremento dello `STOCK` della `VARIETA` corrispondente. Sottoinsieme scelto
dall'owner del punto 6 della sequenza pre-gestionale
(`GESTIONALE_TPO_ROADMAP.md` §8): "Tracciabilità CONSEGNA → RACCOLTA e
riconciliazione STOCK/MOVIMENTO_MAGAZZINO". Restano esplicitamente fuori
scope, per scelta owner, ASSEGNAZIONE_FISICA, la risoluzione dello stato
`CONFLICTING` di STOCK e il confine MOVIMENTO_MAGAZZINO/ARTICOLO (vedi §8).

## 2. Prior-art gate

- `RACCOLTA_AUTHORITY_FREEZE.md` §11-12: registrare una RACCOLTA **non**
  modifica lo STOCK e **non** crea automaticamente un MOVIMENTO_MAGAZZINO
  nascosto; "la pubblicazione Raccolta → Movimento è una futura authority
  boundary" — è esattamente questo freeze. Il confine è già esplicitamente
  riservato, non reinterpretato.
- `STOCK.md`: lo STOCK aumenta solo tramite "processi autorizzati che
  rendono disponibile prodotto fisicamente accertato, inclusi prodotto
  realmente raccolto". `MOVIMENTI_MAGAZZINO.md`: MOVIMENTI_MAGAZZINO è
  l'unico Register autorizzato a modificare STOCK; CARICO è già uno dei tre
  tipi previsti; "Una RACCOLTA può costituire l'origine di un MOVIMENTO
  autorizzato".
- Schema attuale (`20260810_0004_production_execution_prerequisites.py`):
  `tpo.movimenti_magazzino` ha già colonna `raccolta_id` (FK verso
  `tpo.raccolte`) e `MOVIMENTO_ORIGIN_REFERENCE_CHECK` ammette già
  esplicitamente `origine_tipo='RACCOLTA' AND raccolta_id IS NOT NULL AND
  consegna_id IS NULL` — lo schema è già pronto per questa forma, nessuna
  modifica a quel CHECK è richiesta. `tpo.stock.varieta_id` è PRIMARY KEY
  (una sola riga per VARIETA, un solo `unita_misura` per riga: nessuna
  doppia rappresentazione fisica/commerciale nello stesso record).
- **Gap non coperto da alcun freeze esistente, individuato in questa
  ricognizione**: `tpo.raccolte.unita_misura` è vincolata a `'SET'`
  (`ck_raccolte_uom_set`), mentre `tpo.stock`/`tpo.consegne`/FATTURA operano
  in `GRAM`. Nessun fattore di conversione SET→GRAM esiste in alcuna
  authority congelata (`grammi_seme_per_set` in
  `risorse_seme_pianificate` è grammi di **seme in ingresso**, non resa di
  prodotto raccolto in uscita — concetto distinto). Questo freeze non lo
  introduce (Owner Decision D11).
- Precedente strutturale diretto: `PostgreSQLRaccoltaWriter.record`
  (allocazione identità via `tpo.id_sequences` con compare-and-set nella
  stessa transazione, reservation/idempotenza, audit, `SET CONSTRAINTS ALL
  IMMEDIATE`) — stesso schema riusato qui per `MovimentoId`
  (`identifier_type=MovimentoId`, prefix `MOV`, già commissionato e in uso
  da `PostgreSQLDeliveryFulfilmentWriter` per i movimenti SCARICO).
  `PostgreSQLDeliveryFulfilmentWriter._execute` per il pattern di
  aggiornamento `tpo.stock` (lock `FOR UPDATE`, upsert riga se assente,
  incremento `disponibile`, `ultimo_movimento_id`, `version`).

## 3. Owner Decisions (confermate)

- **D11 — Conversione SET→GRAM**: la quantità in GRAM che il CARICO
  aggiunge allo STOCK è **dichiarata dall'operatore al momento della
  pubblicazione** (il peso realmente accertato quel giorno), non calcolata
  dalla quantità in SET della RACCOLTA tramite alcun fattore di resa.
  Nessuna nuova Configuration "resa per Varietà" viene introdotta da questo
  freeze (Owner-confermato).
- **D12 — Molteplicità**: una stessa RACCOLTA può originare **più CARICHI
  parziali** nel tempo (Owner-confermato). Conseguenza diretta di D11: poiché
  non esiste alcuna formula SET→GRAM, non esiste alcuna quantità residua
  calcolabile in GRAM da imporre come tetto. Ogni CARICO è quindi un fatto
  fisico indipendente e autosufficiente (peso dichiarato dall'operatore);
  `raccolta_id` sul MOVIMENTO è un riferimento di **tracciabilità/audit**
  (quale evento di raccolta ha fisicamente originato quel carico), non un
  vincolo di quantità massima cumulabile. Nessun tetto, nessuna
  "quantità residua" è calcolato o imposto da questo freeze. Non essendoci
  alcun legame quantitativo, le correzioni RACCOLTA_CORREZIONE (che operano
  solo sulla quantità SET) restano del tutto indipendenti dai CARICHI già
  registrati: nessuna interazione, nessun nuovo guard richiesto tra i due
  boundary.

## 4. Modello e scelte derivate

```text
RACCOLTA (SET, fatto di produzione)
   │  riferimento di tracciabilità (non quantitativo)
   ▼
MOVIMENTO_MAGAZZINO (CARICO, GRAM, peso dichiarato dall'operatore)
   │
   ▼
STOCK.disponibile += quantità (GRAM), per la VARIETA della SEMINA della RACCOLTA
```

- `varieta_id` del movimento è risolto dal writer attraverso
  `raccolta.semina_id → semina.varieta_id` (mai input diretto del
  chiamante): la VARIETA non è un dato della RACCOLTA, è derivata dalla sua
  SEMINA, esattamente come RACCOLTA stessa la deriva oggi.
- `quantita_pesata` (GRAM) è l'unico dato quantitativo dichiarato
  dall'operatore; deve essere un `Decimal` finito strettamente positivo.
  `unita_misura` del comando è fissa a `GRAM`, non è un parametro
  selezionabile dal chiamante (coerente con l'unico `unita_misura` per riga
  di `tpo.stock`).
- Se `tpo.stock` non ha ancora una riga per quella VARIETA, il writer la
  crea contestualmente (`disponibile=0` prima dell'incremento,
  `unita_misura='GRAM'`); se la riga esiste già con un `unita_misura`
  diverso da `GRAM`, il comando fallisce chiuso (nessuna VARIETA ha oggi
  stock in un'unità diversa da GRAM, ma il vincolo resta esplicito e
  verificato, non assunto).
- Nessun vincolo sullo stato della SEMINA della RACCOLTA al momento del
  CARICO (`MOVIMENTI_MAGAZZINO.md`: "MOVIMENTI_MAGAZZINO non mantiene una
  relazione diretta con SEMINE") — il CARICO richiede solo che la RACCOLTA
  esista.
- Nessun vincolo sul fatto che la RACCOLTA sia essa stessa una correzione o
  abbia correzioni: RACCOLTA_CORREZIONE opera in SET, il CARICO in GRAM
  dichiarato indipendentemente (D12); non c'è alcuna quantità da
  riconciliare tra i due.
- `data_movimento` è dichiarata dal chiamante (coerente con il precedente
  ormai stabilito da `EmitFattura`/`RectifyFattura`: `data_emissione`
  caller-supplied nonostante la formulazione "writer-owned" dei rispettivi
  freeze — qui non c'è nemmeno quell'ambiguità, `MOVIMENTI_MAGAZZINO.md`
  richiede solo "data" tra i dati minimi obbligatori, senza specificare
  l'autorità che la calcola).
- `motivo` è obbligatorio e non vuoto (dato minimo richiesto da
  `MOVIMENTI_MAGAZZINO.md`).

## 5. Schema (migrazione additiva)

Nessuna modifica a `tpo.raccolte` o `tpo.stock`. Nessuna colonna
aggiunta/rimossa/alterata e nessun nuovo CHECK su `tpo.movimenti_magazzino`
(colonna `raccolta_id` e CHECK di origine già pronti, §2); l'unica modifica
additiva è lo stesso precedente già stabilito per `tpo.raccolte`
(`20260830_0022_raccolta_authority.py`): una `UNIQUE (id, public_id)` —
`uq_movimenti_magazzino_id_public_id` — richiesta perché la FK composita
della nuova tabella di idempotenza (sotto) referenzi `(id, public_id)`
insieme (PostgreSQL richiede un vincolo UNIQUE/PK che copra esattamente
l'insieme di colonne di una FK composita; `id` da solo e `public_id` da solo,
già esistenti separatamente, non bastano — individuato dal primo run reale
`pytest` su questo boundary).

Nuova tabella `tpo.movimento_carico_requests` — stesso schema di
`tpo.raccolta_recording_requests` (reservation/idempotenza), scope
`MOVIMENTO_CARICO_RACCOLTA_V1`: `operation_scope`, `idempotency_key`,
`canonical_payload_hash`, `movimento_id` (nullable fino al commit),
`result_public_id`, `outcome` (`RESERVED`/`COMMITTED`), `recorded_at`,
`created_by`. UNIQUE su (`operation_scope`,`idempotency_key`). Nessun altro
vincolo di unicità su `raccolta_id` (D12: molteplicità ammessa).

## 6. Comando applicativo

```text
RegistraCaricoMagazzino(
    raccolta_id: RaccoltaId,        # riferimento di tracciabilità, non quantitativo (D12)
    quantita_pesata: Decimal,       # GRAM, dichiarata dall'operatore, > 0 (D11)
    data_movimento: date,
    motivo: str,                    # obbligatorio, non vuoto
    authority: MovimentoCaricoAuthority(actor, reason, correlation_id, idempotency_key),
) -> RegistraCaricoMagazzinoResult
```

`varieta_id` è risolto dal writer dalla RACCOLTA referenziata (mai input
del chiamante, §4). `MovimentoId` (`MOV-*`) è allocato dal writer nella
stessa transazione (stesso schema di `PostgreSQLRaccoltaWriter._allocate`
su `tpo.id_sequences`, `identifier_type=MovimentoId`). `tipo='CARICO'`,
`direzione='POSITIVO'` sono fissi, non parametri del comando.

Fallimenti tipizzati: RACCOLTA inesistente; quantità non positiva o non
finita; motivo vuoto; STOCK esistente con `unita_misura` diversa da `GRAM`
per quella VARIETA; idempotency key riusata con payload differente;
conflitto di concorrenza sull'allocazione dell'identità o sull'update di
`tpo.stock`.

## 7. Idempotenza e audit

Stesso pattern di `RecordRaccolta` (`RACCOLTA_AUTHORITY_FREEZE.md` §12-13):
reservation table dedicata, hash del payload canonico su (`raccolta_id`,
`quantita_pesata`, `data_movimento`, `motivo`), stessa transazione singola
per reservation + allocazione identità + insert movimento + update stock +
audit. Audit: `tpo.audit_eventi`, `entity_type='MOVIMENTO_MAGAZZINO'`,
`entity_public_id` = il nuovo `MOV-*`, `operation='INSERT'`.

## 8. Fuori scope (deferred)

- ASSEGNAZIONE_FISICA (Raccolta-quantità → Riga Ordine) — scelta owner,
  resta `UNKNOWN / OWNER DECISION REQUIRED` nel registro.
- Risoluzione dello stato `CONFLICTING` di STOCK (fisico vs. proiezioni
  commerciali DISPONIBILE/PRENOTATO/VENDIBILE) — scelta owner, invariato.
- Confine MOVIMENTO_MAGAZZINO / inventario ARTICOLO generico — scelta
  owner, invariato.
- Qualunque fattore di resa/conversione SET→GRAM configurabile (D11: non
  introdotto).
- Qualunque tetto o riconciliazione tra quantità SET della RACCOLTA e
  quantità GRAM cumulate nei suoi CARICHI (D12: nessuna relazione
  quantitativa imposta).
- MOVIMENTO tipo `RETTIFICA` per lo STOCK — resta un futuro boundary
  distinto, non introdotto qui.
- Annullamento/reversal di un CARICO già registrato — il MOVIMENTO è
  immutabile per definizione (`MOVIMENTI_MAGAZZINO.md`); una correzione
  sarebbe un nuovo MOVIMENTO di tipo diverso, fuori scope.
- CLI per RACCOLTA/CONSEGNA esistenti — invariate.

## 9. Implementazione

Dominio: nessun nuovo identifier (`MovimentoId`, `RaccoltaId` già esistono
e vengono riusati). Applicazione:
`src/tpo_core/application/movimento_carico/{models,ports,service,errors}.py`.
Infrastruttura: `src/tpo_core/infrastructure/postgresql/movimento_carico.py`
(stesso schema reserve-or-replay di `PostgreSQLRaccoltaWriter.record`, più
lock/upsert di `tpo.stock` sul modello di
`PostgreSQLDeliveryFulfilmentWriter`). Bootstrap:
`src/tpo_core/bootstrap/movimento_carico.py`. CLI: nuovo sottocomando
(`tpo movimento carica-raccolta`, coerente con lo stile esistente). Test:
dominio/applicazione/CLI/integrazione PostgreSQL reale, stesso livello di
copertura di ogni altro boundary di questo progetto.
