# APPLICATION OPERATIONAL RUNTIME FREEZE

**Stato:** ARCHITECTURE FREEZE  
**Ambito:** Operational Scheduling runtime  
**Baseline:** `5382dc6`  
**Fonti:** `APPLICATION_ATOMIC_COMMIT_FREEZE.md`,
`POSTGRESQL_FOUNDATION_FINAL_FREEZE.md`, `SCHEDULING_ENGINE.md`, `ORDINI.md`,
`REGISTER_GOVERNANCE.md` e `PROJECT_ARCHITECTURE_REVIEW_2026.md`.

## 1. Scopo

Questo documento congela il contratto Application necessario a esporre il
percorso Operational Scheduling a CLI, API o service futuri. Non definisce la
CLI concreta, non autorizza production, non modifica Domain o schema e non
introduce un writer.

Il contratto risolve:

- apertura autorevole della RUN;
- lifecycle success/failure dopo l'apertura;
- ownership dei riferimenti temporali;
- distinzione strutturata fra successo, failure certa ed esito incerto;
- responsabilità dell'orchestratore operativo, della CLI e del Bootstrap.

## 2. Runtime autorevole

Il flusso completo è:

```text
Operational caller
→ Operational Scheduling Orchestrator
→ PersistentIdAllocator.allocate(RunId)
→ SchedulingRunService.open_run(simulation=False)
→ RunScheduling
→ SchedulingRunCompletion proposal
→ WritePlanBuilder
→ WritePlanValidator
→ CommitRequest
→ ApplicationCommitter
→ PostgreSQLCommitRepository
→ Operational Scheduling Result
```

Il caller non apre RUN, non usa repository e non gestisce transazioni.
PostgreSQL resta l'unico writer autorevole. Google non appartiene al flusso.

## 3. Nuovo orchestratore operativo

È richiesto un use case Application di livello superiore. Il nome concreto può
essere scelto in implementazione; la responsabilità è congelata come
**Operational Scheduling Orchestrator**.

L'orchestratore:

1. riceve business date e `CommitExecutionContext` validati;
2. cattura `run_started_at` dal Clock;
3. alloca e persiste una nuova RUN non simulata;
4. esegue Scheduling;
5. gestisce le failure certe prima del commit;
6. delega completamento proposto, piano, validazione e commit a
   `ExecuteSchedulingCommit`;
7. restituisce un outcome strutturato;
8. non esegue retry.

L'orchestratore è riusabile da CLI, API e service. Non contiene parsing, output,
SQL o dipendenze provider-specific.

## 4. Responsabilità di ExecuteSchedulingCommit

`ExecuteSchedulingCommit` resta l'orchestratore del tratto che parte da una
`OpenSchedulingRun` già persistita:

```text
open RUN
→ Scheduling
→ completion proposal
→ WritePlan
→ validation
→ commit
```

Non alloca RunId e non apre la RUN. Deve tuttavia:

- usare il Clock nei punti temporali congelati;
- restituire un risultato anche per `RECONCILIATION_REQUIRED`;
- non materializzare `CompletedSchedulingRun` senza commit confermato;
- propagare failure tipizzate senza parsing di messaggi.

L'attuale eccezione generica quando il commit non è `COMMITTED` deve essere
sostituita dal modello strutturato definito in questo Freeze.

## 5. Apertura RUN

L'apertura appartiene all'Operational Scheduling Orchestrator tramite
`SchedulingRunService.open_run()`.

- `RunId` è allocato da `PersistentIdAllocator`;
- la sequenza è avanzata persistentemente senza retry;
- la RUN è persistita tramite `SchedulingRunRepository.add_open_run()`;
- `simulation` è sempre `False`;
- la versione iniziale è quella di `OpenSchedulingRun`, oggi `0`;
- `expected_version` deriva dalla RUN aperta e non dal caller;
- il caller non può imporre un RunId nel percorso normale.

Se l'allocazione fallisce, nessuna RUN esiste. Se l'allocazione riesce ma
l'apertura fallisce, il buco nella sequenza è ammesso e nessuna RUN viene
considerata aperta.

## 6. Lifecycle della RUN

