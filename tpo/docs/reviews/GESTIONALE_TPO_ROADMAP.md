# ROADMAP — Software Gestionale TPO (Tower Power Operations)

**Stato:** PROPOSTA DI PIANIFICAZIONE — non è un Freeze e non autorizza alcuna
implementazione. Va letta, corretta e approvata dall'owner prima che qualunque
fase inizi a scrivere codice.
**Tipo di documento:** analogo a `docs/reviews/PROJECT_ARCHITECTURE_REVIEW_2026.md`
— un documento di visione e sequenziamento, non una registrazione di autorità.
**Data:** 2026-09-03
**Autore:** sessione Claude, su richiesta dell'owner ("deve diventare una
parte indispensabile per TowerPower. deve essere il mio software gestionale").

## 1. Obiettivo dichiarato dall'owner

Non un'anteprima, non un cruscotto pubblico: un'applicazione di lavoro reale,
multi-utente, in rete locale, con cui l'owner e il team possano sia
consultare sia inserire/modificare dati operativi reali (semine, raccolte,
consegne, ordini — e in prospettiva il resto del dominio TPO). L'owner vuole
potersene fidare ciecamente e vuole che diventi lo strumento gestionale
quotidiano di Tower Power. Il sito pubblico (towerpower.green) verrà
collegato in un secondo momento, separatamente, a scopo di comunicazione —
non è oggetto di questa roadmap.

## 2. Cosa esiste già oggi (la fondamenta su cui si costruisce)

Questo non parte da zero. TPO ha già:

- **PostgreSQL come unica autorità runtime**, sancito da
  `POSTGRESQL_FOUNDATION_FINAL_FREEZE.md` e riaffermato ad ogni Freeze
  successivo: nessuna scrittura silenziosa altrove, nessun doppio percorso.
- **14 moduli CLI governati** (`src/tpo_core/cli/`), ciascuno collegato a un
  boundary Application/Domain/Infrastructure specifico e a un proprio
  documento di Freeze in `docs/architecture/`: onboarding, seed_lot, semente,
  semente_impiego, semina, raccolta, delivery (consegne/ordini), cliente,
  listino_varieta, fattura, production_planning, scheduling, operational,
  preflight.
- **Oltre 1350 test** automatizzati (dominio, applicazione, infrastruttura,
  integrazione PostgreSQL reale), con la stessa disciplina appena applicata a
  FATTURA: nessun boundary entra in produzione senza copertura completa e
  verifica su PostgreSQL reale.
- Un principio già scritto nel Freeze `APPLICATION_OPERATIONAL_ENTRYPOINT_FREEZE.md`:
  il contratto applicativo verso l'esterno è **provider-neutral** — esplicitamente
  pensato per essere usato, senza modifiche, da CLI, API, Scheduler, Job, Batch
  o Event Consumer. In altre parole: l'architettura attuale è già stata
  progettata prevedendo che un giorno arrivasse un adapter diverso dalla CLI.
  Il gestionale è quel giorno.
- Una prima anteprima visiva (la dashboard "Sala Operativa", con dati di
  esempio) che ha già validato un linguaggio grafico e un primo taglio di
  informazioni utili: produzione (semine/raccolte), consegne, ordini.

**Conseguenza pratica:** il gestionale non è un progetto nuovo scritto da zero.
È un nuovo *adapter* (un'interfaccia web) che si appoggia sulla stessa
Application e sullo stesso Domain già scritti, testati e in uso dalla CLI —
mai una loro reinvenzione o duplicazione. Questo è anche ciò che permette di
fidarsi: la logica di business che deciderà se una raccolta è valida, se una
consegna può cambiare stato, se un numero di fattura è coerente, resta
esattamente quella già collaudata da centinaia di test — l'app non la
riscrive, la richiama.

## 3. Il vincolo che decide la forma tecnica

Una pagina "Artifact" pubblicata online (come la dashboard di anteprima) gira
nel browser di chiunque la apra e non può collegarsi in modo sicuro a un
database di produzione privato. Un gestionale vero, multi-utente, in rete
locale, richiede invece un'applicazione a sé: un piccolo servizio che gira
sul tuo computer o su una macchina della rete locale, collegato direttamente
al database TPO, più un'interfaccia web che ci parla dalla stessa rete.
Nessuna delle due parti sarà esposta su internet in questa fase — coerente
con la tua richiesta ("non deve essere online").

## 4. Principio guida per ogni fase

Le stesse regole già in vigore per tutto il resto di TPO si applicano al
gestionale, senza eccezioni:

- **Nessuna invenzione silenziosa.** Ogni nuovo boundary (il "motore" del
  gestionale, l'identità degli utenti, ogni nuova operazione di scrittura)
  passa prima dalla ricognizione prior-art e da un documento di Freeze
  owner-approved, esattamente come `FATTURA_AUTHORITY_FREEZE.md`.
- **Un boundary alla volta.** Non si costruisce "tutto il gestionale" in un
  colpo solo: si aggiunge una funzione, la si copre di test fino allo stesso
  livello già raggiunto altrove, la rivedi, e solo allora entra in uso reale.
- **Lettura prima di scrittura.** Ogni nuova area del gestionale nasce in
  sola lettura (vedi dati reali, non può ancora modificarli) e passa alla
  scrittura solo dopo revisione esplicita.
- **Nessuna logica duplicata.** L'app non decide da sola le regole del
  business: chiama sempre l'Application già esistente, la stessa che usa la
  CLI. Se la CLI oggi impedisce di far tornare indietro una consegna già
  "CONSEGNATA", l'app rispetta lo stesso vincolo perché passa dallo stesso
  codice.
- **Tu resti il proprietario del via libera.** Come per FATTURA, il commit e
  il push restano sempre operazioni tue, dal tuo terminale.

## 5. Le fasi

### Fase 0 — Governance del nuovo boundary (prossimo passo immediato)

Prima di scrivere una sola riga di codice dell'app, prepariamo (io la bozza,
tu la revisione e l'approvazione) un documento di Freeze per il nuovo
boundary — nome di lavoro `OPERATIONAL_WEB_ADAPTER` — che risolve, come
hanno già fatto gli altri Freeze:

- quali operazioni sono esposte in lettura e quali in scrittura, boundary per
  boundary, e in che ordine;
- come si identifica ogni utente che scrive (oggi la CLI richiede sempre un
  `--identity`/`--actor` esplicito: il gestionale userà un vero login, ma il
  principio — nessuna scrittura anonima — resta identico);
- come gli esiti e gli errori dell'Application (già definiti in modo
  provider-neutral) si traducono in risposte per l'interfaccia web, senza
  inventare nuove regole di validazione lato app;
- dove gira il servizio (solo rete locale), chi vi accede e con quali
  permessi;
- come si verifica ogni nuova funzione (stesso standard: test dominio,
  applicazione, PostgreSQL reale).

Questa fase produce un documento, non codice.

### Fase 1 — Fondamenta tecniche in sola lettura

Un piccolo servizio locale che espone, in sola lettura, esattamente ciò che
oggi già puoi interrogare da riga di comando: stato delle semine e del ciclo
di produzione, raccolte, consegne, ordini. Nessuna scrittura ancora. Obiettivo
concreto: sostituire la dashboard con dati di esempio con la stessa dashboard
collegata ai dati veri, sempre aggiornata, a rischio zero perché non può
modificare nulla.

### Fase 2 — Prime scritture, a basso rischio

Una o due operazioni per volta (candidate naturali: segnare l'avanzamento di
una raccolta, aggiornare lo stato di una consegna), ciascuna portata allo
stesso livello di test già visto per FATTURA prima di essere collegata
all'interfaccia. Si parte da ciò che ha conseguenze più contenute in caso di
errore, non da fatture o pagamenti.

### Fase 3 — Identità e permessi per il team

Un vero sistema di accesso (login) per te e per le persone del team che
useranno l'app in rete locale, così che ogni inserimento/modifica porti con
sé in modo tracciabile chi l'ha fatto — lo stesso principio di responsabilità
già richiesto oggi da ogni comando CLI, reso comodo per un'interfaccia
condivisa.

### Fase 4 — Copertura progressiva del resto del dominio

Boundary dopo boundary, tutto ciò che oggi è raggiungibile da CLI
(clienti, listino varietà, semente, fatture, pianificazione produzione...)
diventa raggiungibile anche dall'app, mantenendo sempre la sequenza:
ricognizione → Freeze di boundary → implementazione → test completi →
revisione tua → attivazione. Le aree più delicate (fatture, e in futuro
pagamenti/incassi) restano per ultime e con revisione ancora più stringente.

### Fase 5 — Fuori roadmap, esplicitamente rimandata

Il collegamento con il sito pubblico towerpower.green per finalità di
comunicazione/pubblicità è un progetto distinto, con un pubblico diverso
(visitatori esterni, non il team). Non userà mai lo stesso canale di
scrittura del gestionale interno e mostrerà solo contenuti curati,
esplicitamente approvati per essere pubblici — mai una vista diretta sul
database di produzione. Ne parliamo quando questa roadmap avrà prodotto
qualcosa di stabile da mostrare.

## 6. Perché questo approccio merita la fiducia che chiedi

Non te lo prometto a parole: te lo dimostra il precedente che abbiamo appena
chiuso insieme. FATTURA V1 è arrivata in produzione solo dopo domain,
application, infrastruttura, CLI e integrazione PostgreSQL reale
completamente testati, con tre round di correzioni verificate dai tuoi stessi
`pytest` fino a 1928 test passati e zero falliti, e con revisione e comando
di commit sempre nelle tue mani. Il gestionale seguirà esattamente lo stesso
percorso, boundary per boundary — è l'unico modo, in questo progetto, per
guadagnarsi il diritto di essere "indispensabile".

## 7. Prossimo passo concreto

Se questa sequenza ti convince, il passo immediato è che io prepari la bozza
del Freeze di Fase 0 (`OPERATIONAL_WEB_ADAPTER`, o il nome che preferisci),
seguendo la stessa procedura di ricognizione prior-art già vista per FATTURA,
da rivedere e approvare prima che si scriva la prima riga di codice
dell'applicazione.


## 8. Addendum — decisione owner: sequenza pre-gestionale (2026-09-03)

L'owner ha deciso di **non** avviare la Fase 0 di questa roadmap subito. Prima
si chiudono le lacune di dominio più critiche già emerse dal registro di
autorità, nell'ordine seguente (dal repository, non da questa roadmap: la
gestionale resta successiva):

