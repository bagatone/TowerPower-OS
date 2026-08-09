# OPERATIONAL RUNTIME FINAL FREEZE

**Stato:** FINAL ARCHITECTURE FREEZE
**Ambito:** Runtime Operativo PostgreSQL
**Baseline:** `30d695f`
**Natura:** consolidamento normativo

## 1. Scope

Il presente documento consolida il contratto definitivo del Runtime Operativo
PostgreSQL del Tower Power Operations. Riunisce in un solo riferimento il
runtime Application, l'Operational Entry Point, l'adapter CLI, il Bootstrap e
le garanzie PostgreSQL già congelati.

Il documento comprende:

- il grafo operativo autorevole;
- ownership e confini dei componenti;
- lifecycle della RUN e del commit;
- ownership e ordinamento dei timestamp;
- invarianti di esecuzione;
- outcome Application ed exit del boundary CLI;
- composizione Bootstrap e segregazione Google;
- contratto CLI e Operational Entry Point;
- garanzie PostgreSQL;
- acceptance contract e regression suite minima.

Il documento non comprende:

- nuove decisioni Domain;
- nuovi use case, outcome, stati RUN o writer;
- modifiche a schema, DDL o migrazioni;
- ordini manuali;
- simulation nel nuovo entry point operativo;
- authentication o authorization;
- API, scheduler, job unattended o event consumer concreti;
- recovery o riconciliazione operativa;
- import dati, deployment, monitoring o UI;
- rimozione dei percorsi legacy.

Questo Freeze non modifica né sostituisce i Freeze originari. In caso di
discrepanza, ambiguità o differenza di dettaglio prevalgono sempre i documenti
normativi originari, in particolare:

- `APPLICATION_OPERATIONAL_RUNTIME_FREEZE.md`;
- `APPLICATION_OPERATIONAL_ENTRYPOINT_FREEZE.md`;
- `CLI_OPERATIONAL_ADAPTER_FREEZE.md`;
- `APPLICATION_ATOMIC_COMMIT_FREEZE.md`;
- `POSTGRESQL_FOUNDATION_FINAL_FREEZE.md`.

## 2. Runtime graph

Il grafo operativo autorevole completo è:

```text
CLI
↓
OperationalSchedulingEntryPoint
↓
OperationalSchedulingOrchestrator
↓
RunScheduling
↓
ExecuteSchedulingCommit
↓
ApplicationCommitter
↓
PostgreSQLCommitRepository
↓
PostgreSQL
```

Il grafo è unico. La CLI non salta l'Entry Point; l'Entry Point non sostituisce
l'orchestratore; l'orchestratore non salta `ExecuteSchedulingCommit`; il
runtime Application non chiama direttamente PostgreSQL fuori dalle porte
congelate.

`RunScheduling` legge PROGRAMMI versionati e ORDINI esistenti tramite i
repository PostgreSQL read-only. `PostgreSQLCommitRepository` è l'unico writer
autorevole del commit automatico. Google non appartiene al grafo operativo.

## 3. Ownership

| Componente | Responsabilità | Input | Output | Non può fare |
|---|---|---|---|---|
| CLI | parsing, validazione esterna, conferma, costruzione dell'intenzione, rendering ed exit mapping | settings, business date, business time, identity, confirm | output testuale ed exit code | costruire execution context, aprire RUN, allocare ID, usare Clock, orchestrare Application, accedere a repository o interpretare errori PostgreSQL |
| `OperationalSchedulingEntryPoint` | tradurre l'intenzione provider-neutral, costruire internamente il contesto di esecuzione e proiettare il risultato pubblico | `OperationalSchedulingIntent` | `OperationalEntryPointResult` | governare il lifecycle, esporre modelli Committer, dettagli Infrastructure o cause tecniche |
| `OperationalSchedulingOrchestrator` | allocare RunId, catturare l'avvio, aprire la RUN, eseguire Scheduling e governare success, failure certa e riconciliazione | input operativo Application validato | risultato operativo discriminato | parsing CLI, SQL, retry, secondo lifecycle o classificazione tramite testo di eccezioni |
| `RunScheduling` | leggere i PROGRAMMI attivi, calcolare occorrenze, applicare idempotenza applicativa e produrre lo Scheduling | RUN, business date, modalità, repository read-only | `SchedulingResult` | aprire o concludere RUN, costruire WritePlan, eseguire commit o creare ORDINI manuali |
| `ExecuteSchedulingCommit` | trasformare uno `SchedulingResult` già prodotto in completion proposta, piano validato e richiesta di commit | RUN aperta, `SchedulingResult`, execution context | risultato del tratto commit | allocare RunId, aprire RUN, rieseguire Scheduling, fare retry o trasformare reconciliation in failure certa |
| `ApplicationCommitter` | preparare e invocare una sola volta la porta `CommitRepository`, validare receipt e classificare il risultato | `CommitRequest` | `CommitResult` | scegliere provider, accedere direttamente al database, ripetere il commit o inventare receipt |
| `PostgreSQLCommitRepository` | applicare atomicamente il piano validato, concludere la RUN e produrre receipt o outcome incerto | `CommitRequest` | `CommitExecutionReceipt` o outcome incerto provider-neutral | cambiare il piano, inferire dati mancanti, eseguire I/O esterno, fare retry o produrre scritture parziali |
| PostgreSQL | applicare transazioni, lock, constraint, CAS e persistenza fisica | statement parametrizzati del repository | stato persistente autorevole | assumere ownership della business logic Application |
| Bootstrap | comporre il grafo completo e iniettare le stesse dipendenze condivise | settings e configurazione PostgreSQL | container operativo completo oppure runtime assente | aprire connessioni, eseguire use case, decidere outcome, introdurre fallback o costruire un grafo operativo parziale |

