# POSTGRESQL FOUNDATION FINAL FREEZE

**Stato:** FINAL ARCHITECTURE FREEZE  
**Baseline:** PostgreSQL Foundation conclusa a partire da `1bcbc18`  
**Fonti normative:** `POSTGRESQL_PHYSICAL_SCHEMA.md`,
`APPLICATION_ATOMIC_COMMIT_FREEZE.md`, `ORDINI.md`, `SCHEDULING_ENGINE.md` e
`PERSISTENCE_ARCHITECTURE_REVIEW.md`.

## 1. Stato del Freeze

Il capitolo PostgreSQL Foundation è concluso. La baseline architetturale qui
descritta è congelata.

Ogni modifica futura che alteri i contratti o gli invarianti descritti in
questo documento richiede Architecture Review.

## 2. Scope incluso

Il freeze include esclusivamente i componenti implementati e verificati:

- `PostgreSQLSettings`;
- `PostgreSQLConnectionFactory`;
- `PostgreSQLHealthCheck`;
- configurazione programmatica Alembic;
- migrazione `20260804_0001_postgresql_foundation`;
- migrazione `20260806_0002_order_commit_schema`;
- `PostgreSQLPersistentIdRepository`;
- `PostgreSQLSchedulingRunRepository`;
- `PostgreSQLOrdineRepository`, read-only;
- `PostgreSQLVersionedProgrammaFornituraRepository`, read-only;
- `PostgreSQLWritePlanValidationRepository`, read-only;
- `PostgreSQLCommitRepository`;
- `ApplicationCommitter`;
- `ExecuteSchedulingCommit`;
- wiring PostgreSQL nel Bootstrap.

## 3. Percorso operativo autorevole

Il percorso operativo autorevole è:

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

`RunScheduling` resta puro rispetto alla persistenza di scrittura. Il
Bootstrap compone le dipendenze ma non orchestra il caso d'uso.
`ExecuteSchedulingCommit` è l'orchestratore Application. Il runtime non chiama
direttamente il writer.

## 4. Writer autorevole

`PostgreSQLCommitRepository` è l'unico writer operativo autorevole.

- non esiste dual-write;
- non esiste fallback automatico PostgreSQL → Google;
- `GoogleSheetsCommitRepository` resta legacy, compatibilità e test;
- senza PostgreSQL il commit operativo non è disponibile;
- senza PostgreSQL la simulazione può restare disponibile;
- nessun backend alternativo appartiene al grafo operativo congelato.

## 5. Confine transazionale

Ogni commit operativo usa una connessione PostgreSQL, una transazione e un
solo commit finale. Nella stessa transazione avvengono, nell'ordine:

1. lock e verifica della RUN;
2. pre-check delle chiavi idempotenti;
3. lookup di CLIENTI, VARIETÀ, PROGRAMMI e locator delle righe PROGRAMMA;
4. inserimento delle testate ORDINI;
5. inserimento delle RIGHE_ORDINE;
6. inserimento della provenance;
7. audit INSERT degli ORDINI;
8. completamento versionato della RUN;
9. inserimento dei RUN_MESSAGGI;
10. audit RUN `STATE_TRANSITION`;
11. costruzione della receipt;
12. commit della transazione.

Qualunque errore produce rollback totale. Non esiste retry automatico.

## 6. RUN ownership

- la RUN resta aperta fino al commit atomico;
- `SchedulingRunService.propose_completion()` non persiste;
- `PostgreSQLCommitRepository` conclude la RUN nella transazione del commit;
- il controllo ottimistico usa `version` ed `expected_version`;
- il writer acquisisce `SELECT ... FOR UPDATE` sulla RUN;
- una RUN già completata non viene riaperta né completata una seconda volta;
- `CompletedSchedulingRun` viene materializzata soltanto dopo conferma
  `COMMITTED`.

## 7. ORDINI

`tipo_creazione` è esplicito e non viene inferito.

Nel percorso operativo Scheduling ogni ORDINE è `AUTOMATICO` e richiede:

- `run_id`;
- `programma_fornitura_id`;
- `data_consegna_prevista`;
- `chiave_idempotenza`;
- almeno una provenance per ogni RIGA_ORDINE.

Gli ORDINI `MANUALE` restano fuori dal percorso Scheduling congelato.

## 8. Provenance

Il locator provider-neutral congelato è:

```text
programma_fornitura_id
+ programma_version
+ programma_line_position
+ order_line_position
```

L'Application non espone PK interne PostgreSQL e non usa numeri riga Google.
Non esiste fallback basato su VARIETÀ, quantità o altre uguaglianze non
identificative. Infrastructure risolve il locator alle chiavi fisiche soltanto
all'interno della transazione.

## 9. Idempotenza

L'idempotenza è protetta da due livelli complementari:

- pre-check transazionale sulle chiavi del piano;
- vincolo `UNIQUE` definitivo su `ordini.chiave_idempotenza`.

Una collisione concorrente viene classificata come conflitto di chiave
esistente. Non viene eseguito retry. Il tentativo perdente subisce rollback
totale, inclusi ORDINI, righe, provenance, RUN e audit.

## 10. Audit

Il commit persiste:

- un audit `INSERT` per ogni ORDINE;
- come ultimo evento logico, un audit RUN `STATE_TRANSITION`.