1. **Correzione/annullamento** di RACCOLTA, SEMENTE, SEMENTE_IMPIEGO,
   SEED_LOT — oggi append-only senza percorso governato per correggere un
   errore di inserimento. Priorità più alta: rischio quotidiano più diretto,
   perimetro più circoscritto (si estendono boundary già esistenti e
   testati, non se ne inventano di nuovi).
2. **PRODOTTO vs Varieta** — conflitto di modellazione oggi aperto in
   ORDINE, STOCK e implicitamente nel LISTINO_VARIETA; risolverlo presto
   evita di dover rifare lavoro sui punti successivi.
3. **Governo del LISTINO_VARIETA** (prezzi) — oggi Configuration liberamente
   modificabile, senza autorizzazione né storicizzazione.
4. **PAGAMENTO/INCASSO** — il pezzo economicamente più rilevante, costruito
   dopo che Prodotto e Listino sono stabili.
5. **RectifyFattura** — naturale seguito di Pagamento/Incasso.
6. **Tracciabilità CONSEGNA → RACCOLTA** e riconciliazione STOCK /
   MOVIMENTO_MAGAZZINO — importanti ma meno urgenti per l'uso quotidiano.

Rimangono esplicitamente fuori scope, come già deciso dall'owner:
DOCUMENTO_DI_VENDITA ed elettronica (SII/Verifactu/SDI).

Ogni punto sopra segue comunque la stessa disciplina già in uso in tutto TPO:
ricognizione prior-art → bozza di Freeze di boundary → revisione e
approvazione owner → implementazione con test completi (dominio,
applicazione, PostgreSQL reale) → commit/push sempre a cura dell'owner. Le
Fasi 0-5 di questa roadmap (il software gestionale vero e proprio) restano
valide come descritte sopra e riprendono una volta chiuso questo lavoro.

**Prossimo passo concreto in corso:** ricognizione prior-art e bozza di
Freeze per la correzione/annullamento di RACCOLTA (punto 1).


## 9. Stato di avanzamento — punto 1 completato (2026-09-03)

`RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md` approvato e implementato: domain,
application, migrazione `20260903_0027`, writer PostgreSQL, CLI (`tpo raccolta
correggi`) e test a ogni livello. Suite completa verificata dall'owner con
`python -m pytest` reale: **1969 passed, 8 skipped, 0 failed**. Prossimo
punto della sequenza (§8, addendum 2026-09-03): **2. PRODOTTO vs Varieta**.


## 10. Stato di avanzamento — punto 2 chiuso, non implementato (2026-09-04)

Il punto 2 (Prodotto vs Varieta) è stato ricondotto all'owner prima di
implementare qualunque cosa: la distinzione proposta è stata giudicata non
necessaria oggi (Tower Power vende la Varietà raccolta stessa, non un bene
derivato/trasformato). Decisione registrata come `DEFERRED`, non
implementata: nessuna migrazione a Ordine, Consegna, Listino o Fattura.
Dettagli e condizione di ripresa in
`docs/architecture/PRODOTTO_AUTHORITY_FREEZE_PROPOSTA.md` e in
`AUTHORITY_REGISTRY.yaml` (concept `PRODOTTO`). Si passa al **punto 3:
governo del LISTINO_VARIETA (prezzi)**.

## 11. Stato di avanzamento — punto 3 implementato, in attesa di verifica pytest (2026-09-04)

Il punto 3 (governo del LISTINO_VARIETA) è stato progettato, approvato
dall'owner (Owner Decision D1: nessuna soglia bloccante sulle variazioni di
prezzo in V1, confermata) e implementato: comando tipizzato
`ImpostaPrezzoListinoVarieta` con `ActorId`/`reason`/`correlation_id`
obbligatori, un evento `tpo.audit_eventi` per ogni cambio prezzo (before/
after), stessa transazione atomica dell'UPSERT su `tpo.listino_varieta`.
Nessuna nuova tabella, nessuna nuova identità pubblica: LISTINO_VARIETA
resta Configuration "valore corrente", non diventa un Register a Facts.
Dettagli in `docs/architecture/LISTINO_VARIETA_GOVERNANCE_FREEZE.md` e in
`AUTHORITY_REGISTRY.yaml` (concept `LISTINO_VARIETA`, ora `PRESERVED`).
Verificato con `python -m pytest` reale dell'utente: **2007 passed, 8
skipped, 0 failed**. Punto 3 chiuso. Prossimo passo: **punto 4,
Pagamento/Incasso** (§8, addendum 2026-09-03).

## 12. Stato di avanzamento — punto 4 implementato, in attesa di verifica pytest (2026-09-04)

Il punto 4 (Pagamento/Incasso) è stato ampliato su richiesta esplicita
dell'owner ("ho bisogno anche della sezione uscite per tenere le finanze
dell'impresa") e implementato come due registri Fact paralleli: INCASSO
(pagamenti ricevuti, collegati a una FATTURA) e USCITA (pagamenti
effettuati/spese dell'impresa, con categoria e beneficiario in testo
libero — nessun registro fornitori). Entrambi append-only, con rettifica
tramite nuovo Fact collegato (stesso pattern di RACCOLTA CORREZIONE) e
idempotenza via reservation table. Nessuna guardia anti-sovrapagamento
(Owner Decision D3). Dettagli in
`docs/architecture/FINANZE_AZIENDALI_AUTHORITY_FREEZE.md` e in
`AUTHORITY_REGISTRY.yaml` (concept `INCASSO` e `USCITA`, entrambi
`PRESERVED`; `INCASSO_PAGAMENTO` resta `UNKNOWN` per ciò che rimane
davvero aperto: Allocazione del Pagamento multi-fattura e State economico
derivato). In attesa della verifica `python -m pytest` reale dell'utente
prima del commit. Se confermato, prossimo passo: **punto 5,
RectifyFattura** (§8, addendum 2026-09-03).