Run Tracking conserva la responsabilità tecnica della persistenza della RUN.
`SchedulingRunService.open_run()` registra l'apertura. La conclusione di
successo avviene nella transazione atomica del commit; `fail_run()` appartiene
soltanto alle failure operative certe consentite dal Freeze. Run Tracking non
diventa un orchestratore e non scrive ORDINI.

## 4. Lifecycle

Il lifecycle operativo completo è:

1. La CLI valida sintassi, business reference, identity e presenza di
   `--confirm`.
2. La CLI costruisce esclusivamente `RecognizedOperationalIdentity` e
   `OperationalSchedulingIntent`.
3. La CLI invoca una sola volta `OperationalSchedulingEntryPoint`.
4. L'Entry Point costruisce internamente `CommitExecutionContext`, includendo
   actor, reason applicativa e correlation ID.
5. L'orchestratore alloca un unico RunId tramite `PersistentIdAllocator`.
6. L'orchestratore cattura `run_started_at` dal Clock condiviso.
7. `SchedulingRunService.open_run()` persiste una sola RUN aperta, non
   simulata, alla versione iniziale.
8. `RunScheduling` viene eseguito una sola volta usando la business date
   esplicita.
9. Una failure certa di Scheduling termina il tratto prima del commit e
   attiva, quando consentito, la conclusione best-effort `FAILED` della RUN.
10. Uno Scheduling valido viene consegnato una sola volta a
    `ExecuteSchedulingCommit`.
11. `ExecuteSchedulingCommit` cattura `completion_at`, propone la completion,
    costruisce il WritePlan e ne richiede la validazione read-only.
12. Dopo validazione acquisisce `requested_at` e costruisce il
    `CommitRequest`.
13. `ApplicationCommitter` invoca una sola volta
    `PostgreSQLCommitRepository`.
14. Il repository applica in una sola transazione ORDINI, righe, provenance,
    audit, messaggi e conclusione versionata della RUN.
15. Dopo conferma fisica del commit il repository acquisisce
    `commit_completed_at` e restituisce la receipt.
16. Soltanto un commit confermato produce `CompletedSchedulingRun` e outcome
    `COMMITTED`.

Una failure certamente non committata produce `FAILED` e può concludere la RUN
solo se ancora aperta alla versione attesa. Un outcome fisico incerto produce
`RECONCILIATION_REQUIRED`, non conclude la RUN come `FAILED`, non esegue retry
e non tenta un secondo commit.

## 5. Timeline

Per ogni commit confermato deve valere:

```text
run_started_at <= completion_at <= requested_at <= commit_completed_at
```

| Timestamp | Origine | Owner | Semantica |
|---|---|---|---|
| `run_started_at` | Clock condiviso | `OperationalSchedulingOrchestrator` | istante tecnico acquisito immediatamente prima dell'apertura RUN |
| `completion_at` | Clock condiviso | `ExecuteSchedulingCommit` | conclusione semantica proposta dopo Scheduling e prima del piano |
| `requested_at` | Clock condiviso | `ExecuteSchedulingCommit` | inizio applicativo della richiesta dopo validation e immediatamente prima del commit |
| `commit_completed_at` | Clock condiviso | `PostgreSQLCommitRepository` | istante acquisito soltanto dopo conferma del commit fisico |

