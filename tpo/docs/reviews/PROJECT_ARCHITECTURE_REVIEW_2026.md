# PROJECT ARCHITECTURE REVIEW 2026

**Stato:** PROJECT REVIEW  
**Data:** 2026-08-08  
**Repository snapshot:** `f0750eecea4eab3999cb48da4be8c7c75b10da47`  
**Metodo:** analisi statica completa del repository e suite Core locale; nessuna connessione esterna o modifica al codice.

## 1. Executive Summary

Tower Power OS possiede un Core nuovo ben separato in Domain, Application,
Infrastructure, Bootstrap e CLI. Scheduling e il percorso atomico PostgreSQL
sono implementati, integrati e coperti da una baseline di test consistente. Il
freeze finale stabilisce PostgreSQL come unica persistenza autorevole del
runtime operativo e `PostgreSQLCommitRepository` come unico writer autorevole.

La maturità architetturale del nucleo Scheduling/PostgreSQL è superiore alla
maturità del prodotto complessivo. Il percorso operativo esiste come caso d'uso
Application ed è composto dal Bootstrap, ma non dispone ancora di un entrypoint
operativo per l'utente. La CLI ufficiale espone soltanto simulazione e preflight
Google read-only. Il resto del ciclo aziendale — produzione, stock, consegne,
amministrazione, reporting, Photo Bank e UI — è prevalentemente design,
contratto o implementazione legacy separata.

Il repository conserva infatti due generazioni architetturali:

1. il Core `src/tpo_core`, governato dai freeze recenti e con PostgreSQL
   autorevole per il percorso operativo;
2. i moduli Python storici direttamente sotto `src/`, orientati a Event Engine,
   Google Sheets e operazioni manuali/legacy.

Non esiste dual-write nel grafo operativo congelato, ma la presenza di writer
Google legacy ancora invocabili e di documenti ufficiali non aggiornati genera
un rischio concreto di uso del percorso sbagliato. Il progetto non è ancora
production ready. Il verdetto complessivo è **ALPHA**: architettura del nucleo
**INTERNAL BETA**, prodotto **ALPHA**, operatività **PROTOTYPE**.

Il prossimo macro-capitolo raccomandato è **Operational Runtime / CLI Write**:
rendere il percorso PostgreSQL già congelato utilizzabile in modo esplicito,
sicuro e verificabile da un operatore, senza riaprire i contratti applicativi.

## 2. Repository Snapshot

| Elemento | Evidenza |
|---|---|
| HEAD | `f0750eecea4eab3999cb48da4be8c7c75b10da47` |
| Commit | `Freeze PostgreSQL foundation architecture` |
| Working tree iniziale | pulita |
| Codice `src/tpo_core` | 78 file Python, 6.644 righe complessive |
| Test | 61 file Python complessivi |
| Documentazione | 41 file |
| Migrazioni Alembic | 2 revisioni, più ambiente e template |
| Core locale | `969 passed in 1.09s` |
| Test PostgreSQL reali | non rieseguiti; freeze finale registra `13 passed` |
| Connessioni esterne | nessuna |

La root Git effettiva è la directory padre di `tpo`; il progetto analizzato e il
documento prodotto restano confinati a `tpo`.

## 3. Architecture Overview

### 3.1 Core corrente

```text
CLI / futuro entrypoint operativo
        ↓
Bootstrap (composition root)
        ↓
Application use cases e ports
        ↓
Domain immutabile
        ↓
Infrastructure adapters
        ├── PostgreSQL: runtime operativo autorevole
        └── Google Sheets: simulazione, compatibilità e legacy
```

Il percorso operativo congelato è:

```text
PostgreSQLVersionedProgrammaFornituraRepository
→ RunScheduling
→ SchedulingRunCompletion
→ WritePlanBuilder
→ WritePlanValidator
→ CommitRequest
→ ApplicationCommitter
→ PostgreSQLCommitRepository
→ CompletedSchedulingRun
```

Il Domain non dipende dai provider. Application dipende da Protocol strutturali.
Infrastructure implementa i contratti e Bootstrap sceglie esplicitamente il
grafo. Non esistono connessioni all'import o durante la costruzione del
container.

