# APPLICATION ATOMIC COMMIT FREEZE

**Stato:** APPLICATION ATOMIC COMMIT FREEZE v1.0

## 1. Scopo

Questo documento congela il confine applicativo del commit atomico PostgreSQL del Tower Power Operations prima dell'implementazione delle migrazioni operative e del `PostgreSQLCommitRepository`.

Il Freeze definisce esclusivamente responsabilità, flusso, ownership dei dati e invarianti già presenti nei contratti applicativi approvati. Non definisce SQL, DDL, migrazioni, adapter provider-specific, configurazione cloud o interfaccia utente. Non autorizza scritture reali o di produzione.

## 2. Sorgente autorevole

PostgreSQL è la sorgente autorevole dei dati persistenti del runtime PostgreSQL. Google Sheets è una destinazione di reporting oppure un percorso legacy separato: non è il writer del runtime PostgreSQL e non partecipa alla sua transazione autorevole.

Nessun adapter può introdurre un secondo write path autorevole, un dual-write sincrono o una seconda fonte di verità. Gli output Google Sheets devono essere derivati, rigenerabili e separati dal commit PostgreSQL.

## 3. Ciclo della RUN

Il ciclo applicativo distingue tre modelli immutabili:

- `OpenSchedulingRun` rappresenta la RUN persistita, ancora aperta, identificata da `run_id`, `started_at`, `simulation` e `version`;
- `SchedulingRunCompletion` rappresenta una proposta provider-neutral e non persistita di conclusione, con `expected_version`, stato finale, timestamp, contatori e messaggi;
- `CompletedSchedulingRun` rappresenta la RUN conclusa dopo il commit autorevole.

Una `SchedulingRunCompletion` non equivale a una conclusione già registrata. La RUN resta aperta fino al commit autorevole. Dopo il commit, la proposta può materializzare `CompletedSchedulingRun` tramite `to_completed_run()`; la versione finale è `expected_version + 1`.

`SchedulingRunService.complete_run()` e `SchedulingRunService.fail_run()` costituiscono il percorso legacy: materializzano e persistono direttamente la conclusione tramite `SchedulingRunRepository.complete()`. Non appartengono al runtime atomico PostgreSQL e non devono essere collegati insieme al nuovo writer autorevole.

## 4. Flusso autorevole

Il flusso congelato è:

```text
OpenSchedulingRun
→ SchedulingResult
→ SchedulingRunCompletion
→ WritePlan
→ ValidatedWritePlan
→ CommitRequest
→ ApplicationCommitter
→ CommitRepository.execute_commit()
→ CommitExecutionReceipt
→ CommitResult
→ CompletedSchedulingRun
```

I punti del flusso hanno le responsabilità seguenti:

1. `SchedulingRunService.propose_completion()` o `propose_failure()` costruisce la proposta senza persisterla.
2. `WritePlanBuilder` verifica la coerenza tra RUN, risultato, proposta, record, provenance, contatori e chiavi e costruisce il `WritePlan`.
3. `WritePlanValidator` esegue la validazione pre-commit read-only e produce il `ValidatedWritePlan` con prove strutturate.
4. `CommitRequest` trasporta al confine di commit il piano validato e la proposta di conclusione.
5. `ApplicationCommitter.commit()` invoca una sola volta `CommitRepository.execute_commit()` senza retry.
6. Il futuro repository PostgreSQL esegue in una sola transazione la persistenza di ORDINI, righe, provenance, messaggi e conclusione RUN.
7. `CommitExecutionReceipt` descrive l'esecuzione fisica e la riconciliazione; `ApplicationCommitter` ne verifica la coerenza e produce `CommitResult`.
8. Soltanto dopo un commit autorevole confermato, `SchedulingRunCompletion.to_completed_run()` materializza la rappresentazione applicativa conclusa.

La materializzazione finale è applicativa e non autorizza una seconda scrittura della RUN.

## 5. Ownership dei dati

### `run_id`

`run_id` appartiene al contesto RUN, allo `SchedulingResult` e al `WritePlan`. Non è duplicato in `ScheduledOrderRecord`; il futuro writer lo associa agli ORDINI usando il contesto del commit.

### `expected_version`