## 13. Diagnosi e fix dei 51 fallimenti pytest riportati sul punto 4 (2026-09-04)

Il primo run reale dell'utente su `python -m pytest` dopo l'implementazione
INCASSO/USCITA ha riportato 51 fallimenti. Diagnosi a codice (non eseguibile
qui in sandbox: Python 3.10 disponibile contro il `.venv` 3.13 del progetto,
niente PostgreSQL raggiungibile) e correzioni applicate direttamente sui
file nella cartella collegata:

1. **Causa radice (spiega la maggioranza dei fallimenti)**: le colonne
   `created_at` di `tpo.incassi` e `tpo.uscite` in
   `20260904_0028_finanze_aziendali_authority.py` erano `NOT NULL` senza
   `server_default`, mentre sia i writer applicativi sia gli insert grezzi
   nei test si affidano a `RETURNING id,created_at` senza mai valorizzare la
   colonna in scrittura — ogni INSERT falliva quindi con
   `NotNullViolation` prima ancora di raggiungere il vincolo che il test
   intendeva verificare. Fix: aggiunto `server_default=sa.func.now()` ad
   entrambe le colonne, allineandole al precedente `tpo.raccolte.created_at`
   (`20260810_0004_production_execution_prerequisites.py`).
2. **`test_finanze_aziendali_migration_contains_frozen_guards`**: i nomi dei
   vincoli `uq_incasso_recording_request_key` / `uq_uscita_recording_request_key`
   erano generati solo a runtime via f-string parametrizzata nel loop
   incasso/uscita, quindi non comparivano mai come stringa letterale nel
   sorgente della migration (a differenza del precedente RACCOLTA, che li
   scrive letterali). Fix: introdotta una mappa `RECORDING_REQUEST_KEY_NAMES`
   con i due nomi letterali, usata dal loop — stesso comportamento a runtime,
   nomi ora visibili al controllo di governance sul testo sorgente.
3. **`test_finanze_aziendali_migration_has_no_net_amount_guard`**: il
   commento esplicativo sulla Owner Decision D3 conteneva la parola
   "nonnegative" (proprio per spiegarne l'assenza), facendo scattare il
   controllo che verifica che quella parola non compaia nel sorgente. Fix:
   riformulato il commento senza usare i termini vietati.
4. **`test_incremental_commissioning_replay_preserves_existing_and_counters`**:
   il set atteso di `sequence_name` in `tpo.id_sequences` non includeva
   `INCASSO_ID`/`USCITA_ID`, seminate insieme dalla migration 20260904_0028
   come righe pre-esistenti non correlate (stesso trattamento già riservato
   a `RUN_ID`/`ORDINE_ID`). Fix: aggiunte le due voci al set atteso.
5. **Catena di revisioni hardcoded**: aggiornati tutti i riferimenti
   letterali all'head della catena Alembic (`script.get_heads()`,
   `alembic_version`, liste ordinate di revisioni) da `20260903_0027` a
   `20260904_0028` in
   `test_production_planning_migrations.py`, `test_migrations.py`,
   `test_delivery_fulfilment_migration.py`, `test_id_sequences_backfill_migration.py`,
   `test_fattura_emissione_migration.py`, `test_raccolta_migration.py`,
   `test_semina_traceability_migration.py`, `test_semina_lifecycle_migration.py`,
   `test_raccolta_correzione_migration.py` — pattern già noto da ogni
   migration precedente di questo progetto.

Tutti i file toccati compilano (`py_compile`/`compileall`) e i controlli
statici di `test_finanze_aziendali_migration.py` (frammenti attesi, assenza
dei termini vietati, precedente offline-mode) sono stati riverificati
programmaticamente contro il sorgente aggiornato. **In attesa della verifica
`python -m pytest` reale dell'utente** prima del commit — questa correzione
non è stata eseguita contro un vero PostgreSQL in questa sessione.

## 14. Punto 5 — RectifyFattura (2026-09-05)

Implementato il punto 5 della sequenza (§8): rettifica per singola riga di
una `FATTURA` già emessa, riserva di identità/numerazione fissata da
`FATTURA_AUTHORITY_FREEZE.md` §16 (Owner Decision D7) e mai prima
implementata. Freeze di riferimento:
`docs/architecture/RECTIFY_FATTURA_AUTHORITY_FREEZE.md`, approvato
dall'owner ("ok", 2026-09-05) dopo prior-art gate e tre Owner Decisions:

- **D8 — Copertura**: la rettifica corregge una o più righe specifiche
  della fattura originale, non necessariamente l'intera fattura.
- **D9 — Convenzione importi**: l'operatore dichiara direttamente la
  `quantita` di rettifica con segno; `importo_netto`/`importo_igic`
  restano writer-computed come `quantita × prezzo_unitario` /
  `× aliquota_igic/100`, stesso invariante della riga ordinaria.
- **D10 — Tracciabilità riga**: ogni riga rettificativa referenzia
  esplicitamente la `RIGA_FATTURA` originale che corregge
  (`rettifica_riga_fattura_id`), non solo la fattura a livello aggregato.