`CommitRequest.requested_at` valorizza esplicitamente `ordini.created_at`.
`SchedulingRunCompletion.completed_at` valorizza la conclusione della RUN.
`commit_completed_at` appartiene alla receipt e non viene ricostruito dal
database. L'audit transazionale usa un proprio timestamp pre-commit distinto.

La business date e la business time non appartengono a questa timeline
tecnica. Formano il `CurrentSystemDate` esplicito usato dallo Scheduling nella
timezone `Atlantic/Canary` e non vengono derivate dal Clock runtime.

## 6. Runtime invariants

Il Runtime Operativo rispetta congiuntamente i seguenti invarianti:

- una sola allocazione di RunId per intenzione invocata;
- una sola apertura RUN;
- una sola esecuzione di `RunScheduling`;
- una sola esecuzione di `ExecuteSchedulingCommit`;
- una sola invocazione del commit repository;
- una sola transazione e un solo commit fisico per tentativo;
- nessun retry automatico;
- nessun fallback Google o provider alternativo;
- nessun dual-write;
- nessun doppio commit;
- nessun secondo lifecycle operativo;
- nessun accesso runtime alternativo esposto alla CLI;
- stessa istanza logica Clock per orchestratore, tratto commit e repository;
- stessa istanza `PersistentIdAllocator` per allocazione RunId e allocazione
  degli identificativi richiesta dal grafo Scheduling;
- business date distinta dal Clock tecnico;
- RUN non simulata nel percorso operativo;
- optimistic version e lock della RUN;
- idempotenza applicativa più vincolo PostgreSQL definitivo;
- nessun dato parziale, audit orfano o provenance orfana dopo rollback;
- nessuna classificazione basata sul testo di eccezioni provider-specific.

## 7. Outcome matrix

Gli outcome Application e gli exit del boundary CLI restano livelli distinti.

| Esito | Origine | Boundary | Responsabilità |
|---|---|---|---|
| `COMMITTED` | commit fisico confermato e receipt coerente | Application | restituisce la RUN conclusa e i dati pubblici autorizzati |
| `FAILED` | failure certa, con prova di mancato commit | Application | preserva errore primario, warning e stato RUN noto; finalizza `FAILED` solo quando consentito |
| `RECONCILIATION_REQUIRED` | esito fisico non dimostrabile | Application | espone contesto provider-neutral, non conclude `FAILED`, non ritenta |
| `INPUT_INVALID` | parsing, valore esterno o conferma non validi | CLI | termina prima dell'invocazione Application |
| `RUNTIME_UNAVAILABLE` | grafo PostgreSQL operativo completo assente | CLI/Bootstrap boundary | termina senza fallback e senza grafo parziale |
| `INTERNAL_ERROR` | errore inatteso non rappresentato dagli outcome Application | CLI boundary | produce errore generico provider-neutral senza causa tecnica o traceback |

Gli exit code congelati sono:

| Exit simbolico | Codice |
|---|---:|
| `OPERATION_COMMITTED` | `0` |
| `OPERATION_FAILED` | `1` |
| `OPERATION_INPUT_INVALID` | `2` |
| `OPERATION_RUNTIME_UNAVAILABLE` | `3` |
| `OPERATION_RECONCILIATION_REQUIRED` | `4` |
| `OPERATION_INTERNAL_ERROR` | `5` |

I nomi simbolici degli exit code non costituiscono automaticamente contenuto
obbligatorio dello stdout. Il rendering e l'exit code vengono verificati
separatamente secondo il contratto CLI approvato.

## 8. Bootstrap

La factory legacy conserva il grafo necessario a `tpo schedule run` e
`tpo schedule preflight`, senza modificarne la semantica. Tale grafo può
costruire adapter Google per simulazione e preflight, ma non costituisce il
runtime operativo PostgreSQL.

La factory operativa:

- compone direttamente il solo grafo PostgreSQL necessario;
- espone `OperationalSchedulingEntryPoint` quando il grafo è completo;
- non attraversa la costruzione del grafo Google legacy;
- non costruisce gateway, repository o writer Google;
- non espone `RunScheduling` come entry point alternativo;
- restituisce runtime non disponibile quando la configurazione PostgreSQL non
  consente il grafo completo;
- non introduce fallback.

La costruzione è lazy:

- nessuna connessione PostgreSQL al build;
- nessuna lettura `Clock.now()` al build;
- nessuna chiamata Google;
- nessuna autenticazione;
- nessuna operazione network;
- nessuna migrazione applicata implicitamente.