`actor`, `reason` e `correlation_id` provengono dal
`CommitExecutionContext` esplicito. I payload sono quelli congelati da
`APPLICATION_ATOMIC_COMMIT_FREEZE.md` e non espongono PK interne. Un rollback
elimina anche ogni audit non committato.

## 11. Timestamp

I tre riferimenti temporali hanno semantiche distinte e non intercambiabili:

- `CommitRequest.requested_at` → `ordini.created_at`;
- `SchedulingRunCompletion.completed_at` → conclusione semantica della RUN;
- `execute_commit(completed_at)` → `commit_completed_at` della receipt.

Nessun clock implicito appartiene all'orchestratore Application.

## 12. Receipt

La semantica dei conteggi è congelata:

- `expected_record_count`: numero di testate ORDINE attese;
- `expected_logical_row_count`: numero di righe logiche del piano;
- `appended_physical_row_count`: numero di `righe_ordine` realmente
  persistite;
- `CommitResult.committed_operations`: deriva da
  `appended_physical_row_count`.

Una receipt incompatibile con il piano validato viene rifiutata.

## 13. Repository read-only

Sono read-only:

- `PostgreSQLOrdineRepository`;
- `PostgreSQLVersionedProgrammaFornituraRepository`;
- `PostgreSQLWritePlanValidationRepository`.

Questi adapter non espongono né eseguono `INSERT`, `UPDATE` o `DELETE`. Le loro
operazioni terminano con cleanup conservativo della connessione.

## 14. Bootstrap

Il Bootstrap è lazy:

- nessuna connessione viene aperta durante la costruzione;
- il container espone la stessa istanza `PostgreSQLCommitRepository` iniettata
  nell'`ApplicationCommitter`;
- lo stesso `ApplicationCommitter` è iniettato in
  `ExecuteSchedulingCommit`;
- `ExecuteSchedulingCommit` è disponibile soltanto quando il grafo PostgreSQL
  completo è disponibile;
- senza PostgreSQL, repository di commit, committer e orchestratore operativo
  sono assenti;
- non viene costruito un orchestratore parziale.

## 15. Configurazione e sicurezza

- nessuna connessione avviene all'import;
- `.env.local` non viene letto implicitamente;
- non esiste selezione automatica di Supabase;
- segreti e password non vengono esposti in `repr` o errori applicativi;
- SSL e timeout seguono esclusivamente `PostgreSQLSettings`;
- i test reali richiedono `TPO_TEST_DATABASE_URL` e un database il cui nome
  contenga `test`.

## 16. Migrazioni

La migrazione `20260804_0001_postgresql_foundation` crea la foundation runtime:
schema, enum runtime, sequenze identificative, RUN, messaggi e log.

La migrazione `20260806_0002_order_commit_schema` crea il perimetro atomico:

- CLIENTI;
- VARIETÀ;
- PROGRAMMI_FORNITURA;
- versioni e righe PROGRAMMA;
- giorni PROGRAMMA;
- ORDINI;
- RIGHE_ORDINE;
- provenance;
- audit.

Upgrade e downgrade seguono l'ordine delle dipendenze. Il lifecycle di test
non usa `DROP SCHEMA ... CASCADE` né cleanup distruttivo di oggetti estranei.
Ogni modifica futura dello schema richiede una nuova migrazione versionata;
le migrazioni congelate non vengono riscritte.

## 17. Concorrenza

Le prove reali concluse coprono:

- CAS concorrente di Identity;
- completamento concorrente di Run Tracking;
- commit concorrenti del `PostgreSQLCommitRepository`;
- Operational Scheduling concorrente attraverso Bootstrap e orchestratore.

Gli invarianti dimostrati sono:

- al massimo un commit tra tentativi incompatibili;
- conflitto di versione della RUN;
- conflitto idempotente definitivo;
- uso di connessioni concorrenti e lock PostgreSQL reali;
- nessun dato parziale;
- nessun audit o provenance orfano.

La sincronizzazione dei test è deterministica e non usa attese temporali
arbitrarie.

## 18. Evidenza test finale

La baseline finale è stata verificata con:

```text
PostgreSQL integration:              13 passed
PostgreSQL Infrastructure + Bootstrap: 197 passed
Core:                                969 passed
git diff --check:                    success
```

I test integration sono stati eseguiti contro PostgreSQL 17 locale dedicato
ai test, con SSL attivo. Nessuna credenziale o DSN appartiene a questo freeze.

## 19. Fuori scope

Restano esplicitamente fuori da questo freeze:

- CLI operativa di scrittura;
- Supabase production;
- deployment production;
- backup e restore;
- monitoring e observability avanzata;
- import legacy;
- ORDINI manuali operativi;
- UI;
- amministrazione;
- sincronizzazione bidirezionale Google/PostgreSQL;
- future nuove entità di dominio.

## 20. Regola di modifica futura

Richiede Architecture Review ogni modifica che alteri:

- writer autorevole;
- confine transazionale;
- schema fisico congelato;
- provenance;
- idempotenza;
- lifecycle RUN;
- audit contract;
- receipt semantics;
- backend selection;
- dual-write o fallback;
- orchestrazione Application.

Le correzioni di bug che preservano integralmente questi invarianti possono
procedere tramite Code Review ordinaria.