Modello: la rettifica è una **nuova** `FATTURA` (proprio `numero_fattura`
dalla stessa serie annuale, `rettifica_di` verso l'originale, `cliente_id`
vincolato uguale all'originale) le cui `RIGA_FATTURA` hanno
`riga_consegna_id NULL` e `rettifica_riga_fattura_id` valorizzato;
`prezzo_unitario`/`aliquota_igic`/`varieta_id` sono copiati dalla riga
originale (mai ri-letti da `LISTINO_VARIETA` alla data di rettifica).
Vietata la rettifica-di-rettifica (niente catene, stesso limite già
accettato per RACCOLTA/INCASSO/USCITA CORREZIONE) e la doppia correzione
della stessa riga originale.

File aggiunti/modificati:

1. **Migrazione** `migrations/versions/20260905_0029_fattura_rettifica.py`
   (`down_revision=20260904_0028`): `riga_consegna_id` reso nullable;
   nuova colonna `rettifica_riga_fattura_id` (FK self-referenziante su
   `righe_fattura`, RESTRICT/RESTRICT) con UNIQUE (una sola rettifica per
   riga originale); `ck_righe_fattura_quantita_positive` sostituito da
   `ck_righe_fattura_ordinaria_o_rettifica` (mutua esclusione riga
   ordinaria/rettificativa); nuova tabella `fattura_rettifica_requests`
   (stesso schema di `fattura_emissione_requests`, scope
   `FATTURA_RETTIFICA_V1`); due trigger deferred di coerenza
   (`fn_righe_fattura_rettifica_coerente` — anti auto-riferimento, anti
   catena, corrispondenza varietà e fattura-di-appartenenza;
   `fn_fatture_rettifica_cliente_coerente` — corrispondenza cliente);
   downgrade con guardia fail-closed se esistono già rettifiche.
2. **Applicazione** `src/tpo_core/application/fattura_rettifica/`
   (`models.py`, `ports.py`, `service.py`, `errors.py`) — stesso schema di
   classificazione campi (writer-owned vs caller-owned) di
   `fattura_emissione`; nessun nuovo identifier di dominio
   (`NumeroFattura` riusato).
3. **Infrastruttura** `src/tpo_core/infrastructure/postgresql/fattura_rettifica.py`
   — `PostgreSQLFatturaRettificaWriter`, stesso pattern reserve-or-replay
   (idempotenza) e stessa transazione singola per reservation +
   numerazione + insert + audit di `PostgreSQLFatturaEmissioneWriter`;
   `SET CONSTRAINTS ALL IMMEDIATE` prima del commit per forzare i trigger
   deferred entro il blocco `try` che li mappa a errori tipizzati.
4. **Bootstrap** `src/tpo_core/bootstrap/fattura_rettifica.py` +
   esportazione in `bootstrap/__init__.py`.
5. **CLI** nuovo sottocomando `fattura rettifica` (`cli/fattura.py`,
   `cli/main.py`) — stesso stile argparse del sottocomando `emetti`
   esistente, con `--riga POSIZIONE:QUANTITA` ripetibile.
6. **Test** (dominio/applicazione/CLI/integrazione, stesso livello di
   copertura di ogni altro boundary del progetto):
   `tests/application/test_fattura_rettifica.py`,
   `tests/cli/test_fattura_rettifica_cli.py`,
   `tests/infrastructure/postgresql/test_fattura_rettifica_writer.py`,
   `tests/infrastructure/postgresql/test_fattura_rettifica_migration.py`.
7. **Governance**: `AUTHORITY_REGISTRY.yaml` — riscritta per intero la voce
   `FATTURA` (resta `UNKNOWN / OWNER DECISION REQUIRED`, come atteso da
   `required_unresolved`: ciò che resta davvero aperto è
   PAGAMENTO/INCASSO/Allocazione del Pagamento multi-fattura, non più
   RectifyFattura); aggiunta nuova voce `RIGA_FATTURA` (`PRESERVED`,
   `conflicts`/`open_owner_decisions` vuoti). Verificato con script
   indipendente Python/yaml: 33 concetti totali, nessun `concept_id`
   duplicato, tutti i `REQUIRED_FIELDS` presenti su ogni voce, `FATTURA`
   ancora `UNKNOWN`, `RIGA_FATTURA` `PRESERVED` senza conflitti aperti.

**Correzione preventiva applicata in questo stesso passaggio** (stesso
schema di regressione già osservato al punto 4, §13.5): aggiornata la
catena Alembic hardcoded da `20260904_0028` a `20260905_0029` in
`test_delivery_fulfilment_migration.py`,
`test_id_sequences_backfill_migration.py`,
`test_fattura_emissione_migration.py`, `test_raccolta_migration.py`,
`test_semina_traceability_migration.py`,
`test_semina_lifecycle_migration.py`,
`test_raccolta_correzione_migration.py`,
`test_finanze_aziendali_migration.py`,
`test_production_planning_migrations.py`, `test_migrations.py` — prima
che l'utente eseguisse pytest, non dopo.

Tutti i file nuovi/modificati compilano (`py_compile`/`compileall`).
Nessuna esecuzione contro PostgreSQL reale è stata possibile in questa
sandbox (nessun Postgres raggiungibile, versione Python non allineata al
`.venv` del progetto) — la correttezza di trigger, fixture e comportamento
SQL non è stata verificata empiricamente. **In attesa della verifica
`python -m pytest` reale dell'utente** prima del commit.

## 15. Diagnosi e fix dei fallimenti pytest reali riportati sul punto 5 (2026-09-05)

Il primo run reale dell'utente su `python -m pytest` dopo l'implementazione
RectifyFattura ha riportato 2 fallimenti e 17 errori. Diagnosi a codice e
correzioni applicate direttamente sui file nella cartella collegata, in tre
round successivi (ogni round diagnosticato dal traceback reale incollato
dall'utente):

1. **`AUTHORITY_REGISTRY.yaml`**: la voce `FATTURA` aveva
   `identities: [NumeroFattura (value object, not a PermanentId, Owner
   Decision D1)]` — le virgole non quotate dentro la nota hanno fatto
   interpretare a YAML tre stringhe separate invece di una, e
   `test_every_current_core_public_identity_prefix_is_registered` accede a
   `identity["prefix"]` assumendo dizionari, causando `TypeError`. Fix:
   `identities: []` (corretto comunque: `NumeroFattura` non è un
   `PermanentId` con prefisso, coerente con lo stato precedente a questa
   sessione; la nota resta in `preserved_rules`).
2. **CLI `fattura rettifica`**: `_date()` in `cli/fattura.py` era condivisa
   con `emetti` e sollevava sempre `InvalidEmitFatturaCommandError`
   (`FATTURA_EMISSIONE_INPUT_INVALID`) invece di
   `InvalidRectifyFatturaCommandError` (`FATTURA_RETTIFICA_INPUT_INVALID`)
   su data non valida. Fix: `_date(value, *, error=...)` parametrizzata,
   `_run_rettifica` passa `InvalidRectifyFatturaCommandError`.
3. **Fixture non risolvibile (17 errori)**: `test_fattura_rettifica_writer.py`
   e `test_fattura_rettifica_migration.py` importavano
   `fattura_postgresql_cluster_engine`/`fattura_postgresql_engine` da
   `test_fattura_emissione_writer.py` ma non la loro dipendenza a monte
   (`migration_postgresql`, alias di `isolated_postgresql`), che pytest deve
   risolvere per nome nel namespace del modulo *richiedente* — stesso schema
   già noto (`test_production_planning_input.py`). Fix: aggiunto l'import
   mancante a entrambi i file.
4. **Collisione `public_id` nei dati di test**: `test_righe_fattura_rettifica_varieta_mismatch_is_rejected`
   e `test_fatture_rettifica_cliente_mismatch_is_rejected` inserivano una
   "varietà"/"cliente alternativo" riusando lo stesso `public_id` già
   assegnato dall'helper `_seed()` al cliente/varietà della fattura
   originale (`VAR-950004`, `CLI-950008`), violando la UNIQUE reale. Un
   primo fix (`-ALT` come suffisso) violava a sua volta il CHECK reale di
   formato (`ck_clienti_public_id_format`/`ck_varieta_public_id_format`,
   solo cifre dopo il prefisso). Fix definitivo: `VAR-999998`/`CLI-999998`
   (numerico, fuori range dagli altri identificativi del file).

Tutti i fix verificati con `py_compile`/`compileall` e infine con
**esecuzione reale** dell'utente: `python -m pytest` → 2126 passed, 8
skipped, 0 failed. Punto 5 (RectifyFattura) confermato, pronto per il
commit.

## 16. Punto 6 (perimetro scelto) — Movimento Carico da Raccolta (2026-09-05)

**Scope scelto dall'owner** (tra 4 sotto-aree emerse dal prior-art gate su
"Tracciabilità CONSEGNA → RACCOLTA e riconciliazione STOCK/MOVIMENTO_MAGAZZINO",
§8 punto 6): solo **RACCOLTA → STOCK (CARICO)**. Esplicitamente deferred, per
scelta owner: ASSEGNAZIONE_FISICA, risoluzione dello stato `CONFLICTING` di
STOCK, confine MOVIMENTO_MAGAZZINO/ARTICOLO.

**Gap non documentato individuato durante il prior-art gate**: `tpo.raccolte`
è vincolata a `unita_misura='SET'`, mentre `tpo.stock`/commerciale operano in
`GRAM`. Nessun fattore di conversione SET→GRAM esiste in alcuna authority
congelata. Risolto con due Owner Decision:

- **D11**: la quantità in GRAM è dichiarata/pesata dall'operatore al momento
  della pubblicazione del CARICO, mai calcolata dalla quantità SET della
  RACCOLTA. Nessuna Configuration di conversione introdotta.
- **D12**: una RACCOLTA può originare più CARICHI parziali nel tempo (scelta
  owner, in alternativa alla proposta "un CARICO per RACCOLTA"). Conseguenza:
  `raccolta_id` sul MOVIMENTO è solo tracciabilità/audit, mai vincolo di
  quantità; RACCOLTA_CORREZIONE (che opera solo in SET) resta indipendente
  dai CARICHI già registrati.

Freeze approvato dall'owner: `docs/architecture/MOVIMENTO_CARICO_AUTHORITY_FREEZE.md`.

**Implementazione**:
- Migrazione additiva `migrations/versions/20260905_0030_movimento_carico_raccolta.py`
  — nessuna modifica a `tpo.movimenti_magazzino`/`tpo.stock`/`tpo.raccolte`
  (lo schema di `movimenti_magazzino` già prevedeva `raccolta_id` e il CHECK
  di origine `RACCOLTA` da `20260810_0004`); solo la nuova tabella di
  reservation/idempotenza `tpo.movimento_carico_requests` (scope
  `MOVIMENTO_CARICO_RACCOLTA_V1`), stesso schema di
  `tpo.raccolta_recording_requests`, trigger di protezione incluso.
- Dominio: nessun nuovo identifier; aggiunto `sequence_name = "MOVIMENTO_ID"`
  a `MovimentoId` (già commissionato in `tpo.id_sequences` da
  `20260903_0025_id_sequences_backfill.py`) per allinearlo al pattern di
  auto-allocazione già usato da `PostgreSQLRaccoltaWriter`/
  `PostgreSQLFatturaRettificaWriter`.
- Applicazione: `src/tpo_core/application/movimento_carico/{models,ports,service,errors}.py`
  — comando `RegistraCaricoMagazzino(raccolta_id, quantita_pesata, data_movimento, motivo, authority)`.
- Infrastruttura: `src/tpo_core/infrastructure/postgresql/movimento_carico.py`
  — stesso schema reserve-or-replay di `PostgreSQLRaccoltaWriter.record`, più
  lock/upsert di `tpo.stock` sul modello di `PostgreSQLDeliveryFulfilmentWriter`;
  `varieta_id` risolto internamente da `raccolta.semina_id → semina.varieta_id`,
  mai input del chiamante.
- Bootstrap (`bootstrap/movimento_carico.py`) e CLI (`cli/movimento_carico.py`,
  sottocomando `tpo movimento carica-raccolta`) aggiunti coerentemente con lo
  stile esistente.
- Test: `tests/application/test_movimento_carico.py`,
  `tests/cli/test_movimento_carico_cli.py`,
  `tests/infrastructure/postgresql/test_movimento_carico_migration.py`,
  `tests/integration/postgresql/test_movimento_carico.py` (fixture-chain:
  importa `harvest`/`harvest_environment`/`ready` da
  `test_raccolta.py`, `environment` da `test_semina_commissioning.py`,
  `isolated_postgresql` da `test_production_planning_migrations.py`).

**Fix preventivo applicato prima del run reale** (stessa regressione già
vista ai punti 4 e 5: catena Alembic hardcoded in ~10 file di test, causata
dallo spostamento dell'head da `20260905_0029` a `20260905_0030`):
`test_delivery_fulfilment_migration.py`, `test_fattura_emissione_migration.py`,
`test_finanze_aziendali_migration.py`, `test_id_sequences_backfill_migration.py`,
`test_raccolta_correzione_migration.py`, `test_raccolta_migration.py`,
`test_semina_lifecycle_migration.py`, `test_semina_traceability_migration.py`
(bump semplice dell'head atteso); `test_fattura_rettifica_migration.py` (fix
chirurgico: solo l'asserzione sull'head, non il suo `SOURCE_PATH`/
`get_revision("20260905_0029")` che referenziano legittimamente la propria
revisione); `test_production_planning_migrations.py` e `test_migrations.py`
(liste ordinate della catena: `20260905_0030` prepeso davanti a
`20260905_0029`, non sostituito, perché la revisione precedente resta un nodo
reale della catena).

**Governance**: `AUTHORITY_REGISTRY.yaml` aggiornato — `MOVIMENTO_MAGAZZINO`
(authority primaria: nuovo `current_authorities`, `core_implementations`,
`persistence_authorities`, `preserved_rules` D11/D12, `verification_tests`),
`STOCK` (cross-reference: nuova regola su come il CARICO incrementa
`disponibile`, invariati `status: CONFLICTING`/conflicts/open_owner_decisions
— non risolti da questo freeze, per scelta owner), `RACCOLTA`
(cross-reference: il boundary "Raccolta → Movimento" riservato da
`RACCOLTA_AUTHORITY_FREEZE.md` §11 è ora implementato; nota su indipendenza da
RACCOLTA_CORREZIONE). Verificato con lo stesso script indipendente delle
sessioni precedenti: 33 concetti, nessun duplicato, tutti i `REQUIRED_FIELDS`
presenti, nessun crash sul controllo `identities`/`prefix`.

Verificato con `py_compile`/`compileall` su tutto l'albero (`src`, `tests`,
`migrations`). **Non ancora verificato con `python -m pytest` reale** — in
attesa dell'esecuzione dell'utente prima del commit, come da prassi di questa
sessione.

## 17. Diagnosi e fix dei fallimenti pytest reali riportati sul punto 6 (2026-09-05)

Run reale dell'utente: **25 failed, 1898 passed, 8 skipped, 232 errors**.
Causa radice unica per l'intera cascata (quasi tutti i test PostgreSQL reali
falliscono/errano, perché tutti eseguono un upgrade Alembic a `head`):