### 3.2 Architettura storica

I moduli direttamente sotto `src/` costituiscono un sistema precedente:
Event Engine, Source Gate, Production Planner, Resource Engine, Sheets Loader,
Sheets Writer, Stock Alarm, AGGIORNAMI e CLI dedicate. Questo sistema non è
integrato nel grafo `tpo_core` e usa ancora Google Sheets come datastore e
writer. È codice funzionante e testato, ma non appartiene al runtime
PostgreSQL congelato.

## 4. Domain Status

### 4.1 Inventario

Il Domain contiene **37 componenti di modello e contratto**, più **7 tipi di
errore**:

- 14 tipi nelle entità: `Varieta`, `Semina`, `Raccolta`, `Stock`,
  `MovimentoMagazzino`, `ProgrammaFornitura`, `RigaProgrammaFornitura`,
  `ConfigurazioneTemporale`, `TipoRicorrenza`, `Ordine`, `RigaOrdine`,
  `PrenotazioneOrdine`, `Consegna`, `RigaConsegna`;
- 10 identificativi tipizzati e il contratto `IdGenerator`;
- 9 enum di stato/tipo;
- `Quantity`, `UnitOfMeasure` e `CurrentSystemDate`.

Gli oggetti sono dataclass/value object con validazione in costruzione,
identità permanente tipizzata, quantità positive e unità esplicite, transizioni
di stato controllate e riferimento temporale esplicito.

### 4.2 Stato per area

| Area | Modello | Test | Infrastruttura/Application |
|---|---|---|---|
| VARIETÀ | implementato | forte | persistenza minima read-only per Scheduling; modello fisico completo futuro |
| PROGRAMMI | implementato, incluse ricorrenze | forte | lettura Google e lettura versionata PostgreSQL |
| ORDINI | implementato, manuale/automatico | forte | lettura PG; commit automatico PG; scrittura manuale fuori scope |
| RUN | stato nel Domain/Application | forte | persistenza PG e commit atomico |
| SEMINE | implementato | forte | nessun use case/adattatore nel nuovo Core |
| RACCOLTE | implementato | forte | nessun use case/adattatore nel nuovo Core |
| STOCK | implementato | forte | nessun use case/adattatore nel nuovo Core |
| MOVIMENTI | implementato | forte | nessun use case/adattatore nel nuovo Core |
| CONSEGNE | implementato | forte | nessun use case/adattatore nel nuovo Core |
| CLIENTI | solo `ClienteId` | indiretto | tabella minima e lookup nel commit; entità/use case assenti |

Il Domain anticipa intenzionalmente aree non ancora integrate. Non è codice
morto: rappresenta contratti già documentati, ma la sua presenza non equivale
a capacità operativa.

## 5. Application Status

Sono presenti **8 componenti applicativi eseguibili**:

1. `SchedulingEngine`;
2. `RunScheduling`;
3. `PersistentIdAllocator`;
4. `SchedulingRunService`;
5. `WritePlanBuilder`;
6. `WritePlanValidator`;
7. `ApplicationCommitter`;
8. `ExecuteSchedulingCommit`.

| Modulo | Implemented | Wired | Tested | Operational | Nota |
|---|---:|---:|---:|---:|---|
| Scheduling Engine | sì | sì | sì | sì, via simulazione e grafo PG | deterministico |
| RunScheduling | sì | sì | sì | sì | simulazione Google e lettura PG |
| Identity | sì | sì nel grafo PG | sì | sì tecnicamente | nessuna CLI autonoma |
| Run Tracking | sì | sì nel grafo PG | sì | sì tecnicamente | metodi persistenti legacy isolati dal commit atomico |
| WritePlan | sì | sì nel grafo PG | sì | sì | piano immutabile |
| WritePlan Validation | sì | sì nel grafo PG | sì | sì | snapshot PG read-only |
| Committer | sì | sì nel grafo PG | sì | sì | provider-neutral |
| Operational Scheduling | sì | sì nel grafo PG | sì | capacità tecnica | nessun entrypoint utente |