Il container operativo mantiene assenti le dipendenze Google e i servizi
legacy esposti, conservando internamente le sole dipendenze necessarie
all'Operational Entry Point.

## 9. CLI

Il comando operativo ufficiale V1 è:

```text
tpo schedule execute \
  --settings SETTINGS \
  --business-date YYYY-MM-DD \
  --business-time HH:MM \
  --identity IDENTITY \
  --confirm
```

`--business-date` e `--business-time` sono obbligatori, privi di default e
formano il riferimento semantico nella timezone `Atlantic/Canary`.
`--identity` è obbligatoria, non vuota, opaca e provider-neutral. La CLI la
trasforma esclusivamente in `RecognizedOperationalIdentity`; non costruisce
`ActorId`, reason, correlation ID o `CommitExecutionContext`.

`--confirm` è obbligatorio e non interattivo. Se manca, nessun componente
Application viene invocato. Non esistono prompt, `--force`, write implicito o
fallback simulation.

Il comando non supporta `--simulation`. La simulation legacy resta separata.
La CLI non accede direttamente a orchestratore, Scheduling, Committer,
repository, Clock o connection factory e non interpreta eccezioni PostgreSQL.

Per un successo il processo restituisce exit code `0` e il rendering pubblico
contiene `STATUS: COMMITTED`, RunId e warning secondo il formato approvato. Il
nome simbolico `OPERATION_COMMITTED` non è una stringa stdout obbligatoria.

## 10. Entry Point

`OperationalSchedulingEntryPoint` è il solo contratto pubblico Application per
gli adapter operativi.

`RecognizedOperationalIdentity` rappresenta l'identità operativa riconosciuta
dal caller. È provider-neutral, opaca e non equivale a una credenziale. Il
boundary la trasforma internamente nell'actor applicativo.

`OperationalSchedulingIntent` contiene soltanto gli input pubblici autorizzati:
il riferimento di business esplicito e l'identità operativa riconosciuta. Non
espone RunId, Clock, timestamp tecnici o execution context.

Il boundary interno costruisce `CommitExecutionContext` mediante il componente
Application dedicato:

- actor deriva dall'identità riconosciuta;
- reason deriva dalla policy Application dell'operazione;
- correlation ID viene generato uniformemente e propagato senza modifiche.

`OperationalEntryPointResult` espone soltanto il risultato provider-neutral:
status, RunId, RUN conclusa quando autorizzata, warning, errori e contesto di
riconciliazione pubblico quando necessario. Non espone modelli Committer,
exception provider-specific o cause tecniche.

`OperationalReconciliationContext` è la proiezione pubblica autorizzata
dell'esito incerto. Può trasportare RunId, requested_at, correlation ID,
idempotency keys e conteggi attesi congelati. Non trasporta
`CommitOutcomeUncertain`, `technical_cause`, `BaseException`, SQL, credenziali
o dettagli provider-specific.

L'Entry Point non apre RUN, non alloca ID e non governa il lifecycle. Delega una
sola volta all'`OperationalSchedulingOrchestrator`.

## 11. PostgreSQL guarantees

### Atomic commit

Il commit operativo usa una connessione, una transazione e un solo commit
finale. La transazione comprende lock e verifica della RUN, pre-check
idempotente, lookup autorevoli, ORDINI, RIGHE_ORDINE, provenance, audit,
completamento versionato della RUN e RUN_MESSAGGI. Qualunque failure certa
prima del commit produce rollback totale.

### Audit

Ogni ORDINE committato produce un audit `ORDINE`/`INSERT`. L'ultimo evento
logico della transazione è un audit RUN `STATE_TRANSITION`. Actor, reason e
correlation ID provengono dal medesimo `CommitExecutionContext`. I payload non
espongono PK interne. Il rollback elimina anche gli audit non committati.

### Run Tracking

La RUN viene aperta prima dello Scheduling e resta aperta fino alla conclusione
autorevole. Il successo viene concluso nella transazione del commit. Le failure
certe possono essere concluse separatamente tramite Run Tracking solo se la RUN
è ancora aperta alla versione attesa. Una RUN già conclusa non riceve una
seconda finalizzazione.

### Identity CAS

Gli identificativi operativi sono allocati persistentemente tramite sequenze
tipizzate e versionate. Il compare-and-set PostgreSQL impedisce allocazioni
concorrenti incoerenti. Non esiste retry automatico; eventuali buchi di
sequenza dopo failure sono ammessi dal contratto.

### Optimistic concurrency