Non vengono introdotti nuovi `RunState`. Gli stati finali restano `SUCCESS`,
`SUCCESS_WITH_WARNINGS` e `FAILED`.

| Caso | Stato autorevole |
|---|---|
| Scheduling senza warning e commit confermato | `SUCCESS` nella transazione del commit |
| Scheduling con warning e commit confermato | `SUCCESS_WITH_WARNINGS` nella transazione del commit |
| Scheduling restituisce `FAILED` | RUN conclusa `FAILED` da Run Tracking |
| Validation failure certa | RUN conclusa `FAILED` da Run Tracking |
| Identity allocation failure | nessuna RUN |
| Commit preparation failure certa | RUN conclusa `FAILED` da Run Tracking |
| Commit execution failure certamente non committata | RUN conclusa `FAILED` da Run Tracking |
| Idempotency conflict | RUN conclusa `FAILED` se ancora aperta e alla versione attesa |
| Version conflict / RUN già conclusa | nessuna seconda conclusione; stato persistente prevale |
| Outcome incerto | RUN non conclusa come `FAILED`; richiede riconciliazione |
| Errore Application inatteso prima del write attempt | tentativo di conclusione `FAILED` senza mascherare l'errore primario |
| Errore inatteso dopo l'inizio del write attempt | outcome incerto salvo prova strutturata di rollback certo |

La RUN può restare aperta soltanto quando:

- la finalizzazione FAILED fallisce;
- lo stato è concorrente o già concluso;
- l'esito del commit è incerto.

Il risultato deve dichiararlo esplicitamente.

## 7. Failure lifecycle

Per failure certe senza ORDINI committati, il percorso autorevole minimo è
Run Tracking:

```text
SchedulingRunService.propose_failure()
→ SchedulingRunRepository.complete()
```

`SchedulingRunService.fail_run()` può essere riutilizzato soltanto dopo
emendamento esplicito della sua classificazione legacy: diventa autorevole
esclusivamente per concludere failure operative certe fuori dal commit ORDINI.
Non diventa writer di ORDINI e non compete con il Commit Repository.

La conclusione FAILED:

- usa una transazione Run Tracking separata;
- persiste errori e warning disponibili;
- incrementa la versione una sola volta;
- non inserisce ORDINI, provenance o audit ORDINI;
- non viene tentata se il commit può essere già avvenuto;
- non viene ripetuta automaticamente in caso di conflitto.

L'errore originale non deve essere perso se la finalizzazione FAILED fallisce.
L'outcome espone sia la failure primaria sia la failure di finalizzazione.

## 8. Confine del Commit Repository

`CommitRepository` resta il writer del solo piano validato con completion non
FAILED. Non deve essere forzato a concludere RUN FAILED prive di ORDINI.

Il Commit Repository deve distinguere strutturalmente:

- receipt confermata;
- failure nota e sicuramente non committata;
- outcome incerto.

Non è ammessa classificazione basata sul testo di un'eccezione.

## 9. Clock port

È richiesta una porta Application provider-neutral concettualmente equivalente
a:

```text
Clock.now() -> CurrentSystemDate
```

La porta vive in Application. Il Domain non legge il clock. Bootstrap compone
l'implementazione system clock; i test usano un fake deterministico. Lo stesso
Clock logico viene fornito agli elementi Application/Infrastructure che devono
catturare timestamp del protocollo.

Ogni valore deve essere timezone-aware. Il Clock non fornisce la business date
dello Scheduling.

## 10. Business date

`CURRENT_SYSTEM_DATE` usata da Scheduling resta input semantico esplicito del
caller. Non viene derivata dal Clock runtime.

Questa separazione consente simulazioni, esecuzioni controllate e ripetibilità
senza confondere il tempo di business con l'istante tecnico dell'esecuzione.

## 11. Ownership dei timestamp