`ExecuteSchedulingCommit` è il solo orchestratore del commit Scheduling. Esso
esegue Scheduling, propone la conclusione RUN, costruisce e valida il piano,
crea la richiesta e invoca il committer. Non usa clock impliciti e rifiuta RUN
in simulazione.

## 6. Ports

Sono presenti **8 porte Application** e un contratto Domain di generazione ID:

| Porta | Implementazioni | Lettura/scrittura | Uso |
|---|---|---|---|
| `ProgrammaFornituraRepository` | Google | read | simulazione legacy |
| `VersionedProgrammaFornituraRepository` | PostgreSQL | read | runtime operativo |
| `ScheduledOrderReadRepository` | Google, PostgreSQL | read | idempotenza Scheduling |
| `OrdineRepository` | Google | read/write | legacy; non writer autorevole PG |
| `IdentifierSequenceRepository` | PostgreSQL | read/CAS | Identity operativo |
| `SchedulingRunRepository` | PostgreSQL | read/write | apertura RUN; conclusione atomica delegata al commit |
| `WritePlanValidationRepository` | PostgreSQL | read | validazione target |
| `CommitRepository` | PostgreSQL, Google legacy | prepare/commit | PG autorevole; Google compatibilità |
| `IdGenerator` | allocator PG, generator simulazione | allocazione | Domain contract |

Non risultano porte prive di un adapter nel perimetro implementato. Le porte
legacy `OrdineRepository` e `ProgrammaFornituraRepository` restano necessarie
alla simulazione Google ma non devono entrare nel grafo operativo PG.

## 7. Infrastructure

### 7.1 Conteggio adapter

Sono presenti **10 adapter di persistenza/gateway**:

- Google: gateway API, repository PROGRAMMI, repository ORDINI, commit
  repository;
- PostgreSQL: Identity, Run Tracking, Orders read-only, Versioned Program
  read-only, WritePlan Validation read-only, Commit Repository.

Settings, Connection Factory, Health Check e supporto Alembic sono servizi
infrastrutturali, non adapter di porta.

### 7.2 Qualità del confine

- dipendenze provider confinate a Infrastructure e Bootstrap;
- connessioni lazy;
- cleanup conservativo nei repository read-only;
- errori infrastrutturali dedicati;
- configurazione PG validata e segreti esclusi dalle rappresentazioni;
- nessun ORM nel Core; SQL esplicito e schema versionato;
- nessun fallback automatico o retry nascosto.

## 8. PostgreSQL

La foundation comprende configurazione, factory di connessione, health check,
Alembic, Identity, Run Tracking, lettura ORDINI, lettura PROGRAMMI versionati,
validazione del WritePlan e commit atomico.

Il commit usa una connessione e una transazione. Blocca la RUN, verifica la
versione, controlla le chiavi idempotenti, risolve CLIENTI/VARIETÀ/PROGRAMMI,
inserisce ORDINI, righe e provenance, registra audit e conclude la RUN. Un
errore produce rollback totale; la unique constraint resta la barriera finale
alla collisione concorrente.

Gli adapter `PostgreSQLOrdineRepository`,
`PostgreSQLVersionedProgrammaFornituraRepository` e
`PostgreSQLWritePlanValidationRepository` sono read-only. Le scritture di
Identity e apertura RUN sono necessarie alla preparazione del flusso; il writer
dei dati di business del commit resta soltanto `PostgreSQLCommitRepository`.

## 9. Google Legacy

| Componente | Classificazione | Nota |
|---|---|---|
| Google API gateway | A/C/F | necessario a simulazione e preflight; testato |
| Programmi repository | B/C/F | input simulazione |
| Ordini repository | B/C/F | read simulazione; metodo write legacy |
| Google Commit Repository | B/D/E/F | compatibilità testata, non costruito dal Bootstrap operativo |
| `src/sheets_writer.py` | B/D/E/F | writer della generazione precedente |
| Event/Source/Resource engine legacy | B/C/F | separati dal nuovo Core |
| AGGIORNAMI legacy | B/F | read/report operativo storico |