`expected_version` appartiene a `SchedulingRunCompletion` ed è esposto da `CommitRequest.expected_version`. Il repository lo verifica senza ricalcolarlo o sostituirlo.

### Timestamp

Il `completed_at` della RUN appartiene alla proposta di conclusione. Non è generato dal repository. Anche il timestamp di completamento dell'operazione di commit è fornito dall'Application a `ApplicationCommitter.commit()` e deve coincidere con la ricevuta; l'Infrastructure non inventa timestamp applicativi.

### `simulation`

`simulation` deve coincidere tra `OpenSchedulingRun`, `SchedulingResult`, `SchedulingRunCompletion` e piano. Una simulazione non può produrre un piano persistente né un commit autorevole.

### Stato finale

Lo stato finale è fornito dalla proposta. È coerente con lo `SchedulingResult` e non viene dedotto, corretto o inventato dall'Infrastructure.

### Tipo di creazione ORDINE

`OrdineCreationType` distingue esplicitamente `AUTOMATICO` e `MANUALE`. Non possiede un default e non viene dedotto da RUN, PROGRAMMA, chiave idempotente, provenance o adapter.

Il percorso autorevole Scheduling → WritePlan → Commit contiene esclusivamente ORDINI `AUTOMATICO`. Ogni record richiede PROGRAMMA_FORNITURA, data prevista, chiave idempotente non vuota e provenance completa; il `run_id` appartiene al contesto del piano e viene associato dal writer.

Gli ORDINI `MANUALE` appartengono a un futuro caso d'uso separato: non attraversano `ScheduledOrderRecord`, WritePlan o CommitRepository dello Scheduling, non riferiscono PROGRAMMI, non usano la chiave idempotente dello Scheduling e non possiedono provenance. La data prevista è facoltativa.

Importazione e correzione sono processi, non valori di `OrdineCreationType`, e non possono trasformare il tipo dopo la registrazione.

### Contatori

I contatori derivano dallo `SchedulingResult`, sono verificati durante la costruzione e validazione del piano e vengono persistiti nel commit della RUN.

### Warning ed errori

Warning ed errori sono tuple ordinate, devono rispettare gli invarianti di `RunState` e vengono conservati senza deduplicazione, riordinamento o invenzione da parte del repository.

## 6. Programmi versionati

Il percorso autorevole usa:

- `VersionedProgrammaFornitura`, snapshot applicativo di una versione positiva del PROGRAMMA;
- `VersionedProgramLine`, locator di una riga con posizione autorevole positiva;
- `OrderLineProvenance`, locator provider-neutral dell'origine di una riga ORDINE.

Versione e posizione sono dati autorevoli. Non sono ammessi fallback, versioni predefinite, deduzioni da timestamp, ordine di lettura o indici occasionali. Le PK interne PostgreSQL restano nell'Infrastructure e non escono come identità applicative.

Il percorso non versionato è ammesso esclusivamente nella simulazione legacy esplicitamente supportata. Non può essere usato per generare un commit autorevole.

## 7. Provenance

Il locator applicativo congela i campi:

- `ProgrammaFornituraId`;
- `programma_version`;
- `programma_line_position`;
- `order_line_position`.

Ogni riga di ORDINE automatico richiede almeno un'origine. Origini multiple sono conservate. La provenance non può essere ricostruita confrontando varietà e quantità; la posizione si riferisce alla versione autorevole del PROGRAMMA.

Una riga di ORDINE manuale non può possedere provenance.

Una provenance incompleta, orfana, appartenente a un altro PROGRAMMA, duplicata o priva di ordine stabile non può superare costruzione e validazione del piano. Non è ammessa deduplicazione silenziosa.

## 8. Ordine Repository

`ScheduledOrderReadRepository` è la porta read-only del percorso autorevole. Espone la lista degli ORDINI necessaria allo Scheduling; gli adapter possono inoltre offrire lookup e verifiche preliminari delle chiavi idempotenti senza acquisire responsabilità di scrittura.

`OrdineRepository` è la porta legacy che conserva `add_scheduled_orders()` per adapter e percorsi storici. Non è la porta del writer PostgreSQL autorevole.

`PostgreSQLOrdineRepository` è esclusivamente read-only: lista record, esegue lookup e verifica preliminarmente chiavi idempotenti. Non esegue `INSERT`, `UPDATE`, `DELETE` né commit di scrittura.