| Riferimento | Source | Owner | Momento di cattura |
|---|---|---|---|
| business/current system date | caller | caller | prima dell'invocazione |
| `run_started_at` | Clock | Operational Orchestrator | immediatamente prima dell'apertura RUN |
| `completion_at` | Clock | `ExecuteSchedulingCommit` | dopo Scheduling, quando viene proposta la completion |
| `requested_at` | Clock | `ExecuteSchedulingCommit` | dopo validazione, immediatamente prima della richiesta di commit |
| `commit_completed_at` | Clock | Commit Repository boundary | soltanto dopo conferma del commit fisico |

Deve valere:

```text
run_started_at <= completion_at <= requested_at <= commit_completed_at
```

per un commit confermato. Un outcome incerto può non possedere
`commit_completed_at`.

## 12. Semantica del completamento commit

Il contratto corrente `execute_commit(request, completed_at)` obbliga il caller
a fornire un timestamp prima che il commit sia fisicamente confermato. Questo
impedisce di attribuire a `commit_completed_at` il significato nominale.

Il contratto deve essere emendato in modo che:

- il caller non preveda il timestamp di completamento;
- il repository acquisisca `commit_completed_at` solo dopo `commit()` riuscito;
- una receipt confermata contenga quel timestamp;
- un outcome incerto non inventi il timestamp;
- l'audit transazionale usi un istante pre-commit distinto e acquisito dal
  Clock, senza rinominare tale istante come completamento fisico.

Questa è una modifica semantica dell'Application Commit contract, ma non
richiede DDL.

## 13. Known failure

Sono failure note quando il contratto può provare che il commit non è avvenuto:

- validazione o preparazione prima dell'apertura della transazione di write;
- idempotency conflict rilevato prima del commit;
- RUN assente, già conclusa o in version conflict rilevata prima del commit;
- errore applicativo prima del write attempt;
- errore PostgreSQL con rollback confermato prima di ogni tentativo di commit.

Una failure nota non diventa `RECONCILIATION_REQUIRED`. Può concludere FAILED la
RUN soltanto se la RUN è ancora aperta e alla versione attesa.

## 14. Uncertain outcome

È incerto qualunque errore avvenuto durante o dopo il tentativo di commit per il
quale non esiste prova strutturata dell'esito fisico. Esempi includono perdita
di connessione o risposta durante/attorno a `commit()`.

Regole:

- nessun parsing di messaggi Psycopg;
- nessuna assunzione che l'eccezione equivalga a rollback;
- nessuna conclusione FAILED della RUN;
- nessun secondo commit;
- nessun retry;
- outcome `RECONCILIATION_REQUIRED` restituito al caller.

## 15. Reconciliation model

Il caller deve distinguere senza parsing:

```text
COMMITTED
FAILED
RECONCILIATION_REQUIRED
```

La soluzione minima è un outcome Application strutturato. Non è necessaria una
nuova eccezione come canale principale.

Il contesto di riconciliazione contiene, riusando i modelli esistenti:

- `RunId`;
- correlation ID;
- idempotency keys attese;
- expected record count;
- expected logical row count;
- `requested_at`;
- receipt parziale, solo se realmente disponibile;
- stato RUN noto, se verificato senza deduzione;
- chiavi/ORDINI osservati, solo se una futura riconciliazione li legge.

Non contiene PK interne, SQL o dati provider-specific.

`CommitResult` deve consentire `RECONCILIATION_REQUIRED` senza inventare
`committed_operations` o `commit_completed_at`. Le chiavi riconciliate possono
essere un sottoinsieme realmente provato.

## 16. ExecuteSchedulingCommit result

`ExecuteSchedulingCommit` deve restituire un risultato per `COMMITTED` e
`RECONCILIATION_REQUIRED`.

- con `COMMITTED`, `completed_run` è presente;
- con `RECONCILIATION_REQUIRED`, `completed_run` è assente e il contesto di
  riconciliazione è presente;
- failure certa continua attraverso errori tipizzati verso l'orchestratore, che
  governa la finalizzazione FAILED.

Non è ammesso convertire `RECONCILIATION_REQUIRED` in una generica
`OperationalSchedulingCommitError`.

## 17. Operational result model

Il futuro orchestratore restituisce un solo outcome discriminato con stato
operativo `COMMITTED`, `FAILED` o `RECONCILIATION_REQUIRED`.

Il risultato referenzia, senza duplicarli:

- `RunId`;
- `CommitExecutionContext` o almeno correlation ID;
- `SchedulingResult`, se prodotto;
- `CommitResult`, se prodotto;
- `OpenSchedulingRun` o `CompletedSchedulingRun` secondo lo stato noto;
- errori e warning applicativi;
- failure di finalizzazione RUN, se presente;
- contesto di riconciliazione, se richiesto.

I timestamp provengono dai modelli referenziati e non vengono copiati con
significati differenti.

## 18. Retry policy

Non esiste retry automatico in Application, CLI, Bootstrap o repository.

- nessun retry su CAS Identity;
- nessun retry su idempotency/version conflict;
- nessun retry su failure nota;
- nessun retry su outcome incerto;
- nessun secondo commit;
- un futuro retry umano è ammesso soltanto dopo riconciliazione esplicita.

Questa regola vale anche per failure avvenute prima di qualsiasi scrittura. Il
caller può avviare una nuova esecuzione esplicita, che costituisce una nuova
RUN, non un retry interno trasparente.

## 19. CLI boundary

La futura CLI:

- effettua parsing e validazione sintattica;
- costruisce business date e `CommitExecutionContext`;
- invoca l'Operational Scheduling Orchestrator;
- renderizza testo/JSON;
- mappa l'outcome a exit code.

La CLI non:

- apre direttamente RUN o repository;
- alloca ID;
- cattura timestamp tecnici interni;
- gestisce transazioni;
- conclude RUN;
- interpreta errori PostgreSQL;
- esegue retry;
- riconcilia implicitamente.

## 20. Bootstrap boundary

Bootstrap:

- compone Clock, Identity, Run Tracking, Scheduling, WritePlan, Committer e
  orchestratore operativo;
- espone soltanto un grafo completo o nessun runtime operativo;
- inietta lo stesso writer autorevole nel Committer;
- resta lazy;
- non apre connessioni;
- non orchestra il runtime;
- non decide lifecycle, retry o outcome;
- non costruisce writer Google nel grafo operativo PostgreSQL.

## 21. Error model

Gli errori esistenti restano validi per failure note: Identity, Run Tracking,
WritePlan, Committer e PostgreSQL.

Sono richieste al massimo due nuove strutture concettuali:

1. outcome incerto provider-neutral restituito dal `CommitRepository`;
2. risultato operativo discriminato restituito dall'orchestratore.

Una typed exception può trasportare un errore interno, ma non deve sostituire il
risultato strutturato atteso dal caller. Cleanup e failure di finalizzazione non
devono mascherare l'errore principale.

## 22. Modifiche Application richieste

### Application ports

- aggiungere la porta `Clock`;
- emendare `CommitRepository.execute_commit` affinché non riceva un completion
  timestamp previsto e possa restituire receipt o outcome incerto.

### Committer

- emendare `CommitResult` per rappresentare reconciliation senza timestamp o
  conteggi inventati;
- mappare l'outcome incerto a `RECONCILIATION_REQUIRED`;
- preservare la validazione della receipt confermata.

### Operational Scheduling

- aggiungere l'Operational Scheduling Orchestrator;
- aggiungere input/result provider-neutral;
- fare restituire a `ExecuteSchedulingCommit` il risultato di riconciliazione;
- spostare i capture temporali nei momenti definiti.

### Run Tracking

- riclassificare esplicitamente il percorso di failure come autorevole per
  failure operative certe senza ORDINI committati;
- preservare optimistic version e singolo incremento;
- esporre la failure di finalizzazione nel risultato operativo.

### Bootstrap

- comporre e rendere disponibile il nuovo orchestratore e il Clock;
- non esporre alla CLI la necessità di coordinare servizi intermedi.

Le API correnti di simulazione restano backward compatible. Le firme congelate
del commit richiedono emendamento coordinato e aggiornamento dei relativi test.

## 23. Impatto sui Freeze esistenti

### APPLICATION_ATOMIC_COMMIT_FREEZE

Richiede emendamento semantico circoscritto:

- `fail_run()` non è più soltanto legacy per le failure operative certe;
- `execute_commit(..., completed_at)` cambia ownership temporale;
- `RECONCILIATION_REQUIRED` diventa risultato propagato;
- viene aggiunto l'orchestratore sopra `ExecuteSchedulingCommit`.

Restano invariati writer, atomicità, provenance, idempotenza, actor, audit,
versioning, receipt counts e assenza di retry.

### POSTGRESQL_FOUNDATION_FINAL_FREEZE

Richiede chiarimento compatibile:

- il percorso operativo include apertura/failure RUN e outcome incerto;
- il Bootstrap compone il nuovo orchestratore;
- il writer autorevole e il confine transazionale non cambiano.

## 24. Impatto PostgreSQL

Non sono richiesti:

- nuove tabelle;
- nuove colonne;
- nuovi enum;
- nuove constraint;
- nuove migrazioni.

Sono richieste modifiche di adapter e contratto, non DDL. Le tabelle RUN,
messaggi, ORDINI e audit esistenti sono sufficienti.

## 25. Test obbligatori

### Application

- happy path completo dall'apertura al commit;
- success con warning;
- Scheduling FAILED;
- validation failure;
- preparation failure;
- known commit failure;
- uncertain outcome;
- reconciliation result;
- failure di finalizzazione RUN;
- ordering dei timestamp;
- zero retry.

### Run Tracking

- conclusione FAILED autorevole;
- singolo incremento versione;
- conflitto durante failure completion;
- messaggi error/warning persistiti.

### Committer

- receipt confermata;
- known failure propagata;
- uncertain outcome mappato;
- reconciliation senza timestamp inventato;
- mismatch receipt ancora rifiutato.

### Integration PostgreSQL

- RUN aperta → commit;
- RUN aperta → failure pre-commit → FAILED;
- idempotency conflict → failure nota;
- version conflict → nessuna seconda conclusione;
- double/protocol deterministico per outcome incerto quando il driver reale non
  consente di produrlo in modo affidabile;
- nessun ORDINE parziale e nessun retry.

## 26. Invarianti soggetti a futura Architecture Review

Richiede nuova Architecture Review qualunque modifica a:

- owner dell'apertura RUN;
- distinzione business date/runtime clock;
- momenti di cattura dei timestamp;
- classificazione known/uncertain;
- failure completion della RUN;
- modello di reconciliation;
- retry policy;
- responsabilità CLI/Bootstrap;
- writer autorevole o confine transazionale;
- introduzione di nuovi stati RUN;
- aggiunta di persistenza per outcome/reconciliation.

## 27. Decision matrix

| Voce | Scelta congelata | Contratto impattato |
|---|---|---|
| RUN open owner | Operational Scheduling Orchestrator | nuovo use case Application |
| RUN failure owner | Run Tracking per failure certe | riclassificazione failure path |
| Clock owner | porta Application composta dal Bootstrap | nuova porta |
| Business date | input esplicito caller | invariato |
| `requested_at` | dopo validation, prima della richiesta commit | Operational Scheduling |
| `completion_at` | dopo Scheduling, prima del piano | Operational Scheduling |
| `commit_completed_at` | dopo commit fisico confermato | Commit Repository/receipt |
| Reconciliation | outcome strutturato | Committer e Operational result |
| Known failure | prova strutturata di non-commit | error mapping |
| Uncertain outcome | nessuna prova dell'esito fisico | nuovo outcome provider-neutral |
| Retry | mai automatico | tutti i layer |
| CLI | input/output/exit mapping | boundary |
| Bootstrap | composition only, lazy | boundary |

## 28. Fuori scope

- sintassi e numeri degli exit code CLI;
- environment/production authorization;
- Supabase;
- riconciliazione completa e comandi di recovery;
- daemon, API e scheduler unattended;
- import dati;
- ordini manuali;
- modifiche Domain o DDL;
- reporting Google.

## 29. Conclusione

Il runtime operativo richiede modifiche coordinate a più contratti Application,
ma le decisioni sono completamente determinate da questo Freeze. Non è
necessaria una review Domain o schema. L'implementazione deve procedere senza
riaprire il writer PostgreSQL, l'atomicità del commit o gli invarianti già
congelati.