Il rischio split-brain non è presente nel grafo congelato, ma è possibile a
livello operativo se uno script legacy viene invocato direttamente. Non esiste
un meccanismo tecnico globale che renda ineseguibili tutti i writer storici.
La mitigazione corretta è governance/entrypoint, non il dual-write.

## 10. Bootstrap

Il container costruisce sempre il grafo Google di simulazione:

```text
GoogleApiSheetsGateway
→ GoogleSheetsProgrammaFornituraRepository
→ GoogleSheetsOrdineRepository
→ RunScheduling
```

Se viene fornita configurazione PostgreSQL, costruisce inoltre il grafo
operativo completo:

```text
PostgreSQLConnectionFactory
├── Identity + Run Tracking
├── Versioned Programs + Orders
├── WritePlan Validation
└── PostgreSQLCommitRepository
    → ApplicationCommitter
    → ExecuteSchedulingCommit
```

Il grafo è lazy e non parziale. `execute_scheduling_commit` è `None` senza PG.
La stessa istanza del commit repository è iniettata nel committer e lo stesso
committer nell'orchestratore. Non esiste selezione implicita del backend: la
presenza esplicita della configurazione PG abilita il grafo operativo; il grafo
Google rimane separato per simulazione.

## 11. CLI

La CLI ufficiale `tpo_core` espone **2 comandi**:

| Comando | Modalità | Backend | Scrive |
|---|---|---|---:|
| `tpo schedule run --simulate` | simulazione | Google read | no |
| `tpo schedule preflight` | verifica | Google read-only guarded | no |

Non esiste comando per `ExecuteSchedulingCommit`, apertura RUN operativa,
commit PostgreSQL, lettura ordini PostgreSQL o amministrazione. Pertanto un
utente non può usare il percorso autorevole senza scrivere codice Python o
invocare direttamente le classi.

Sono inoltre presenti entrypoint legacy (`process_event`, `aggiornami`,
`init_resource_engine`, `write_sheets`) che appartengono alla precedente
architettura Google. Alcuni possono scrivere se invocati con le opzioni
appropriate e non devono essere confusi con la CLI ufficiale del Core.

## 12. Database

### 12.1 Migrazione 0001

La foundation crea:

- `id_sequences`;
- `runs`;
- `run_messaggi`;
- `run_log`;
- enum, check, foreign key e indici necessari.

### 12.2 Migrazione 0002

Il perimetro del commit crea:

- `clienti`;
- `varieta`;
- `programmi_fornitura`;
- `programmi_fornitura_versioni`;
- `righe_programma_fornitura`;
- `righe_programma_giorni`;
- `ordini`;
- `righe_ordine`;
- `origini_righe_ordine`;
- `audit_eventi`.

Le tabelle sono effettivamente usate da Identity, Run Tracking, lettura
Scheduling, validazione e commit. `run_log` è foundation disponibile ma non è
parte del commit operativo congelato. Il Physical Schema documenta inoltre
molte tabelle future non ancora migrate: cultivar, usi, protocolli, sementi,
lotti seme, consegne, semine, raccolte, stock e movimenti.

Non è un mismatch implementativo: la migrazione 0002 è intenzionalmente minima
per il write path atomico. Diventa però essenziale non interpretare il Physical
Schema completo come schema già materializzato.

## 13. Tests

La suite Core richiesta ha prodotto:

```text
969 passed in 1.09s
```

Non sono comparsi skip o warning nella suite Core. I test PostgreSQL reali sono
opt-in mediante `TPO_TEST_DATABASE_URL`; non sono stati eseguiti in questa
review per rispettare il divieto di connessioni. Il freeze finale registra 13
test di integrazione reali verdi, inclusi concorrenza, lock, optimistic version,
idempotenza e rollback.

Punti forti:

- invarianti Domain capillarmente coperti;
- servizi Application testati con fake/spy;
- adapter Google e PG coperti senza richiedere rete nel Core;
- migrazioni ispezionate strutturalmente;
- Bootstrap verifica istanze, injection e lazy construction;
- CLI verifica codici di uscita, formato e guardie read-only;
- test reali separati e opt-in.

