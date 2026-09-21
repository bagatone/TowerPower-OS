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

## 10. Addendum V2 (19/9/2026): CARICO in SET per prodotto venduto a unità intera

Contesto reale (`handoff/scoperta-tpo-roadmap-2026-09.md`, Fatto 21-23):
per i microgreens, Tower Power vende il `SET` "ready to cut" così com'è —
non taglia, non pesa mai il prodotto finito. Il percorso GRAM di questo
freeze (V1, §1-9, Owner Decision D11/D12) resta corretto per prodotto
fisicamente tagliato/pesato (es. futura verdura da torre verticale), ma non
ha mai avuto un percorso equivalente per prodotto venduto come unità
intera — gap già esplicitamente segnalato in §2 come non coperto da alcuna
authority congelata, e qui colmato senza riaprire D11/D12.

**Owner Decision D13** (Matteo, "si, ok" su
`docs/architecture/STOCK_UNITA_VENDITA_INTERA_PROPOSTA.md`, 19/9/2026):
`movimento carica-raccolta` accetta un nuovo parametro esplicito
`--unita-misura {GRAM,SET}` (default `GRAM`, retrocompatibile con ogni
CARICO registrato finora). Non è una selezione implicita da
`protocollo_versioni.resa_unita_misura` né da alcun'altra configurazione:
è una scelta esplicita dell'operatore ad ogni CARICO, stesso principio di
trasparenza di D11 ("nessuna invenzione silenziosa").

**Owner Decision D14** (stessa approvazione): per il percorso SET,
`--quantita-pesata` non è ammesso — è un errore di comando
(`MOVIMENTO_CARICO_INPUT_INVALID`), non un default silenzioso. La quantità
caricata è esattamente `tpo.raccolte.quantita` della RACCOLTA collegata
(già vincolata a `SET` da `ck_raccolte_uom_set`, RACCOLTA_AUTHORITY_FREEZE.md
§11): "N SET raccolti" e "N SET caricati a magazzino" sono la stessa unità
fisica, senza fattore di resa né nuova dichiarazione. Non introduce alcuna
Configuration "resa per Varietà" — D11 resta invariato per il percorso
GRAM, e per il percorso SET non esiste proprio la nozione di resa (nessuna
trasformazione fisica tra raccolta e carico).

Invariante fisico non toccato: `tpo.stock.varieta_id` resta PRIMARY KEY —
una VARIETA ha una sola unità di misura di stock, per sempre (mai GRAM e
SET insieme sulla stessa VARIETA). Il guardrail di stock-unit-mismatch
(§6, `MovimentoCaricoStockUnitMismatchError`) si applica identico nelle due
direzioni: un CARICO GRAM contro uno stock già SET fallisce, e viceversa.

**Payload canonico esteso**: l'hash idempotente (§7) include ora anche
`unita_misura`; per il percorso SET, dove non esiste una quantità
dichiarata dall'operatore, il componente quantità del payload è la costante
`FROM_RACCOLTA` — la sensibilità del payload a `raccolta_id` è già
sufficiente a distinguere carichi diversi, dato che la quantità è derivata
deterministicamente da quella RACCOLTA.

**Migrazione dati una tantum** (fuori dal boundary applicativo, script
diretto non un comando CLI governato — nessun `rettifica` esiste per STOCK
di VARIETA, gap noto, non colmato da questo addendum): uno script
(`scripts/commissioning/2026-09-19_migrazione_stock_set_afila_cilantro.py`)
riclassifica le righe `tpo.stock` esistenti di Afila (933g GRAM → 3 SET) e
Cilantro (408g GRAM → 2 SET) — le uniche due VARIETA con CARICHI reali
registrati prima che il percorso SET esistesse (RAC-000001..4/
MOV-000001..4, Fatto 23). Tocca solo lo stato corrente di STOCK; RACCOLTE e
MOVIMENTI_MAGAZZINO storici restano invariati (la storia in GRAM di quei 4
eventi non viene riscritta, solo la proiezione corrente di STOCK). Audit:
`tpo.audit_eventi`, `entity_type='STOCK'`, `entity_public_id` = il
`VAR-*` della varietà, `operation='CORRECTION'`.

Fuori scope invariato (§8): nessun `RETTIFICA` governato per STOCK di
VARIETA viene introdotto da questo addendum (resta gap noto, colmato solo
per questa migrazione una tantum con script diretto); nessuna
riconciliazione quantitativa SET RACCOLTA ↔ SET CARICHI cumulati oltre il
guardrail già esistente (D12, invariato anche per il percorso SET: più
CARICHI SET parziali per la stessa RACCOLTA restano ammessi, senza tetto).

## 11. Addendum V3 (19/9/2026): chiave STOCK composita (varieta_id, unita_misura)