## 9. Write Plan

`WritePlan` trasporta:

- `run_id`;
- `SchedulingRunCompletion` nel percorso autorevole;
- `ScheduledOrderRecord` e relative righe;
- provenance;
- conteggi attesi dei record e delle righe logiche;
- chiavi idempotenti;
- warning;
- timestamp applicativi.

Gli invarianti congelati richiedono RUN, modalità, stato finale, warning e contatori coerenti; provenance completa; chiavi non vuote, ordinate come i record e non duplicate; conteggi corrispondenti al contenuto. Nessun piano persistente è ammesso per `simulation=True` e nessun piano ORDINI è ammesso per una RUN o uno `SchedulingResult` `FAILED`.

Il supporto a `CompletedSchedulingRun` nel builder è un adattamento legacy: viene convertito in una proposta con `expected_version = version - 1` e non modifica il flusso autorevole.

## 10. Validated Write Plan

La validazione:

- non effettua scritture;
- non sostituisce i vincoli PostgreSQL;
- verifica target, nome schema e versione schema;
- verifica preliminarmente le chiavi già esistenti;
- ricontrolla record, conteggi, identità e provenance;
- conserva prove strutturate in `WritePlanValidationSnapshot`;
- produce un `ValidatedWritePlan` immutabile;
- precede sempre il commit autorevole.

La verifica preliminare non garantisce da sola l'idempotenza concorrente e può diventare obsoleta prima della transazione.

## 11. Commit Request

`CommitRequest` espone almeno:

- `ValidatedWritePlan` tramite `validated_plan`;
- `requested_at`;
- `SchedulingRunCompletion` tramite `completion`;
- `expected_version` tramite la proprietà omonima.

Nel percorso autorevole `completion` ed `expected_version` non sono `None`. Il valore `None` identifica soltanto il percorso legacy compatibile.

Il contratto consegna al repository identità RUN, versione attesa, stato finale, modalità, timestamp, contatori, warning/errori, ORDINI, righe, provenance e chiavi idempotenti. Nessuno di questi dati viene inventato dall'Infrastructure.

## 12. Commit Repository

`CommitRepository` è la porta dell'unico writer autorevole PostgreSQL. `prepare_commit()` appartiene al protocollo di preparazione già esistente e non applica effetti persistenti al target; il write path autorevole usa `execute_commit()`.

Il futuro `PostgreSQLCommitRepository`, non ancora implementato, deve eseguire in una singola transazione:

1. lock della RUN;
2. verifica che la RUN sia aperta;
3. verifica di `expected_version`;
4. verifica di `simulation`;
5. controllo delle chiavi idempotenti;
6. risoluzione della provenance verso righe PROGRAMMA versionate;
7. inserimento ORDINI;
8. inserimento RIGHE_ORDINE;
9. inserimento ORIGINI_RIGHE_ORDINE;
10. conclusione RUN;
11. inserimento ordinato di warning/errori;
12. eventuale audit già congelato dal Physical Schema;
13. commit fisico;
14. produzione della ricevuta.

Sono vietati retry ciechi, secondi writer, persistenza parziale, conclusione anticipata della RUN e chiamate esterne mentre la transazione detiene lock.

## 13. Idempotenza

L'idempotenza ha due livelli distinti:

1. controllo applicativo preliminare tramite repository read-only e validazione;
2. vincolo `UNIQUE` PostgreSQL definitivo sulla chiave idempotente.

Il controllo preliminare può diventare obsoleto. Il vincolo PostgreSQL è la difesa concorrente finale. Una collisione produce rollback completo: nessun ORDINE duplicato, nessuna conclusione parziale della RUN e nessuna conversione automatica in successo senza riconciliazione certa.

Non è ammesso retry automatico o cieco.

## 14. Concorrenza

I meccanismi congelati sono:

- Identity: compare-and-set PostgreSQL su sequenza tipizzata e versionata;
- RUN: `expected_version` e row lock nel commit;
- ORDINI: vincolo `UNIQUE` sulla chiave idempotente;
- write path: una sola transazione PostgreSQL.