Punti deboli:

- il numero elevato di test non misura direttamente coverage di linea/ramo;
- manca un test di entrypoint operativo perché tale entrypoint non esiste;
- i moduli legacy e il nuovo Core mantengono suite separate ma convivono nello
  stesso package `src`, aumentando il costo di governance;
- i test strutturali delle migrazioni possono divergere dal comportamento reale,
  mitigato ma non sostituito dai 13 test opt-in;
- nessuna evidenza di test deployment, backup/restore, osservabilità o UI.

## 14. Runtime Capabilities

### Capacità tecnica disponibile

- leggere PROGRAMMI e ORDINI da Google per simulazione;
- generare anteprime Scheduling deterministiche;
- leggere PROGRAMMI versionati e ORDINI da PostgreSQL;
- allocare ID persistenti e aprire RUN;
- costruire e validare WritePlan;
- committare atomically ORDINI automatici in PostgreSQL;
- completare RUN, provenance e audit nella stessa transazione;
- leggere ordini PostgreSQL tramite repository;
- eseguire health check e migrazioni tramite API infrastrutturali esplicite.

### Capacità disponibile all'utente

- eseguire simulazione Scheduling;
- eseguire preflight Google read-only;
- usare gli entrypoint storici Google, separati dal runtime autorevole.

### Capacità non disponibile senza Python diretto

- commit operativo PostgreSQL;
- apertura e gestione RUN operativa completa;
- consultazione operativa degli ORDINI PostgreSQL;
- import/bootstrap dati;
- gestione manuale di CLIENTI, VARIETÀ, PROGRAMMI e ORDINI;
- cicli produzione, stock, consegna e amministrazione nel nuovo Core.

La capacità tecnica PostgreSQL è quindi validata ma non ancora trasformata in
capacità operativa self-service.

## 15. Frozen Contracts

Sono congelati e non devono essere riaperti senza Architecture Review:

- PostgreSQL come sorgente autorevole del runtime operativo;
- `PostgreSQLCommitRepository` come unico writer del commit;
- nessun dual-write o fallback Google;
- confine transazionale unico;
- lifecycle e optimistic version della RUN;
- programmi versionati nel percorso autorevole;
- locator provider-neutral della provenance;
- idempotenza a pre-check più unique constraint;
- actor, reason e correlation ID espliciti;
- semantica dei tre timestamp;
- receipt e conteggi;
- schema fisico e migrazioni versionate;
- orchestrazione `ExecuteSchedulingCommit`;
- Bootstrap lazy e grafo operativo completo o assente.

## 16. Documentation Alignment

| Gravità | Documento | Codice/freeze | Mismatch | Proposta |
|---|---|---|---|---|
| CRITICAL | `TPO_CORE_PRINCIPLES.md` principio 2 | freeze PG finale | dichiara Google unico database ufficiale | emendamento normativo che distingua baseline storica e autorità PG corrente |
| CRITICAL | `SYSTEM_ARCHITECTURE.md` | freeze PG finale e Bootstrap | dichiara Google Sheets Writer unico writer e Google datastore ufficiale | nuova revisione architetturale allineata, preservando il documento storico |
| MAJOR | `PROJECT_SNAPSHOT_v1.0.md` | Core corrente | fotografa baseline pre-implementazione e Google autorevole | marcarlo chiaramente historical/superseded nel catalogo documentale |
| MAJOR | `TPO_SHEETS_SCHEMA.md` | schema PG | è autorevole per intestazioni Google, non per PG | dichiarare esplicitamente il suo confine legacy/reporting |
| MAJOR | `PERSISTENCE_ARCHITECTURE_REVIEW.md` | freeze finale | stato ancora “decision proposed” e provider Supabase consigliato | marcarne le decisioni recepite, superate o ancora aperte |
| MINOR | `migrations/README.md` | migrazione 0002 presente | descrive soprattutto la prima revisione | aggiornare l'inventario senza modificare policy |
| HISTORICAL | `MILESTONE_REVIEW_1_PRE_WRITE.md` | foundation completata | blocker Google pre-write ormai superati dal percorso PG | conservare come checkpoint storico |