Supera l'affermazione "Invariante fisico non toccato" del §10 (Addendum
V2): `tpo.stock.varieta_id` **non è più** PRIMARY KEY da solo. Situazione
reale verificata eseguendo lo script di migrazione dati una tantum
descritto nel §10: `UPDATE tpo.stock SET unita_misura='SET' ... WHERE
varieta_id=<Afila>` è fallito con
`psycopg.errors.ForeignKeyViolation: update or delete on table "stock"
violates foreign key constraint "movimenti_magazzino_varieta_id_unita_
misura_fkey"` — i 4 MOVIMENTI_MAGAZZINO storici in GRAM (MOV-000001..4,
Fatto 23) referenziano quella riga STOCK con una foreign key
`ON UPDATE RESTRICT`, e sono immutabili per definizione (MOVIMENTO è un
evento storico, mai riscritto). Con `varieta_id` come sola PRIMARY KEY,
questo rende impossibile per sempre cambiare l'unità di misura dello STOCK
di una VARIETA che abbia anche un solo MOVIMENTO storico in un'altra
unità — non un bug dello script, un vincolo strutturale dello schema V1/V2.

**Owner Decision** (Matteo, 19/9/2026, verbatim): *"o facciamo tutto in
grammi o tutto in set, non me la sento di lasciare due varieta in grammi e
il resto in set"*. Questo supera esplicitamente anche l'"Alternativa
scartata" di `docs/architecture/STOCK_UNITA_VENDITA_INTERA_PROPOSTA.md`
(che escludeva la chiave composita proprio per evitare di toccare questa
foreign key) — la realtà operativa impone SET vivo ovunque da oggi in poi,
nessuna VARIETA permanentemente mista, anche al costo di una migrazione più
invasiva.

**Decisione tecnica**: `tpo.stock` passa da PRIMARY KEY `varieta_id` a
PRIMARY KEY composita `(varieta_id, unita_misura)`
(`migrations/versions/20260919_0035_stock_unita_composita.py`). Una
VARIETA può ora avere più righe STOCK, una per unità di misura, ma **mai
due vive contemporaneamente** (`disponibile>0`): una riga storica congelata
a `disponibile=0` (es. lo STOCK in GRAM di Afila/Cilantro dopo la
migrazione corretta, vedi sotto) non conta come "viva". Tre autorità
referenziano `tpo.stock` ed erano tutte accoppiate all'assunzione di una
sola riga per VARIETA, verificate e corrette in questo stesso giro:
`movimenti_magazzino` (foreign key già composita, nessuna modifica),
`allocazioni_stock` (Production Planning Allocations — guadagna la colonna
`stock_unita_misura`, back-fillata e resa NOT NULL, foreign key ricreata
composita), `disponibilita_commerciale`/Production Planning (lettori
applicativi, mai lo schema).

**Politica applicativa di risoluzione** (dove serve "la" riga STOCK di una
VARIETA — lettura commerciale, Production Planning): si preferisce l'unica
riga con `disponibile>0`; se questo è ambiguo (nessuna riga viva, o più di
una viva insieme — un'anomalia che non deve mai accadere in condizioni
normali) si fallisce chiuso invece di indovinare quale riga rappresenta la
disponibilità reale (`DisponibilitaCommercialeStockConflictError`,
`STOCK_RESOURCE_CONFLICT` in Production Planning input).

**`_lock_or_create_stock` ridisegnato** (§6, `movimento_carico.py`): non
rifiuta più qualunque unità diversa da quella richiesta, rifiuta solo se
un'**altra unità della stessa VARIETA è ancora viva** (`disponibile>0`).
Una riga storica congelata non blocca più un nuovo CARICO nell'unità
corrente — condizione necessaria perché Afila/Cilantro (STOCK GRAM storico
congelato) possano ricevere nuovi CARICHI in SET.

**Migrazione dati una tantum corretta** (supera la descrizione nel §10,
che presupponeva un `UPDATE ... SET unita_misura='SET'` in place, non
eseguibile): `scripts/commissioning/2026-09-19_migrazione_stock_set_afila_
cilantro.py` ora (a) azzera `disponibile` della riga GRAM esistente in
place — nessun cambio di `unita_misura`, quindi nessun conflitto di
foreign key — lasciandola per sempre come residuo storico congelato, e (b)
inserisce una nuova riga STOCK in SET con la quantità reale già nota dalle
RACCOLTE (Afila 3 SET, Cilantro 2 SET, stessi numeri del §10, nessun
fattore di resa). Va eseguita **dopo** la migrazione schema
`20260919_0035` (`migrate_to_head.sh`), mai prima. RACCOLTE e
MOVIMENTI_MAGAZZINO storici restano invariati, invariato anche rispetto al
§10. Audit: due eventi `tpo.audit_eventi` per VARIETA (`operation=
'CORRECTION'` sul congelamento GRAM, `operation='INSERT'` sulla creazione
SET), non più uno solo.

Fuori scope invariato: nessun `RETTIFICA` governato per STOCK di VARIETA
viene introdotto (resta gap noto, invariato dal §10); nessuna terza unità
di misura viva contemporaneamente non prevista da questo addendum.