1. **FK composita invalida in `20260905_0030_movimento_carico_raccolta.py`**:
   la FK `(movimento_id, result_public_id) -> (movimenti_magazzino.id,
   movimenti_magazzino.public_id)` falliva con
   `psycopg.errors.InvalidForeignKey: there is no unique constraint matching
   given keys for referenced table "movimenti_magazzino"`. `id` è PRIMARY KEY
   e `public_id` ha una propria UNIQUE separata, ma PostgreSQL richiede un
   vincolo UNIQUE/PK che copra esattamente l'insieme di colonne referenziato
   da una FK composita — nessuno dei due, preso da solo, basta. Lo stesso
   identico problema era già stato risolto per `RACCOLTA`
   (`20260830_0022_raccolta_authority.py` aggiunge `uq_raccolte_id_public_id`
   prima della propria FK composita), ma non era stato replicato qui. Fix:
   aggiunta `UNIQUE (id, public_id)` — `uq_movimenti_magazzino_id_public_id`
   — su `movimenti_magazzino` in `upgrade()` (con `drop_constraint`
   simmetrico in `downgrade()`), stesso precedente. Aggiornati di conseguenza
   il docstring della migrazione, `MOVIMENTO_CARICO_AUTHORITY_FREEZE.md` §5
   (che erroneamente dichiarava "nessuna modifica a movimenti_magazzino") e
   il commento/asserzioni di `test_movimento_carico_migration_touches_no_existing_table_shape`
   in `test_movimento_carico_migration.py`, con un nuovo test dedicato
   (`test_movimento_carico_migration_adds_only_the_composite_unique_constraint`)
   che verifica che l'unica modifica additiva sia esattamente questa UNIQUE
   constraint.
2. **Bug nel mio stesso fix preventivo della catena Alembic** (§16): il bulk
   replace di `test_production_planning_migrations.py` aveva sovrascritto per
   errore anche i due valori appena prepesi (`"20260905_0029"` diventato
   `"20260905_0030"` sia nella entry #2 di `revisions[:20]` sia nella entry #1
   di `revisions[:19]` dei down_revision), producendo una lista con
   `"20260905_0030"` duplicato invece della sequenza corretta
   `20260905_0030 -> 20260905_0029 -> 20260904_0028 -> ...`. Fix: ripristinati
   i valori corretti in entrambe le liste (`test_revision_chain_e_nuovo_head`).
   `test_migrations.py`, corretto manualmente voce per voce nello stesso
   passaggio, non aveva questo problema.

Verificato con `py_compile`/`compileall` su tutto l'albero. **Non ancora
verificato con un nuovo run `pytest` reale** — in attesa dell'esecuzione
dell'utente.

## 18. Secondo round di diagnosi pytest reale sul punto 6 (2026-09-05)

Run reale dell'utente dopo il fix del §17: **5 failed, 2151 passed, 8
skipped** (tutti i fallimenti residui confinati a
`tests/integration/postgresql/test_movimento_carico.py`).

**Causa radice**: `_seed_authorities` (definita in
`test_production_planning_commit_writer.py`, riusata dalla catena di fixture
`environment` -> `harvest_environment` su cui questo boundary si appoggia)
pre-semina una riga `tpo.stock` legacy per `VAR-000001` in `SET`
(`disponibile=2`), come baseline per i test di production planning —
dato di fixture condiviso, non correlato a questo boundary. I nuovi test
CARICO ereditavano quella riga pre-esistente:

- Nelle 4 tabelle "normali" (creazione, carichi parziali multipli, replay
  idempotente, conflitto idempotency key): `_lock_or_create_stock` trovava
  già una riga (in `SET`, non inserita da lui) e falliva chiuso con
  `MovimentoCaricoStockUnitMismatchError` — comportamento corretto a fronte
  di uno stock preesistente non in GRAM, ma il fixture legacy non era lo
  scenario che quei test intendevano simulare.
- In `test_rejects_stock_existing_with_non_gram_unit`: il seed manuale del
  test (un secondo INSERT `SET` per la stessa `VAR-000001`) violava la
  UNIQUE/PK di `tpo.stock` perché una riga esisteva già.