Le architecture note specialistiche e i register descrivono un perimetro molto
più ampio del codice attuale. Questo è design intenzionale, non dichiarazione di
implementazione.

## 17. Technical Debt

### A. Debito tecnico reale

- doppia generazione di runtime sotto `src/` senza separazione di packaging o
  deprecation enforcement;
- writer Google legacy invocabili direttamente;
- documentazione normativa contraddittoria sull'autorità dei dati;
- Bootstrap richiede ancora configurazione Google anche per costruire il grafo
  PG, creando coupling operativo non necessario al futuro entrypoint PG;
- `ApplicationContainer` espone soltanto parte degli oggetti PG costruiti,
  rendendo diagnostica e introspezione meno uniformi;
- assenza di comando operativo e relativo error mapping;
- nessuna misura coverage pubblicata;
- requisiti production (backup, restore, monitoring, least privilege) non
  automatizzati né validati.

### B. Debito apparente / scelta architetturale

- tabelle del Physical Schema non ancora migrate fuori dal commit ORDINI;
- Domain di SEMINE/RACCOLTE/STOCK/CONSEGNE senza adapter;
- ORDINI manuali fuori dal percorso Scheduling;
- Google mantenuto per simulazione e compatibilità;
- assenza di UI, amministrazione e reporting nel freeze PostgreSQL;
- assenza di retry automatico nel commit;
- repository PG di lettura deliberatamente read-only.

Questi elementi sono scope rinviato o invarianti espliciti, non difetti della
foundation.

## 18. Functional Gaps

| Macro-area | Gap verificabile |
|---|---|
| OPERATIONS | nessun entrypoint operativo PG; nessun workflow completo operatore |
| PRODUCTION | SEMINE/RACCOLTE e pianificazione produttiva non integrate nel nuovo Core |
| STOCK | niente persistenza operativa di stock/movimenti nel nuovo Core |
| CLIENTI | nessuna gestione anagrafica/use case; solo ID e tabella minima |
| ORDINI | solo generazione automatica Scheduling; manuali e gestione lifecycle assenti |
| PROGRAMMI | lettura presente; creazione/modifica/versionamento operativo assenti |
| AMMINISTRAZIONE | documenti vendita, fatture, incassi e workflow assenti |
| PHOTO BANK | solo design/legacy; nessun modulo nel nuovo Core |
| REPORTING | nessun read model/report PG; AGGIORNAMI resta Google legacy |
| CLI | solo simulazione e preflight; nessun commit, query o admin PG |
| UI | assente |
| IMPORT/EXPORT | import legacy e bootstrap dati assenti; export Google futuro |
| DEPLOYMENT | nessun ambiente production congelato o pipeline di deploy operativo |
| OBSERVABILITY | health check presente; monitoring, metriche e alerting assenti |

## 19. Maturity Matrix

Scala: 0 non iniziata, 1 design, 2 contracts, 3 implemented, 4 integrated,
5 validated, 6 frozen/stable.

| Area | Livello | Motivazione |
|---|---:|---|
| Domain Core | 5 | implementato e ampiamente testato; alcune aree non integrate |
| Scheduling | 6 | implementato, integrato, validato e congelato |
| Identity | 6 | PG, CAS concorrente e freeze |
| Run Tracking | 6 | lifecycle, persistenza e concorrenza congelati |
| WritePlan | 6 | contratti e validazione congelati |
| Committer | 6 | receipt e repository contract congelati |
| PostgreSQL Persistence | 6 | foundation validata e freeze finale |
| Operational Scheduling | 5 | E2E tecnico validato, non accessibile da CLI |
| Bootstrap | 6 | wiring lazy validato e congelato |
| Google Legacy | 4 | integrato/testato, ma non più autorevole |
| CLI | 3 | simulazione/preflight implementati; runtime operativo assente |
| Administration | 1 | documentazione/register, nessun nuovo Core |
| Production/Stock | 2 | Domain e contratti documentali, integrazione assente |
| Photo Bank | 1 | design documentale/legacy |
| Deployment | 1 | requisiti noti, implementazione production assente |
| Monitoring | 2 | health contract implementato, osservabilità assente |
| UI | 0 | non iniziata nel TPO Core |

