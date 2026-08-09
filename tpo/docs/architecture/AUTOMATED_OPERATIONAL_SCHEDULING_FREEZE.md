# AUTOMATED OPERATIONAL SCHEDULING FREEZE

## 1. Stato

**Stato:** FINAL ARCHITECTURE FREEZE

**Ambito:** adapter automatico V1 del Runtime Operativo PostgreSQL

**Baseline:** `1531802`

**Fonti normative:**

- `AUTOMATED_OPERATIONAL_SCHEDULING_ARCHITECTURE_REVIEW.md`;
- `OPERATIONAL_RUNTIME_FINAL_FREEZE.md`;
- `CLI_OPERATIONAL_ADAPTER_FREEZE.md`;
- `APPLICATION_OPERATIONAL_ENTRYPOINT_FREEZE.md`.

Il presente documento consolida esclusivamente le decisioni approvate per il
primo scheduler automatico. Non modifica Runtime, Domain, Application,
Infrastructure, Bootstrap, CLI o Freeze precedenti. In caso di discrepanza sui
contratti già esistenti prevalgono i rispettivi Freeze originari.

## 2. Scope

Il Freeze comprende:

- ownership dell'automazione;
- piattaforma macOS V1;
- frequenza e orario;
- business date e business time;
- identity unattended;
- conferma non interattiva;
- policy per esecuzioni mancate;
- protezione da sovrapposizioni;
- policy degli outcome;
- logging locale e retention;
- confine del provisioning dei segreti;
- escalation del primo deployment;
- compatibilità con la CLI manuale;
- contratto minimo dei test futuri.

L'automazione è un adapter esterno al Core. Non introduce un nuovo runtime, un
nuovo outcome, un nuovo writer, un nuovo comando operativo o una nuova
semantica di Scheduling.

## 3. Runtime automatico

Il percorso automatico ufficiale è:

```text
macOS launchd LaunchAgent
↓
adapter automatico V1
↓
tpo schedule execute
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

L'adapter automatico invoca esclusivamente il comando CLI operativo già
congelato e validato. Non importa né chiama direttamente:

- `OperationalSchedulingEntryPoint`;
- `OperationalSchedulingOrchestrator`;
- `RunScheduling`;
- `ExecuteSchedulingCommit`;
- `ApplicationCommitter`;
- Committer o Commit Repository;
- repository;
- connection factory;
- PostgreSQL.

Il Core non diventa un daemon. Non esiste un runtime scheduler-only.

## 4. Platform

La piattaforma ufficiale V1 è **macOS launchd** in modalità **LaunchAgent**.

La scelta è congelata perché:

- l'esecuzione appartiene al contesto utente;
- non sono richiesti privilegi di sistema;
- `launchd` è il meccanismo nativo macOS;
- gestione del job, login e restart sono integrate nel sistema operativo;
- il Runtime Operativo corrente è già eseguito nel contesto utente.

`cron` non è il meccanismo ufficiale V1. `LaunchDaemon` non appartiene al
deployment V1. Il futuro file plist e l'adapter concreto appartengono a uno
sprint di implementazione successivo.

## 5. Schedule

È autorizzata una sola esecuzione automatica ordinaria al giorno.

La pianificazione ufficiale è:

```text
06:00 Atlantic/Canary
```

Non viene avviata una seconda RUN automatica ordinaria nella stessa giornata.
Una esecuzione manuale autorizzata non cambia la frequenza automatica e non
costituisce una seconda scadenza dello scheduler.

L'orario `06:00` è la decisione della pianificazione unattended. Non modifica
gli orari di generazione dei PROGRAMMI e non viene dedotto da essi.

## 6. Business time

L'esecuzione ordinaria delle `06:00 Atlantic/Canary` costruisce:

- `--business-date` con la data locale `Atlantic/Canary` dell'esecuzione
  pianificata, nel formato `YYYY-MM-DD`;
- `--business-time 06:00`.

Il riferimento viene costruito nel boundary automatico e passato
esplicitamente alla CLI. Non usa UTC implicita, mezzanotte, data o ora del
Clock Application, timezone non verificata o default.

Business date e business time mantengono la stessa semantica del comando
manuale. L'adapter non bypassa il Clock Application: il riferimento di
business resta distinto dai timestamp tecnici `run_started_at`,
`completion_at`, `requested_at` e `commit_completed_at`.

## 7. Identity

L'identità tecnica dedicata V1 è:

```text
towerpower-scheduler
```

Ogni esecuzione automatica passa esplicitamente:

```text
--identity towerpower-scheduler
```

`towerpower-scheduler` è una recognized operational identity
provider-neutral, opaca e dedicata. Non è:

- un `ActorId` costruito dal launcher;
- una credenziale;
- authentication;
- authorization;
- utente del sistema operativo;
- hostname;
- valore dedotto o fallback.

L'`OperationalSchedulingEntryPoint` continua a costruire internamente
`ActorId`, reason applicativa, correlation ID e `CommitExecutionContext`.

## 8. Confirmation

Ogni esecuzione automatica autorizzata include esplicitamente:

```text
--confirm
```

La conferma è non interattiva ed è completata dal caller automatico prima
dell'invocazione Application. Non esistono prompt, input da terminale,
domande `YES/NO`, `--force` o conferme implicite.

L'assenza di `--confirm` produce `OPERATION_INPUT_INVALID` prima di allocazione
RunId, apertura RUN o Scheduling.

## 9. Missed execution

Non esiste catch-up automatico.

Se il Mac o il processo era spento, il LaunchAgent non era disponibile oppure
il job non è partito alla scadenza prevista:

- non viene avviata una esecuzione retroattiva automatica;
- non viene ricostruita la RUN mancata;
- non viene usata una business reference retroattiva;
- non viene eseguito retry immediato;
- l'evento viene registrato e segnalato operativamente;
- un eventuale recupero avviene esclusivamente mediante comando manuale
  autorizzato.

Il comportamento nativo di wake o coalescing della piattaforma non autorizza
un catch-up. L'adapter V1 deve rispettare la policy di mancata esecuzione e non
trasformare una scadenza trascorsa in una nuova invocazione automatica. La
protezione concreta appartiene allo sprint di implementazione.

La capacità dello Scheduling Engine di elaborare occorrenze ancora operative
non equivale al recupero della RUN automatica mancata.

## 10. Single-run protection

La protezione è distinta su quattro livelli.

### A. Process-level overlap

L'adapter V1 impedisce esternamente al Core l'avvio di un secondo processo
automatico concorrente. Esiste una sola definizione LaunchAgent ufficiale per
la funzione e non vengono attivati in parallelo cron, una seconda plist o un
secondo launcher per la medesima pianificazione.

L'implementazione concreta della protezione appartiene allo sprint successivo.
Non viene introdotto alcun lock Python nel Core.

### B. Identity CAS

Il Runtime usa il compare-and-set PostgreSQL delle sequenze tipizzate e
versionate. CAS preserva l'unicità delle allocazioni concorrenti senza retry.

### C. RUN optimistic concurrency

Il commit usa lock PostgreSQL, stato aperto ed `expected_version`. Una RUN non
viene conclusa due volte e un conflitto non viene ritentato automaticamente.

### D. Business idempotency

Scheduling applica il controllo preliminare e PostgreSQL conserva il vincolo
univoco definitivo sulle chiavi idempotenti. La stessa occorrenza non produce
due ORDINI autorevoli.

I livelli B, C e D proteggono integrità e atomicità, ma non sostituiscono la
protezione process-level. Sono vietate doppie esecuzioni automatiche
intenzionali, secondi commit e retry automatici.

## 11. Outcome policy

| Esito | Policy automatica V1 |
|---|---|
| `COMMITTED` / exit `0` | registra il risultato, conclude normalmente, nessuna azione ulteriore |
| `FAILED` / exit `1` | registra, esegue escalation operativa, nessun retry |
| `INPUT_INVALID` / exit `2` | classifica errore di configurazione del launcher, registra, esegue escalation, nessun retry |
| `RUNTIME_UNAVAILABLE` / exit `3` | registra e termina; nessun retry immediato; attende la successiva scadenza ordinaria |
| `RECONCILIATION_REQUIRED` / exit `4` | registra, escalation prioritaria, nessun retry, nessuna seconda esecuzione automatica, conserva il contesto pubblico |
| `INTERNAL_ERROR` / exit `5` | registra, esegue escalation operativa, nessun retry |

Nessun esito autorizza fallback Google, recovery automatico, nuova RUN
immediata, parsing di eccezioni provider-specific o modifica della
classificazione prodotta dalla CLI.

Con `RECONCILIATION_REQUIRED` l'adapter conserva, quando pubblicamente
disponibili, RunId, correlation ID, requested_at, idempotency keys e conteggi
attesi. Non consulta direttamente PostgreSQL e non deduce l'esito fisico.

## 12. Logging

Il launcher automatico produce log locali espliciti nella directory:

```text
runtime/logs/
```

La directory è relativa alla root applicativa operativa. I log registrano:

- timestamp dell'invocazione nella timezone `Atlantic/Canary`;
- identificativo del LaunchAgent o dell'adapter;
- exit code;
- stdout sanitizzato;
- stderr sanitizzato;
- RunId, quando presente;
- correlation ID, quando pubblico nell'outcome disponibile;
- stato finale, quando disponibile.

I log non contengono mai:

- password;
- DSN o URL PostgreSQL;
- segreti;
- SQL;
- `technical_cause`;
- traceback provider-specific non autorizzato;
- cause tecniche non esposte dal boundary pubblico;
- PK interne.

Il launcher non ottiene dati tramite attributi privati, accesso diretto al
database o ricostruzione di informazioni non renderizzate dalla CLI.

## 13. Retention

La retention dei log automatici è di **30 giorni**.

I file oltre la retention vengono rimossi dal meccanismo esterno di gestione
dei log. La rotazione e la rimozione non appartengono al Runtime Operativo e
non modificano dati PostgreSQL, audit, RUN o outcome.

La retention non autorizza la conservazione di segreti o dati vietati durante
il periodo consentito.

## 14. Secrets

Il processo LaunchAgent riceve configurazione PostgreSQL e segreti mediante
environment esplicito del servizio o meccanismo equivalente approvato dal
deployment.

Il contratto congela:

- uso esclusivo delle configurazioni PostgreSQL già definite dal Runtime;
- nessuna lettura implicita di `.env.local`;
- nessun segreto hardcoded nel repository;
- nessun segreto negli argomenti del comando;
- nessun DSN o segreto nei log;
- nessun segreto nel plist versionato;
- nessuna dipendenza dalla shell interattiva o da environment ereditato
  casualmente.

Il valore segreto concreto e il provisioning locale non vengono versionati.
Il deployment fornisce i valori al processo con permessi coerenti con il
contesto utente del LaunchAgent. Il contratto di configurazione resta separato
dai dati locali segreti.

## 15. Escalation

Nel primo deployment l'escalation obbligatoria consiste nella registrazione
locale esplicita e riconoscibile dell'esito che richiede intervento.

Richiedono escalation:

- `FAILED`;
- `INPUT_INVALID`;
- `RECONCILIATION_REQUIRED`, con priorità;
- `INTERNAL_ERROR`.

`RUNTIME_UNAVAILABLE` viene registrato e termina senza retry immediato; il
processo attende la successiva scadenza ordinaria e l'eventuale intervento è
manuale. Anche una esecuzione mancata viene registrata come evento operativo
da segnalare.

Il canale di notifica automatica non appartiene all'adapter V1. Non vengono
inviate email o notifiche Slack, Telegram o equivalenti. Escalation non
significa retry, recovery, riconciliazione o seconda esecuzione.

## 16. Manual compatibility

La CLI manuale resta invariata.

Scheduler e operatore manuale attraversano esattamente lo stesso comando:

```text
tpo schedule execute
```

Entrambi usano gli stessi argomenti, la stessa validazione, lo stesso
`OperationalSchedulingEntryPoint`, lo stesso Runtime Application, lo stesso
writer PostgreSQL, gli stessi outcome e gli stessi exit code.

Non viene introdotto un flag unattended, un comando scheduler-specifico, una
factory alternativa, un runtime parallelo o un fallback.

## 17. Test contract

Il futuro adapter automatico deve dimostrare almeno:

- una sola pianificazione giornaliera alle `06:00 Atlantic/Canary`;
- business date locale corretta;
- `--business-time 06:00`;
- `--identity towerpower-scheduler`;
- presenza esplicita di `--confirm`;
- una sola invocazione della CLI ufficiale;
- percorso esclusivo attraverso `tpo schedule execute`;
- gestione `COMMITTED` senza ulteriori azioni;
- gestione `FAILED` senza retry;
- gestione `RECONCILIATION_REQUIRED` senza retry o seconda esecuzione;
- gestione `INTERNAL_ERROR` senza retry;
- gestione `RUNTIME_UNAVAILABLE` fino alla scadenza ordinaria successiva;
- gestione `INPUT_INVALID` come errore di configurazione;
- nessun catch-up automatico;
- protezione process-level esterna al Core;
- nessun lock Python nel Core;
- logging sanitizzato in `runtime/logs/`;
- retention di 30 giorni;
- nessun segreto nel plist versionato o nei log;
- nessun accesso diretto ad Application o Infrastructure;
- nessuna costruzione o fallback Google;
- nessuna regressione della CLI manuale.

I test non aprono percorsi alternativi, non interpretano errori PostgreSQL e
non modificano i contratti Runtime congelati.

## 18. Fuori scope

Restano esplicitamente fuori scope:

- daemon nel Core;
- API scheduler;
- cron V1;
- LaunchDaemon;
- catch-up automatico;
- retry automatici;
- notifica email, Slack, Telegram o equivalente;
- recovery automatico;
- reconciliation automatica;
- scheduler distribuito;
- high availability;
- Supabase production;
- deployment multi-host;
- UI scheduler;
- modifiche a Runtime, Domain, Application, PostgreSQL, Bootstrap o CLI.

## 19. Decision Matrix

| Area | Decisione congelata |
|---|---|
| owner automazione | adapter esterno al Core |
| platform V1 | macOS `launchd` |
| modalità | LaunchAgent nel contesto utente |
| cron | non ufficiale V1 |
| frequenza | una esecuzione automatica al giorno |
| orario | `06:00 Atlantic/Canary` |
| seconda RUN ordinaria | vietata nella stessa giornata |
| business date | data locale `Atlantic/Canary` dell'esecuzione pianificata |
| business time | `06:00` esplicito |
| identity | `towerpower-scheduler` |
| confirmation | `--confirm` esplicito, nessun prompt |
| comando | esclusivamente `tpo schedule execute` |
| missed execution | nessun catch-up automatico; recupero soltanto manuale |
| overlap process-level | protezione esterna al Core, implementazione nello sprint successivo |
| integrità concorrente | Identity CAS, RUN optimistic concurrency, idempotenza business |
| retry | vietato |
| fallback | vietato, incluso Google |
| logging | locale in `runtime/logs/`, sanitizzato |
| retention | 30 giorni |
| escalation V1 | logging locale obbligatorio; notifiche automatiche fuori scope |
| secret provisioning | environment esplicito del servizio o equivalente deployment; valori locali non versionati |
| CLI manuale | invariata e sul medesimo percorso |

## 20. Regola di modifica futura

Ogni modifica a piattaforma, modalità LaunchAgent, frequenza, orario, timezone,
identity, conferma, missed execution, overlap protection, retry, outcome
policy, logging, retention, secret boundary, escalation, comando ufficiale o
compatibilità manuale richiede una nuova Architecture Review.

L'implementazione puramente meccanica dell'adapter, della plist e dei test può
procedere senza modificare questo Freeze soltanto se ne rispetta integralmente
le decisioni.

Nessuna implementazione può modificare Runtime, Application o CLI per adattarli
alle necessità di `launchd`. È l'adapter automatico che deve conformarsi al
contratto operativo esistente.

## 21. Conclusione

L'architettura dell'Automated Operational Scheduling V1 è congelata.

Un solo LaunchAgent macOS avvia una sola esecuzione giornaliera alle
`06:00 Atlantic/Canary`, usando esclusivamente `tpo schedule execute` con
business date locale esplicita, business time `06:00`, identity
`towerpower-scheduler` e `--confirm`.

Il sistema non introduce daemon nel Core, catch-up, retry, secondo runtime,
secondo writer o fallback. Logging locale sanitizzato, retention di 30 giorni,
protezione esterna dalle sovrapposizioni e separazione dei segreti completano
il confine V1 senza modificare il Runtime Operativo PostgreSQL congelato.
