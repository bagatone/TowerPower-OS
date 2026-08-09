# CLI Operational Adapter Freeze

## 1. Scopo

Il presente documento congela il contratto normativo dell'adapter CLI per
l'esecuzione operativa dello Scheduling. Le decisioni qui definite completano
il boundary già congelato dall'Application Operational Entry Point senza
modificare Application, Domain, Infrastructure o i Freeze precedenti.

## 2. Comando operativo ufficiale

Il comando operativo ufficiale V1 è:

```text
tpo schedule execute \
  --settings SETTINGS \
  --business-date YYYY-MM-DD \
  --business-time HH:MM \
  --identity IDENTITY \
  --confirm
```

Il namespace ufficiale resta `tpo schedule`.

I comandi esistenti `tpo schedule run` e `tpo schedule preflight` conservano
invariata la propria semantica. Il comando operativo di write non riutilizza
implicitamente il percorso di simulation legacy.

## 3. Business date e business time

`--business-date` è obbligatorio e accetta una data nel formato
`YYYY-MM-DD`.

`--business-time` è obbligatorio e accetta un orario nel formato `HH:MM` a 24
ore.

Business date e business time sono entrambi input semantici espliciti del
caller. La CLI ne esegue il parsing e la validazione sintattica e costruisce il
`CurrentSystemDate` combinando:

- business date;
- business time;
- timezone ufficiale `Atlantic/Canary`.

Il `CurrentSystemDate` risultante è il riferimento temporale operativo usato
dallo Scheduling. La CLI non introduce una mezzanotte implicita, non applica
default e non deriva data o ora dal Clock, dall'orario locale del processo,
dalla RUN o dall'Infrastructure.

Un valore assente, non valido o impossibile termina l'esecuzione come
`OPERATION_INPUT_INVALID` prima di ogni invocazione Application.

## 4. Operational identity

`--identity VALUE` è obbligatorio.

`VALUE` è un'identità operativa esplicita, provider-neutral, opaca e non vuota.
La CLI non ne interpreta il contenuto come credenziale e può costruire
esclusivamente:

```text
RecognizedOperationalIdentity(VALUE)
```

La CLI non costruisce `ActorId`, `CommitExecutionContext`, reason o correlation
ID. Non legge l'utente del sistema operativo, non deduce email, non usa
hostname e non assegna default o fallback.

L'`OperationalSchedulingEntryPoint` resta responsabile della trasformazione
interna della `RecognizedOperationalIdentity` nell'execution context
applicativo.

Un'identità assente o non valida termina l'esecuzione come
`OPERATION_INPUT_INVALID` prima di ogni invocazione Application.

## 5. Confirmation

`--confirm` è obbligatorio per il comando operativo di write.

La conferma è non interattiva. La CLI non presenta prompt, domande `YES/NO` o
altre interazioni. Non è previsto `--force`.

Se `--confirm` manca, la CLI:

- non invoca l'`OperationalSchedulingEntryPoint`;
- non apre una RUN;
- non alloca un RunId;
- non esegue Scheduling;
- termina come `OPERATION_INPUT_INVALID`.

La conferma è completata interamente dal caller prima del boundary Application.

## 6. Exit mapping

Il mapping numerico ufficiale è congelato come segue:

| Exit simbolico | Codice numerico |
|---|---:|
| `OPERATION_COMMITTED` | `0` |
| `OPERATION_FAILED` | `1` |
| `OPERATION_INPUT_INVALID` | `2` |
| `OPERATION_RUNTIME_UNAVAILABLE` | `3` |
| `OPERATION_RECONCILIATION_REQUIRED` | `4` |
| `OPERATION_INTERNAL_ERROR` | `5` |

`OPERATION_COMMITTED` è l'unico success exit.

Input non valido, parsing fallito o conferma mancante producono
`OPERATION_INPUT_INVALID`. L'assenza del runtime PostgreSQL operativo produce
`OPERATION_RUNTIME_UNAVAILABLE`. `OPERATION_FAILED` e
`OPERATION_RECONCILIATION_REQUIRED` restano esiti distinti.

Un errore Application inatteso, una violazione non rappresentata dagli outcome
`COMMITTED`, `FAILED` e `RECONCILIATION_REQUIRED`, oppure un errore non
classificabile come input non valido o runtime non disponibile produce
`OPERATION_INTERNAL_ERROR`.

`OPERATION_INTERNAL_ERROR` è un exit del boundary CLI e non introduce un nuovo
outcome Application. Non viene riclassificato come `OPERATION_FAILED` o
`OPERATION_RUNTIME_UNAVAILABLE`.