## 20. Risks

| Categoria | Rischio | Prob. | Impatto | Priorità | Mitigazione |
|---|---|---:|---:|---:|---|
| ARCHITECTURAL | documenti ufficiali indicano writer diversi | alta | alta | P0 | riallineare autorità documentale senza riaprire il freeze |
| OPERATIONAL | writer legacy invocato al posto del runtime PG | media | alta | P0 | entrypoint unico, guardie e deprecation esplicita |
| PRODUCT | Core validato ma inutilizzabile dall'operatore per commit | alta | alta | P0 | CLI operativa PG con conferma ed error mapping |
| DATA | assenza di bootstrap/import governato | alta | alta | P1 | progettare migrazione dati verificabile e idempotente |
| SECURITY | privilegi, backup e restore production non validati | media | alta | P1 | runbook, ruoli minimi e restore drill prima della produzione |
| MAINTENANCE | doppia codebase legacy/Core | alta | media | P1 | catalogare ownership, deprecare e poi rimuovere per capitoli |
| OPERATIONAL | health check senza monitoring/alerting | media | media | P2 | metriche e alert sul runtime |
| PRODUCT | aree Domain scambiate per feature complete | media | media | P2 | matrice capability pubblica e acceptance per area |

## 21. Remaining Macro Chapters

### Capitoli completati

- Domain Core fondamentale;
- Scheduling deterministico;
- Identity e Run Tracking PostgreSQL;
- WritePlan, validation e Committer;
- PostgreSQL Foundation, schema atomico e concorrenza;
- Operational Scheduling Application e Bootstrap wiring;
- freeze finale del percorso atomico.

### Roadmap dei capitoli aperti

| Ordine | Macro-capitolo | Obiettivo/output | Prerequisiti | Dipendenze sbloccate | Rischio | Priorità |
|---:|---|---|---|---|---|---|
| 1 | Operational Runtime / CLI Write | entrypoint PG sicuro, conferma, esiti e runbook | freeze attuale | uso reale, import verification | medio | P0 |
| 2 | Data Bootstrap / Import iniziale | caricare CLIENTI, VARIETÀ e PROGRAMMI con riconciliazione | entrypoint/strumenti operativi | esercizio su dati reali | alto | P0 |
| 3 | Operations Core | gestione anagrafiche, programmi e ordini manuali | dati bootstrap e review dei writer | ciclo commerciale | alto | P1 |
| 4 | Production Core | SEMINE, RACCOLTE, CONSEGNE e workflow | Operations Core e schema incrementale | tracciabilità farm | alto | P1 |
| 5 | Stock | movimenti autorevoli e proiezione stock | produzione/consegne | disponibilità e planning | alto | P1 |
| 6 | Reporting | read model PG, export e AGGIORNAMI | dati operativi affidabili | decisioni quotidiane | medio | P2 |
| 7 | Administration | documenti vendita e incassi | ordini/consegne stabili | back office | alto | P2 |
| 8 | Observability | metriche, log, alert e audit operativo | runtime stabile | unattended operation | medio | P1 |
| 9 | Production Deployment | ambienti, ruoli, backup, restore e release | runtime, dati, osservabilità | go-live | alto | P0 prima del go-live |
| 10 | UI | interfaccia operatore sulle capability stabili | use case e API definiti | adozione | medio | P3 |
| 11 | Photo Bank | tracciabilità media collegata ai lotti | Production Core | documentazione visiva | basso | P3 |

L'ordine non segue l'elenco suggerito alla lettera: Stock dipende dagli eventi
di produzione e consegna; UI deve seguire use case stabili; deployment deve
essere preparato presto ma può essere validato soltanto dopo un runtime
operativo osservabile.

## 22. Recommended Next Chapter