Nessun bug nel writer di produzione (`movimento_carico.py`): il comportamento
di fail-closed su unità non-GRAM è corretto by design (D11). Fix isolato
esclusivamente nel proprio file di test: la fixture `seeded_raccolta` ora
ripulisce `tpo.stock` (`DELETE FROM tpo.stock`) subito dopo aver registrato
la RACCOLTA, prima di restituire l'ambiente ai test — nessuna FK punta ancora
a `stock` a quel punto (nessun MOVIMENTO_MAGAZZINO ancora registrato), quindi
la DELETE è sicura. La funzione condivisa `_seed_authorities` non è stata
toccata (usata da molti altri test di production planning che dipendono dal
suo baseline).

Verificato con `py_compile`/`compileall`. **Non ancora verificato con un
nuovo run `pytest` reale** — in attesa dell'esecuzione dell'utente.

## 19. Terzo round di diagnosi pytest reale sul punto 6 (2026-09-05)

Run reale dell'utente dopo il fix del §18: **4 failed, 2152 passed, 8
skipped** (`test_rejects_stock_existing_with_non_gram_unit` ora verde; i 4
fallimenti residui sono le tabelle "normali" che ora arrivano fino
all'INSERT reale su `movimenti_magazzino`, con `MovimentoCaricoCommitRolledBackError`
generico — un `psycopg.Error` non-Integrity non gestito nel ramo dedicato).

**Causa radice — bug reale nello writer di produzione**
(`src/tpo_core/infrastructure/postgresql/movimento_carico.py`, INSERT su
`tpo.movimenti_magazzino`): la lista colonne includeva `created_at` come
colonna esplicita (13 colonne, 9 placeholder), ma la tupla di parametri ne
forniva solo 8 — un disallineamento che spostava
`command.authority.actor.value` (destinato a `created_by`) sul placeholder di
`created_at`, lasciando `created_by` senza alcun valore. `created_at` ha già
`server_default=sa.func.now()` nello schema e viene comunque riletto tramite
`RETURNING id,created_at` per popolare `recorded_at`: non andava mai passato
esplicitamente. Fix: rimossa la colonna `created_at` (e il suo placeholder)
dalla lista/VALUES dell'INSERT, lasciando che il default del server la
popoli; `created_by` ora riceve correttamente `command.authority.actor.value`
sull'ultimo placeholder. Verificata anche l'assenza dello stesso tipo di
disallineamento in tutte le altre query dello stesso writer (reservation/
replay, audit, update stock, update request, update id_sequences): tutte
corrette, nessun altro caso.

Verificato con `py_compile`/`compileall`. **Non ancora verificato con un
nuovo run `pytest` reale** — in attesa dell'esecuzione dell'utente.

Verificato con **esecuzione reale** dell'utente: `python -m pytest` -> 2156
passed, 8 skipped, 0 failed. Punto 6 (perimetro RACCOLTA -> STOCK, CARICO)
confermato, pronto per il commit.

## 20. Tre boundary rimanenti implementati insieme (ASSEGNAZIONE_FISICA, STOCK
    CONFLICTING, confine MOVIMENTO_MAGAZZINO/ARTICOLO) (2026-09-05)

**Decisione owner sul sequencing**: dei tre elementi deferred dal punto 6
(§16), l'owner ha scelto di implementarli **tutti insieme in questo giro**
("Tutti insieme, un solo giro di verifica/commit alla fine",
D-sequencing), deviando dal ritmo un-boundary-alla-volta seguito fino a
qui in questa sessione — un solo run pytest reale e un solo commit al
termine dei tre.