Non appartengono al contratto mutex Python, lock applicativi in memoria, polling o loop di retry. I lock vengono acquisiti in ordine deterministico e mantenuti per transazioni brevi senza I/O esterno.

## 15. Ricevuta e riconciliazione

I modelli congelati sono `CommitExecutionReceipt`, `CommitResult` e `CommitStatus`.

- `PREPARED` indica che la richiesta è stata preparata senza dati di commit completato;
- `COMMITTED` viene restituito soltanto dopo commit fisico e riconciliazione completa;
- `RECONCILIATION_REQUIRED` indica che la prova disponibile non consente di dichiarare una riconciliazione completa.

Una risposta incerta non autorizza un retry cieco. I conteggi logici attesi e le righe fisiche appendate restano distinti. La ricevuta deve essere coerente con `run_id`, target, conteggi del piano, timestamp fornito e insieme delle chiavi idempotenti.

## 16. Error handling

Gli errori applicativi vengono propagati senza retry automatico. Gli errori Psycopg vengono convertiti dall'Infrastructure in errori infrastrutturali o applicativi specifici, preservando la causa con exception chaining.

Rollback e chiusura della connessione sono cleanup best-effort e non sostituiscono l'errore principale. Errori e log non devono contenere credenziali, host, password, project reference o stringhe di connessione.

`TypeError` e altri bug di programmazione non devono essere catturati come errori database né mascherati da cleanup generico.

## 17. Percorsi legacy

Restano esplicitamente isolati:

- completamento RUN tramite `complete_run()` e `fail_run()`;
- scrittura tramite `OrdineRepository.add_scheduled_orders()`;
- adapter di commit Google Sheets.

Questi percorsi non appartengono al runtime PostgreSQL autorevole, non devono essere collegati simultaneamente al nuovo runtime e non devono introdurre doppia scrittura. La loro eventuale rimozione o dismissione appartiene a uno sprint futuro dedicato.

## 18. Componenti congelati

Sono congelati nel significato e nelle responsabilità correnti:

- `OpenSchedulingRun`;
- `SchedulingRunCompletion`;
- `CompletedSchedulingRun`;
- `VersionedProgrammaFornitura`;
- `VersionedProgramLine`;
- `OrderLineProvenance`;
- `ScheduledOrderRecord`;
- `SchedulingResult`;
- `WritePlan`;
- `ValidatedWritePlan`;
- `CommitRequest`;
- `CommitExecutionReceipt`;
- `CommitResult`;
- `ScheduledOrderReadRepository`;
- `CommitRepository`.

## 19. Componenti non ancora implementati

Non sono ancora implementati o completati:

- migrazione dello schema operativo ORDINI/PROGRAMMI;
- `PostgreSQLCommitRepository`;
- repository PostgreSQL dei PROGRAMMI versionati;
- repository PostgreSQL CLIENTI;
- repository PostgreSQL VARIETÀ;
- bootstrap runtime PostgreSQL end-to-end;
- importazione iniziale dei dati;
- interfaccia operativa;
- test concorrenti su PostgreSQL reale, ancora skipped nel normale perimetro Core.

La presenza di porte, modelli, repository read-only o migrazioni foundation non equivale all'implementazione del write path atomico completo.

## 20. Regole per gli sprint successivi

1. Una modifica al significato dei contratti congelati richiede Architecture Review.
2. Aggiunte puramente infrastrutturali coerenti con il Freeze non richiedono una modifica del documento.
3. Nessun adapter può ricostruire, dedurre o sostituire dati applicativi mancanti.
4. Nessuna migrazione può semplificare, indebolire o aggirare gli invarianti congelati.
5. Nessuna scrittura reale è autorizzata finché migrazioni, adapter, bootstrap e test sandbox non sono completati e revisionati.
6. Il futuro runtime deve collegare un solo writer autorevole.
7. Google Sheets resta fuori dalla transazione PostgreSQL e dal write path autorevole.
8. Timeout o esiti incerti richiedono riconciliazione esplicita, non retry cieco.
9. `OrdineCreationType` è obbligatorio e immutabile; nessun writer può trasformare AUTOMATICO e MANUALE l'uno nell'altro.

Il presente documento congela l'architettura applicativa del write path PostgreSQL nello stato:

**APPLICATION ATOMIC COMMIT FREEZE v1.0**