Il prossimo capitolo deve essere **Operational Runtime / CLI Write**.

È il passaggio più piccolo che trasforma una capacità tecnica già validata in
una capacità utilizzabile senza introdurre un secondo writer o nuove semantiche
di dominio. È opportuno ora perché Foundation, concorrenza, orchestratore e
Bootstrap sono congelati: il rischio di costruire l'entrypoint su contratti
instabili è rimosso.

Questo capitolo sblocca:

- esercizio controllato del percorso autorevole;
- verifica dei dati bootstrap;
- procedure operative e gestione errori;
- successiva dismissione pratica dei writer Google;
- misurazione e osservabilità del runtime reale.

Data import, Operations Core e UI possono aspettare perché, senza un percorso
operativo ufficiale, aggiungerebbero dati o superfici che l'operatore non può
governare in sicurezza. Deployment production può essere progettato in
parallelo a livello di requisiti, ma non dichiarato pronto.

## 23. Overall Maturity Verdict

| Dimensione | Verdetto | Motivazione |
|---|---|---|
| Architecture maturity | **INTERNAL BETA** | nucleo PG solido e congelato; documentazione globale e legacy ancora da governare |
| Product maturity | **ALPHA** | Scheduling completo, ma gran parte del ciclo aziendale non è integrata |
| Operational maturity | **PROTOTYPE** | simulazione disponibile; commit PG richiede Python diretto; niente deploy/monitoring |
| Overall | **ALPHA** | base credibile e testata, non ancora prodotto operativo completo |

Il progetto è **architecture-ready per evolvere**, non product-ready e non
production-ready.

## 24. Architecture Decisions That Must Not Be Reopened

1. PostgreSQL è la fonte autorevole del runtime operativo.
2. Il Domain e le porte non dipendono da Supabase o da un provider specifico.
3. `PostgreSQLCommitRepository` è l'unico writer del commit Scheduling.
4. Google non partecipa alla transazione autorevole e non è fallback.
5. Il commit di ORDINI, provenance, audit e completamento RUN è atomico.
6. RUN usa lock e optimistic version.
7. Gli identificativi sono permanenti, tipizzati e allocati persistentemente.
8. Scheduling operativo richiede PROGRAMMI versionati.
9. Provenance usa il locator provider-neutral congelato.
10. Idempotenza usa pre-check più unique constraint.
11. Actor, reason, correlation ID e timestamp sono espliciti.
12. Receipt e conteggi hanno semantica congelata.
13. I repository PG dichiarati read-only restano read-only.
14. Bootstrap non apre connessioni e costruisce il grafo completo o nessuno.
15. Ogni evoluzione dello schema avviene con nuova migrazione.

## 25. Open Questions Requiring Future Architecture Review

1. Qual è il contratto dell'entrypoint operativo, inclusi conferma umana,
   costruzione del contesto actor e gestione degli errori?
2. Come separare formalmente package, comandi e lifecycle della codebase Google
   legacy dal Core PostgreSQL?
3. Quale processo governa import iniziale, validazione, riconciliazione e
   cut-over dei dati?
4. Quali use case scrivono CLIENTI, VARIETÀ, PROGRAMMI e ORDINI manuali?
5. Qual è il prossimo confine transazionale per PRODUZIONE, CONSEGNE, MOVIMENTI
   e STOCK?
6. Quali register diventano tabelle autorevoli, eventi immutabili o viste
   derivate nel modello PG?
7. Qual è il modello di autenticazione/autorizzazione degli operatori?
8. Quali requisiti minimi di backup, restore, retention e disaster recovery
   precedono il go-live?
9. Quali read model e quale strategia export sostituiscono AGGIORNAMI Google?
10. Quando e con quali criteri i writer Google legacy possono essere rimossi?

---

**Conclusione:** la PostgreSQL Foundation è conclusa e non va riaperta. Il
progetto deve ora rendere operativo quel percorso, riallineare l'autorità
documentale e costruire i macro-capitoli di prodotto sopra contratti stabili,
senza confondere solidità del nucleo con prontezza produttiva complessiva.