Owner Decision aggiuntive raccolte via `AskUserQuestion` (due giri, il
secondo per riconfermare esplicitamente il vero costo tecnico di
ARTICOLO): **D-ARTICOLO-scope** ("Congela ARTICOLO come concetto distinto
ora" + "Estensione completa ora" per MOVIMENTO_MAGAZZINO/STOCK, confermata
due volte), **D-STOCK-read-model** ("STOCK resta fisico puro; PRENOTATO/
VENDIBILE derivati a sola lettura"), **D-ASSEGNAZIONE_FISICA-capacity**
("No, solo riferimento di tracciabilità" — nessun vincolo di capienza),
**D-sequencing** (di cui sopra). Chiarimento di dominio dell'owner
(non tecnico, solo di scope): ARTICOLO identifica i materiali che servono
alla catena produttiva (substrati, fertilizzante, packaging, ecc.),
VARIETA identifica i semi — le due identità restano concettualmente
distinte come già congelato.

### 20.1 ARTICOLO + estensione MOVIMENTO_MAGAZZINO/STOCK

Freeze: `docs/architecture/ARTICOLO_AUTHORITY_FREEZE.md`. Strategia a
tabella parallela per non toccare la forma esistente di `tpo.stock`/
`tpo.movimenti_magazzino` in produzione: nuova `tpo.stock_articoli`
(stessa forma di `tpo.stock`, PK `articolo_id`), `tpo.movimenti_magazzino.varieta_id`
rilassato a nullable, nuova colonna `articolo_id` nullable + FK, nuovo
CHECK `ck_movimenti_magazzino_risorsa_xor` (esattamente una tra
varieta_id/articolo_id), nuova FK composita verso `stock_articoli`. La FK
composita esistente `(varieta_id,unita_misura) -> stock(...)` non richiede
modifiche: Postgres non la verifica su righe con `varieta_id` NULL (MATCH
SIMPLE). Nessun movimento ARTICOLO può originare da RACCOLTA/CONSEGNA
(fisicamente non applicabile); CARICO/SCARICO fissano `direzione`
implicita, RETTIFICA la richiede esplicita.

Migrazione additiva: `migrations/versions/20260905_0031_articolo_authority.py`
— nuove tabelle `tpo.articoli`, `tpo.stock_articoli`,
`tpo.articolo_commissioning_requests`, `tpo.movimento_articolo_requests`;
seed `ARTICOLO_ID`/`ArticoloId`/`ART` in `tpo.id_sequences`; trigger
`protect_articolo_constitutive_authority` (Configuration: protegge solo
`denominazione`/`unita_misura`, mirror di `semente_commissioning`) più i
trigger di reservation.

Dominio: nuovo `ArticoloId` (prefix `ART`). Applicazione:
`src/tpo_core/application/articolo/` (commissioning) e
`src/tpo_core/application/movimento_articolo/` (movimento, con
`MovimentoArticoloInsufficientStockError` dedicato per SCARICO/RETTIFICA
negativa che porterebbe `stock_articoli.disponibile` sotto zero).
Infrastruttura: `src/tpo_core/infrastructure/postgresql/articolo.py`,
`.../movimento_articolo.py` (stesso schema reserve-or-replay di
`PostgreSQLMovimentoCaricoWriter`, con lock/upsert di `stock_articoli`
invece di `stock`). Bootstrap/CLI: `tpo articolo commissiona`,
`tpo movimento carica-articolo` / `scarica-articolo` / `rettifica-articolo`.
`docs/architecture/MOVIMENTI_MAGAZZINO.md` riceve un'appendice che estende
(non sostituisce) il principio "una sola VARIETÀ" a "una sola VARIETÀ o un
solo ARTICOLO".

Test: `tests/application/test_articolo.py`,
`tests/application/test_movimento_articolo.py`,
`tests/cli/test_articolo_cli.py`, `tests/cli/test_movimento_articolo_cli.py`,
`tests/infrastructure/postgresql/test_articolo_migration.py`,
`tests/integration/postgresql/test_articolo.py`,
`tests/integration/postgresql/test_movimento_articolo.py`.

### 20.2 STOCK — Disponibilità Commerciale (PRENOTATO/VENDIBILE)

Freeze: `docs/architecture/STOCK_DISPONIBILITA_COMMERCIALE_FREEZE.md`.
Risolve lo `status: CONFLICTING` di STOCK senza alcuna migrazione: PRENOTATO
e VENDIBILE sono un query/application-service a sola lettura, calcolato
on-demand da `tpo.ordini`/`tpo.righe_ordine`/`tpo.righe_consegna`, mai
scritto su `tpo.stock`. PRENOTATO(varieta_id) somma, per le righe ordine di
quella varietà con ordine `APERTO`/`PARZIALMENTE_EVASO`, `quantita -
consegnato` (il segno delle righe di rettifica consegna è già incorporato
da `ck_righe_consegna_ordinary_or_correction`, nessuna gestione speciale
necessaria), pavimentato a zero per riga. VENDIBILE = DISPONIBILE -
PRENOTATO; `integrita_allarme = vendibile < 0`, puro segnale, mai scritto.

Applicazione: `src/tpo_core/application/disponibilita_commerciale/`
(nessun errore/Authority: è una query pura, non un writer). Infrastruttura:
`src/tpo_core/infrastructure/postgresql/disponibilita_commerciale.py`
(sola lettura). Nessun comando CLI dedicato in V1 (deferred a richiesta
futura). Test: `tests/application/test_disponibilita_commerciale.py`,
`tests/integration/postgresql/test_disponibilita_commerciale.py`
(coprono APERTO/PARZIALMENTE_EVASO/EVASO/ANNULLATO, consegna parziale,
evasione totale con pavimento a zero, `vendibile < 0` senza scrittura su
`tpo.stock`, varietà sconosciuta).

### 20.3 ASSEGNAZIONE_FISICA (solo Fact di creazione)

Freeze: `docs/architecture/ASSEGNAZIONE_FISICA_AUTHORITY_FREEZE.md`. Nuovo
Register append-only e fully immutable (mirror di `raccolte`, non di
ARTICOLO che è una Configuration): lega una RACCOLTA a una RIGA_ORDINE, con
CONSEGNA opzionale. Nessuna relazione con le identità `ALL` di production
planning (concetti distinti, conflitto già registrato — nessuna FK).
Nessun vincolo di capienza/quantità imposto dal sistema
(D-ASSEGNAZIONE_FISICA-capacity): `raccolta_id`/`riga_ordine_id` sono puro
riferimento di tracciabilità, mai verificati contro somme di
`raccolte.quantita`/`righe_ordine.quantita`. Se `consegna_id` è fornito,
deve esistere e risultare collegata alla stessa `riga_ordine_id` tramite
`tpo.righe_consegna` (coerenza referenziale minima, non una nuova regola di
business). Variazione/rettifica/riallocazione/annullamento restano
deferred (stesso pattern RACCOLTA/RACCOLTA_CORREZIONE).

Gap individuato durante il prior-art gate e chiarito nel freeze:
`tpo.righe_ordine.public_id` è nullable (allocato pigramente da
`order_line_identity.py` per production planning) — una Riga Ordine senza
`public_id` già allocato non è referenziabile da un'Assegnazione Fisica.

Migrazione additiva: `migrations/versions/20260905_0032_assegnazione_fisica_authority.py`
— nuove tabelle `tpo.assegnazioni_fisiche` (FK dirette verso
`tpo.raccolte.id`/`tpo.righe_ordine.id`/`tpo.consegne.id`, quest'ultima
nullable) e `tpo.assegnazione_fisica_requests`; seed
`ASSEGNAZIONE_FISICA_ID`/`AssegnazioneFisicaId`/`ASF`; trigger
`protect_assegnazione_fisica_authority` (blocca UPDATE/DELETE
incondizionatamente, Fact pura).

Dominio: nuovo `AssegnazioneFisicaId` (prefix `ASF`); riuso di
`RigaOrdineId`/`ConsegnaId`/`RaccoltaId` già esistenti. Applicazione:
`src/tpo_core/application/assegnazione_fisica/{models,ports,service,errors}.py`.
Infrastruttura: `src/tpo_core/infrastructure/postgresql/assegnazione_fisica.py`
(stesso schema reserve-or-replay di `PostgreSQLRaccoltaWriter.record`, con
la risoluzione RACCOLTA/RIGA_ORDINE/CONSEGNA per `public_id` sul modello di
`PostgreSQLMovimentoCaricoWriter._lock_raccolta`). Bootstrap/CLI:
`tpo assegnazione registra`.

Test: `tests/application/test_assegnazione_fisica.py`,
`tests/cli/test_assegnazione_fisica_cli.py`,
`tests/infrastructure/postgresql/test_assegnazione_fisica_migration.py`,
`tests/integration/postgresql/test_assegnazione_fisica.py` (inclusi i casi
consegna assente/coerente/incoerente su un'altra riga ordine, raccolta/riga
ordine/consegna inesistenti, replay idempotente, idempotency key riusata
con payload diverso).

### 20.4 Manutenzione ricorrente catena Alembic

Stesso fix preventivo già visto ai punti precedenti, applicato due volte
in questo giro (head `20260905_0030` → `0031` per ARTICOLO, poi `0031` →
`0032` per ASSEGNAZIONE_FISICA): bump dell'head atteso in ~13 file di test
(`test_delivery_fulfilment_migration.py`, `test_fattura_emissione_migration.py`,
`test_fattura_rettifica_migration.py`, `test_finanze_aziendali_migration.py`,
`test_id_sequences_backfill_migration.py`, `test_raccolta_correzione_migration.py`,
`test_raccolta_migration.py`, `test_semina_lifecycle_migration.py`,
`test_semina_traceability_migration.py`, `test_movimento_carico_migration.py`,
`test_articolo_migration.py` — questi ultimi due con fix chirurgico: solo
l'asserzione sull'head, mai il proprio `SOURCE_PATH`/`get_revision(...)` che
referenzia legittimamente la propria revisione, inclusa l'asserzione
post-rollback in `test_real_postgresql_downgrade_blocked_once_a_request_exists`
che verifica lo stato dopo un `connection.rollback()` di un downgrade
bloccato — torna al vero head corrente, non a una revisione intermedia);
`test_migrations.py` e `test_production_planning_migrations.py` (liste
ordinate della catena, nuovo head prepeso e ultimo elemento troncato,
verificato algoritmicamente con `items_a[1:] == items_b`, mai una
sostituzione cieca di stringa — una prima passata scorretta su
`test_production_planning_migrations.py` è stata individuata e corretta
nello stesso turno prima di proseguire).

**Governance**: `docs/architecture/AUTHORITY_REGISTRY.yaml` aggiornato —
`ARTICOLO` (da `UNKNOWN / OWNER DECISION REQUIRED` a `IMPLEMENTED`),
`MOVIMENTO_MAGAZZINO` (da `PARTIALLY MIGRATED` a `IMPLEMENTED`, conflitto
ARTICOLO risolto), `STOCK` (da `CONFLICTING` a `IMPLEMENTED`),
`PRENOTAZIONE` (da `PARTIALLY MIGRATED` a `IMPLEMENTED`),
`ASSEGNAZIONE_FISICA` (da `UNKNOWN / OWNER DECISION REQUIRED` a
`IMPLEMENTED`, nessuna relazione con `PRODUCTION_PLANNING`/`ALL`).
Verificato con lo stesso script indipendente delle sessioni precedenti: 33
concetti, nessun duplicato di `concept_id`/alias, tutti i `REQUIRED_FIELDS`
presenti, nessun crash sul controllo `identities`/`prefix` (`ART`/`ASF`
correttamente registrati), tutti i path dei freeze doc referenziati
esistono su disco.

Verificato con `py_compile`/`compileall` su tutto l'albero (`src`, `tests`,
`migrations`). Verificato con `python -m pytest` reale dell'utente, in tre
round di diagnosi e fix (dettagli in §21): risultato finale **2262 passed, 8
skipped, 0 failed**. Commit registrato dall'owner: `750adc3` (precedente
head `28d8d25`), branch `sprint-4.4-production-planning`, pushato.
## 21. Sequenza pre-gestionale (§8) chiusa — verifica pytest reale, commit, e transizione a Fase 0-5 (2026-09-05)

### 21.1 Verifica pytest reale sui tre boundary del punto 6

Come da D-sequencing (§20), i tre boundary implementati insieme
(ASSEGNAZIONE_FISICA, risoluzione `CONFLICTING` di STOCK, estensione
MOVIMENTO_MAGAZZINO/ARTICOLO) sono stati verificati con un solo run
`pytest` reale dell'utente, in tre round di diagnosi/fix:

- **Round 1**: 10 failed, 2244 passed, 8 skipped, 8 errors. Cause radice
  distinte: (a) bug reale in produzione — la query PRENOTATO/VENDIBILE in
  `disponibilita_commerciale.py` non filtrava le righe consegna per
  `consegne.stato='CONSEGNATA'`, sommando anche consegne non ancora
  effettuate; (b) due controlli di governance con insiemi attesi
  hard-coded (`test_authority_registry.py`, `test_identity_commissioning.py`)
  da aggiornare a fronte di concetti/sequenze ora risolti — manutenzione
  attesa, non un difetto; (c) collisione di `public_id` tra i dati di test
  di `test_assegnazione_fisica.py` (integrazione) e i dati pre-seminati da
  fixture condivise altrove nella suite; (d) un import di fixture mancante
  (`isolated_postgresql`) in `test_movimento_articolo.py`, che pytest non
  risolve per nome se non importato esplicitamente nel modulo che lo
  richiede.
- **Round 2** (dopo i fix sopra): 1 failed, 2261 passed, 8 skipped — un
  test di `test_disponibilita_commerciale.py` costruiva un ordine in uno
  stato (`PARZIALMENTE_EVASO`) internamente incoerente con la propria
  premessa (consegna dell'intera quantità ordinata), in conflitto con il
  trigger di stato fulfilment (`ct_ordini_fulfilment_state`).
- **Round 3**: **2262 passed, 8 skipped, 0 failed** — verde completo.

Commit registrato e pushato dall'owner: `750adc3` (precedente head
`28d8d25`), branch `sprint-4.4-production-planning`.

### 21.2 Chiusura formale dei sei punti della sequenza pre-gestionale

Con questo, tutti e sei i punti dell'addendum owner del 2026-09-03 (§8)
risultano chiusi:

1. Correzione/annullamento RACCOLTA, SEMENTE, SEMENTE_IMPIEGO, SEED_LOT —
   §9.
2. PRODOTTO vs Varieta — §10 (Owner Decision: `DEFERRED`, non
   implementato per scelta esplicita dell'owner, nessuna migrazione).
3. Governo del LISTINO_VARIETA — §11.
4. PAGAMENTO/INCASSO (esteso a INCASSO + USCITA su richiesta owner) —
   §12-13.
5. RectifyFattura — §14-15.
6. Tracciabilità CONSEGNA → RACCOLTA e riconciliazione STOCK/
   MOVIMENTO_MAGAZZINO — §16-20, esteso su decisione owner a
   MOVIMENTO_CARICO, ARTICOLO, risoluzione `CONFLICTING` di STOCK e
   ASSEGNAZIONE_FISICA.

### 21.3 Decisione owner su come procedere ora

Come previsto da §8 stesso ("Le Fasi 0-5 di questa roadmap... riprendono
una volta chiuso questo lavoro") e da §5/§7, il passo successivo naturale
sarebbe Fase 0: ricognizione prior-art e bozza di Freeze di governance per
il nuovo boundary `OPERATIONAL_WEB_ADAPTER` (l'interfaccia web del
gestionale). L'owner ha scelto esplicitamente di **non** avviare quel
prior-art gate in questo giro — sarà un giro dedicato separato — e di
limitare questo giro a due cose:

- **Aggiornare la roadmap** (questo paragrafo), per fissare lo stato reale
  raggiunto e il punto di transizione verso la Fase 0.
- **Eseguire un walkthrough CLI end-to-end** su un database di
  test/isolato, per verificare visivamente che l'intera catena funzioni
  come sistema integrato (non solo boundary per boundary via test
  automatici) — copertura prevista: semina → raccolta → movimento di
  carico a stock → assegnazione fisica/consegna → fattura → incasso, oltre
  a eventuali boundary collaterali rilevanti (articolo/movimento
  magazzino, disponibilità commerciale). Esito documentato nel prossimo
  paragrafo di questa roadmap.

**Prossimo passo concreto**: walkthrough CLI end-to-end pronto in
`scripts/walkthrough/e2e_walkthrough.py` (`scripts/walkthrough/README.md`
per l'uso) — esegue l'intera catena onboarding cliente/varietà → listino
→ fatturazione cliente → SEMENTE → SEMENTE_IMPIEGO → LOTTO_SEME → SEMINA
(commissioning + transizioni) → RACCOLTA → MOVIMENTO_MAGAZZINO (carico) →
CONSEGNA → ASSEGNAZIONE_FISICA → FATTURA → INCASSO chiamando il vero
binario CLI di produzione, su un cluster PostgreSQL locale isolato e
usa-e-getta (mai il database reale), chiuso da una query di traccia
end-to-end e da una verifica di DISPONIBILITA_COMMERCIALE. In attesa
dell'esecuzione dall'utente (richiede `initdb`/`pg_ctl`/`openssl` sul
PATH del proprio terminale) e del relativo esito, da registrare nel
prossimo paragrafo di questa roadmap. La bozza di Freeze per Fase 0
(`OPERATIONAL_WEB_ADAPTER`) resta esplicitamente rimandata a un round
dedicato successivo.
## 22. Walkthrough CLI end-to-end eseguito con successo (2026-09-05)

Il walkthrough preparato al §21.3 (`scripts/walkthrough/e2e_walkthrough.py`)
e' stato eseguito dall'utente dal proprio terminale, su un cluster
PostgreSQL locale isolato e usa-e-getta, in due round.

**Primo round**: fallito a metà catena con
`SEED_LOT_COMMISSIONING_FAILED: SEED_LOT_IDENTITY_UNAVAILABLE`. Causa
reale, non uno scenario di prova invalido: `SEMINA_ID` e `LOTTO_SEME_ID`
sono identità *allocate* (il sistema assegna il progressivo, non
l'operatore) che — a differenza di `RACCOLTA_ID`, `MOVIMENTO_ID`,
`CONSEGNA_ID`, `INCASSO_ID`, `USCITA_ID`, `ARTICOLO_ID` e
`ASSEGNAZIONE_FISICA_ID`, tutte seminate direttamente dalla propria
migrazione di introduzione — richiedono un'autorizzazione esplicita, una
tantum, prima del primo uso su un database nuovo
(`IdentityRegistrationCommissioningService`, lo stesso meccanismo già
usato dalle fixture di integrazione reali, es.
`tests/integration/postgresql/test_seed_lot_commissioning.py` e
`tests/integration/postgresql/test_semina_commissioning.py`). Lo script
non lo faceva. Corretto aggiungendo il passo di commissioning per
entrambe le identità subito dopo i dati di riferimento, prima del primo
comando che le usa.

**Secondo round**: verde end-to-end. Traccia finale (query unica dal
CLIENTE all'INCASSO): RAC (5 SET) → SEM-000001 (`PRONTA_ALLA_RACCOLTA`) →
CON-000001 (`CONSEGNATA`) → fattura `2026/0001` (totale 24.08) →
INC-000001 (importo 24.08, coincidente). Verifica
DISPONIBILITA_COMMERCIALE coerente con l'esito atteso: disponibile 700
GRAM (1200 caricati − 500 consegnati), prenotato 0 (ordine `EVASO`,
escluso dalla somma), vendibile 700, nessun allarme di integrità.

**Esito**: l'intera catena TPO — onboarding, SEMENTE, SEMENTE_IMPIEGO,
LOTTO_SEME, SEMINA, RACCOLTA, MOVIMENTO_MAGAZZINO, CONSEGNA,
ASSEGNAZIONE_FISICA, FATTURA, INCASSO — funziona insieme come sistema
integrato, chiamando il vero binario CLI di produzione, non solo boundary
per boundary via test automatici. L'unico difetto reale trovato (il
commissioning mancante di due identità su database nuovo) è ora corretto
nello script; vale la pena verificare, quando si affronterà la messa in
produzione di un ambiente nuovo (non quello Supabase già in uso), che lo
stesso passo una tantum non venga dimenticato — non è un'azione da
prendere ora, solo una nota operativa per il futuro.

Con questo si chiude anche la verifica pratica richiesta insieme
all'aggiornamento della roadmap (§21): il sistema è confermato funzionante
end-to-end. Il passo successivo, quando deciderai di riprenderlo, resta
quello indicato al §21.3: la bozza di Freeze di governance per Fase 0
(`OPERATIONAL_WEB_ADAPTER`), in un round dedicato separato.