Il comando operativo V1 non introduce exit code ulteriori rispetto a quelli
congelati in questa sezione.

## 7. Simulation

`tpo schedule execute` non supporta `--simulation` né altre opzioni equivalenti.

La simulation resta esclusivamente sul percorso legacy esistente. Il comando
operativo non degrada a simulation e non introduce modalità di write implicite.

## 8. Application boundary

Il percorso operativo è:

```text
CLI
→ OperationalSchedulingIntent
→ OperationalSchedulingEntryPoint
→ OperationalSchedulingOrchestrator
→ PostgreSQL
```

La CLI costruisce soltanto i modelli pubblici autorizzati del package
Operational Entry Point e invoca una sola volta
`OperationalSchedulingEntryPoint` per ogni intenzione operativa confermata e
valida.

La CLI non accede direttamente a:

- `OperationalSchedulingOrchestrator`;
- `RunScheduling`;
- `ApplicationCommitter`;
- `CommitRepository`;
- Run Tracking;
- repository;
- Clock;
- connection factory.

## 9. Runtime e provider

Il comando operativo richiede il grafo PostgreSQL completo esposto dal
Bootstrap. Se l'`OperationalSchedulingEntryPoint` non è disponibile, la CLI
termina come `OPERATION_RUNTIME_UNAVAILABLE`.

Non è ammesso alcun fallback Google, provider alternativo, runtime parziale,
retry o ricomposizione manuale del percorso operativo.

## 10. Error handling

Il boundary CLI tratta come `OPERATION_INTERNAL_ERROR` esclusivamente:

- un errore Application inatteso;
- una violazione non rappresentata da `COMMITTED`, `FAILED` o
  `RECONCILIATION_REQUIRED`;
- un errore non classificabile come `OPERATION_INPUT_INVALID` o
  `OPERATION_RUNTIME_UNAVAILABLE`.

In tale caso la CLI:

- restituisce exit code `5`;
- produce un messaggio generico e provider-neutral;
- non mostra traceback;
- non mostra la causa tecnica;
- non interpreta né analizza eccezioni provider-specific;
- non esegue retry;
- non altera gli outcome Application congelati.

## 11. Fuori scope

Restano fuori scope:

- Authentication;
- Authorization;
- interpretazione dell'identità come credenziale;
- prompt interattivi;
- simulation del nuovo comando;
- scheduler automatici;
- API;
- recovery e reconciliation operativa;
- fallback Google.

## 12. Decisioni congelate

| Voce | Decisione |
|---|---|
| comando ufficiale | `tpo schedule execute --settings SETTINGS --business-date YYYY-MM-DD --business-time HH:MM --identity IDENTITY --confirm` |
| business date | obbligatoria, esplicita, formato `YYYY-MM-DD` |
| business time | obbligatorio, esplicito, formato `HH:MM` a 24 ore |
| riferimento temporale | business date e business time combinati nella timezone ufficiale `Atlantic/Canary` |
| default temporali | vietati, inclusa la mezzanotte implicita |
| identità | `--identity VALUE`, obbligatoria, provider-neutral e opaca |
| modello identità | esclusivamente `RecognizedOperationalIdentity(VALUE)` |
| conferma | `--confirm` obbligatorio e non interattivo |
| prompt | vietati |
| success exit | `OPERATION_COMMITTED = 0` |
| failure exit | `OPERATION_FAILED = 1` |
| input invalid exit | `OPERATION_INPUT_INVALID = 2` |
| runtime unavailable exit | `OPERATION_RUNTIME_UNAVAILABLE = 3` |
| reconciliation exit | `OPERATION_RECONCILIATION_REQUIRED = 4` |
| internal error exit | `OPERATION_INTERNAL_ERROR = 5` |
| internal error output | generico e provider-neutral, senza causa tecnica o traceback |
| internal error retry | vietato |
| simulation | assente dal nuovo comando |
| boundary | esclusivamente `OperationalSchedulingEntryPoint` |
| accesso diretto al runtime interno | vietato |
| fallback Google | vietato |
| Authentication e Authorization | fuori scope |

## 13. Conclusione

Ogni implementazione di `tpo schedule execute` deve rispettare integralmente
questo contratto. La CLI resta un adapter sottile: valida gli input esterni,
costruisce l'intenzione operativa pubblica, invoca il solo Operational Entry
Point e traduce il risultato negli exit code congelati, senza assumere
responsabilità Application o Infrastructure.