Il commit usa lock PostgreSQL e `expected_version`. La RUN deve essere aperta,
non simulata e alla versione prevista. Una collisione idempotente o un
conflitto di versione non produce dati parziali, secondo commit o retry.

## 12. Acceptance Contract

Il Runtime Operativo è considerato validato soltanto quando l'acceptance
dimostra congiuntamente:

- invocazione del comando reale `tpo schedule execute`;
- parsing esplicito di business date e business time;
- identity esplicita e conferma obbligatoria;
- attraversamento esclusivo di `OperationalSchedulingEntryPoint`;
- allocazione di un RunId e apertura di una RUN;
- esecuzione singola di Scheduling e commit;
- exit code `0` e `STATUS: COMMITTED` nel happy path;
- persistenza coerente di RUN, ORDINE automatico, righe e provenance;
- actor, reason e correlation ID coerenti nell'audit;
- ordinamento `run_started_at <= completion_at <= requested_at` osservabile
  tramite RUN e `ordini.created_at`;
- idempotenza su una seconda intenzione equivalente senza duplicazioni o dati
  parziali;
- input non valido rifiutato prima di qualsiasi nuova RUN;
- runtime assente classificato senza fallback;
- zero costruzioni e zero chiamate Google nel percorso operativo;
- assenza di credenziali, DSN, SQL, traceback, cause tecniche e PK interne
  nell'output pubblico;
- migrazioni applicate e rimosse esclusivamente sul database test dedicato;
- connessione reale PostgreSQL con SSL secondo la configurazione test;
- suite Core priva di regressioni.

L'acceptance non ricostruisce `commit_completed_at` dal database, perché tale
timestamp appartiene alla receipt e non è persistito come dato dedicato.

## 13. Regression Suite

Prima di ogni release del Runtime Operativo devono essere eseguite almeno:

1. suite CLI;
2. suite Bootstrap;
3. suite Application Operational Entry Point;
4. suite Application Operational Scheduling e Run Tracking;
5. suite Infrastructure PostgreSQL;
6. integration PostgreSQL offline;
7. integration PostgreSQL reale opt-in sul database test dedicato;
8. acceptance CLI PostgreSQL reale;
9. Core completo: Domain, Application, Infrastructure, Bootstrap e CLI;
10. `git diff --check`.

La suite PostgreSQL reale conserva le guardie congelate: database il cui nome
contiene `test`, SSL attivo, lifecycle Alembic controllato, nessuna credenziale
stampata e nessun cleanup distruttivo di oggetti estranei.

Le prove di regressione includono almeno happy path, failure certa,
reconciliation, optimistic version, idempotenza, concorrenza reale, rollback,
lazy construction, segregazione Google, input invalid e runtime unavailable.

## 14. Frozen architecture summary

| Area | Stato |
|---|---|
| PostgreSQL Foundation | Frozen |
| Schema e migrazioni del commit | Frozen |
| Identity CAS | Frozen e validata |
| Run Tracking | Frozen e validato |
| Scheduling automatico | Frozen e validato |
| WritePlan e validation | Frozen e validati |
| Atomic Commit | Frozen e validato |
| Writer PostgreSQL autorevole | Frozen |
| Runtime Application | Frozen |
| Operational Entry Point | Frozen |
| CLI operativa | Frozen |
| Exit mapping | Frozen |
| Acceptance | Validata |
| Timeline | Frozen e validata |
| Bootstrap operativo | Frozen e validato |
| Google segregation | Validata |
| PostgreSQL reale | Validato su database test dedicato |
| Retry automatico | Vietato |
| Fallback e dual-write | Vietati |
| Simulation nel nuovo entry point | Fuori scope |
| Authentication e Authorization | Fuori scope |

## 15. Conclusion

Il Runtime Operativo PostgreSQL è architetturalmente stabile.

Il percorso autorevole parte dall'adapter CLI, attraversa esclusivamente
l'Operational Entry Point e l'orchestratore Application e termina nell'unico
writer PostgreSQL. Lifecycle, timeline, outcome, atomicità, idempotenza,
concorrenza, audit, Bootstrap e segregazione Google sono consolidati dai Freeze
originari e dalle rispettive acceptance.

Ogni futuro entry point operativo deve adattarsi al contratto Application. Il
contratto Application non viene modificato per adattarsi a uno specifico
adapter.

Qualunque futura modifica a writer, lifecycle, timeline, outcome, retry,
fallback, execution context, boundary pubblico, grafo operativo, schema o
garanzie transazionali deve essere trattata come evoluzione del contratto
architetturale e sottoposta al processo di Architecture Review previsto dalla
governance ufficiale.
