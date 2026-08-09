# APPLICATION OPERATIONAL ENTRYPOINT FREEZE

**Stato:** ARCHITECTURE FREEZE  
**Ambito:** boundary operativo verso Application  
**Fonti normative:** `APPLICATION_OPERATIONAL_RUNTIME_FREEZE.md`,
`POSTGRESQL_FOUNDATION_FINAL_FREEZE.md` e
`PROJECT_ARCHITECTURE_REVIEW_2026.md`.

## 1. Scopo del Freeze

Il presente documento congela il contratto normativo del boundary tra un
caller esterno e l'Application per l'Operational Scheduling.

Il Freeze risolve in modo definitivo ownership degli input, costruzione del
contesto di esecuzione, responsabilità degli adapter, rappresentazione degli
outcome e mapping simbolico degli esiti. Non descrive una implementazione
concreta e non modifica gli invarianti del runtime operativo, del commit
atomico o della PostgreSQL Foundation.

Per il solo boundary operativo, questo documento specializza la responsabilità
di costruzione del `CommitExecutionContext` indicata in
`APPLICATION_OPERATIONAL_RUNTIME_FREEZE.md`: la costruzione appartiene al
boundary Application dedicato e non al caller o al suo adapter concreto.

## 2. Scope

Il Freeze include:

- il contratto provider-neutral dell'Operational Entry Point;
- gli input ammessi dal caller;
- la costruzione Application del `CommitExecutionContext`;
- l'origine normativa di actor, reason e correlation ID;
- l'invocazione dell'`OperationalSchedulingOrchestrator`;
- la restituzione di outcome provider-neutral;
- il mapping simbolico degli outcome per gli adapter;
- il confine fra Bootstrap, caller, boundary e runtime Application;
- la copertura minima obbligatoria dei futuri adapter operativi.

Il Freeze non autorizza un provider, un canale, un ambiente o una modalità di
esecuzione specifici.

## 3. Principio fondamentale

L'Operational Entry Point è provider-neutral.

Un unico contratto Application governa ogni accesso operativo. Lo stesso
contratto deve poter essere usato, senza modifiche, da:

- CLI;
- API;
- Scheduler;
- Job;
- Batch;
- Event Consumer.

Nessun adapter esterno può alterare il lifecycle della RUN, la semantica del
commit, la classificazione degli outcome, il writer autorevole o le regole di
riconciliazione.

## 4. Boundary operativo

Il percorso congelato è:

```text
Caller
↓
Operational Entry Point
↓
OperationalSchedulingOrchestrator
↓
Application
↓
Infrastructure
```

L'Operational Entry Point è un boundary Application. Traduce l'intenzione
operativa provider-neutral del caller nell'input validato richiesto
dall'`OperationalSchedulingOrchestrator` e restituisce al caller un outcome
provider-neutral.

Il boundary non sostituisce l'orchestratore e non governa il lifecycle della
RUN. L'orchestratore resta l'unico owner di allocazione RunId, apertura RUN,
Scheduling, delega al commit e gestione delle failure operative.

## 5. Responsabilità del caller

Il caller deve:

- fornire la business date esplicita;
- fornire l'identità operativa del canale in forma provider-neutral già
  riconosciuta dal boundary;
- rispettare l'eventuale conferma richiesta dal proprio canale prima
  dell'invocazione;
- invocare una sola volta l'Operational Entry Point per ogni intenzione
  operativa;
- consumare l'outcome strutturato senza dedurre stati ulteriori;
- non eseguire retry automatici.

Il caller non deve conoscere:

- `ActorId`;
- reason applicativa;
- correlation ID applicativo;
- RunId;
- Clock o timestamp tecnici;
- `RunScheduling`;
- Run Tracking;
- WritePlan o relativa validazione;
- Committer o Commit Repository;
- repository PostgreSQL o Google;
- transazioni, lock, versioni fisiche o chiavi interne;
- classificazione di eccezioni provider-specific.

## 6. Execution Context

Il `CommitExecutionContext` non appartiene al caller.

Il caller e il relativo adapter non costruiscono direttamente
`CommitExecutionContext` e non conoscono i suoi Value Object interni.

Il `CommitExecutionContext` viene costruito all'interno del boundary
Application mediante un componente dedicato. Tale componente è responsabile
di produrre un contesto completo, valido, immutabile e provider-neutral prima
dell'invocazione dell'`OperationalSchedulingOrchestrator`.

Il contesto risultante conserva obbligatoriamente actor, reason e correlation
ID espliciti. Non sono ammessi valori mancanti, default generici, fallback,
inferenze Infrastructure o riscritture successive.

La responsabilità del componente dedicato è congelata; la sua implementazione
concreta non appartiene al presente Freeze.

## 7. Actor

L'origine dell'`ActorId` è responsabilità del boundary operativo, non della
CLI e non di qualsiasi altro adapter esterno.

Il boundary riceve dal proprio contesto di invocazione una identità operativa
provider-neutral riconosciuta e la traduce nell'`ActorId` applicativo mediante
il componente dedicato al contesto.

Nessun adapter può inventare actor tecnici, assegnare actor predefiniti o
fornire direttamente un `ActorId` al runtime. L'actor inserito nel
`CommitExecutionContext` resta l'unico actor autorevole del commit e
dell'audit.

## 8. Reason

La reason è una policy applicativa.

La reason deriva dal tipo di operazione Application richiesta ed è assegnata
uniformemente dal componente dedicato al contesto. Non è testo libero del
caller, non è un parametro CLI e non è configurazione Infrastructure.

Adapter differenti che invocano la stessa operazione Application producono la
stessa semantica di reason.

## 9. Correlation ID

La generazione e la propagazione del correlation ID sono uniformi per tutti
gli entry point operativi.

Nessun caller costruisce direttamente il correlation ID applicativo. Il
boundary, mediante il componente dedicato al contesto, acquisisce o genera un
correlation ID valido secondo una sola policy Application e lo propaga senza
modifiche per l'intero lifecycle.

Il correlation ID non viene dedotto da RunId, timestamp, actor, business date,
chiavi idempotenti o identificativi provider-specific.

## 10. Business Date

La business date resta input semantico esplicito del caller.

Il boundary ne effettua la validazione sintattica e la converte nel riferimento
temporale Application previsto dal runtime. Non la deriva dal Clock, dalla data
locale del processo, dalla RUN o dall'Infrastructure.

La business date resta distinta da `run_started_at`, `completion_at`,
`requested_at` e `commit_completed_at`.

## 11. Simulation

La simulation è fuori scope dall'Operational Entry Point congelato.

Nessun caller o adapter operativo può introdurre autonomamente una modalità di
simulation, trasformare un'esecuzione operativa in simulazione o instradare
l'opzione verso il runtime autorevole.

La simulation richiede un contratto Application dedicato e separato. Fino a
quando tale contratto non è congelato, l'Operational Entry Point rappresenta
esclusivamente esecuzioni operative non simulate.

## 12. Confirmation

Le eventuali conferme operative appartengono al caller.

Ogni canale decide e completa l'interazione di conferma prima di invocare
l'Operational Entry Point. Una conferma negata o incompleta non produce alcuna
invocazione Application.

L'Application non interagisce con utenti, terminali, interfacce, prompt o
sessioni. Il boundary non apre RUN e non alloca identificativi prima che il
caller abbia completato la propria conferma.

## 13. Outcome

L'Operational Entry Point espone esclusivamente tre outcome operativi:

- `COMMITTED`;
- `FAILED`;
- `RECONCILIATION_REQUIRED`.

`COMMITTED` dichiara un commit autorevole confermato e include la RUN conclusa.

`FAILED` dichiara una failure certa e conserva le informazioni
provider-neutral disponibili, inclusi RunId, errori, warning e stato noto
della RUN quando presenti.

`RECONCILIATION_REQUIRED` dichiara un esito incerto. Conserva il contesto di
riconciliazione disponibile e non viene trasformato in successo, failure certa
o retry.

Il caller renderizza o trasporta l'outcome senza cambiarne la classificazione.

## 14. Error Boundary

Il boundary Application espone soltanto outcome ed errori provider-neutral.

Nessun adapter operativo:

- interpreta eccezioni PostgreSQL;
- analizza testo di errori o traceback;
- deduce commit, rollback o stato RUN;
- converte un errore Infrastructure in una diversa classe di outcome;
- avvia retry o riconciliazione implicita.

La traduzione delle failure provider-specific appartiene ai confini
Infrastructure e Application già congelati. Dettagli di connessione, SQL,
credenziali, host, driver e PK interne non attraversano l'Operational Entry
Point.

## 15. Exit Mapping

Il mapping esterno usa esclusivamente nomi simbolici:

| Outcome Application | Exit simbolico |
|---|---|
| `COMMITTED` | `OPERATION_COMMITTED` |
| `FAILED` | `OPERATION_FAILED` |
| `RECONCILIATION_REQUIRED` | `OPERATION_RECONCILIATION_REQUIRED` |
| input esterno non valido | `OPERATION_INPUT_INVALID` |
| runtime operativo non disponibile | `OPERATION_RUNTIME_UNAVAILABLE` |

I nomi simbolici sono provider-neutral. Il presente Freeze non assegna numeri,
codici HTTP, segnali, stati di job o valori specifici di trasporto.

## 16. Bootstrap

Bootstrap compone ed espone l'`OperationalSchedulingOrchestrator` soltanto
quando il grafo operativo completo è disponibile. La composizione resta lazy e
non apre connessioni.

Il caller e il suo adapter non ricevono:

- repository;
- Committer;
- `ExecuteSchedulingCommit`;
- `RunScheduling`;
- Run Tracking;
- Clock;
- writer o connection factory.

Il boundary Application usa esclusivamente l'orchestratore operativo composto
dal Bootstrap. L'assenza dell'orchestratore equivale a runtime operativo non
disponibile e non autorizza fallback Google o costruzione parziale del grafo.

## 17. Test obbligatori

Ogni futuro entry point operativo deve coprire almeno:

- parsing e validazione della business date;
- rifiuto di input ulteriori non previsti dal contratto;
- costruzione del `CommitExecutionContext` nel boundary Application;
- assenza di costruzione diretta del contesto da parte dell'adapter;
- risoluzione uniforme dell'actor;
- assegnazione uniforme della reason applicativa;
- generazione e propagazione uniforme del correlation ID;
- invocazione singola dell'`OperationalSchedulingOrchestrator`;
- assenza di accesso a repository, Committer, `RunScheduling`, Run Tracking e
  Clock;
- rendering o trasporto di `COMMITTED`;
- rendering o trasporto di `FAILED`;
- rendering o trasporto di `RECONCILIATION_REQUIRED`;
- conservazione di RunId, warning, errori e contesto di riconciliazione
  disponibili;
- mapping di tutti gli exit simbolici;
- runtime non disponibile senza fallback;
- nessun retry;
- nessuna interpretazione di errori provider-specific;
- assenza della simulation dall'entry point operativo;
- Bootstrap lazy e privo di connessioni durante la composizione;
- equivalenza contrattuale fra adapter esterni differenti.

## 18. Fuori scope

Restano fuori scope:

- Authentication;
- Authorization;
- API;
- Scheduler;
- Simulation;
- Supabase;
- Deployment;
- Monitoring;
- UI.

Sono inoltre fuori scope numeri degli exit code, protocolli di trasporto,
formati di autenticazione, gestione delle sessioni, conferme concrete,
riconciliazione operativa e recovery.

## 19. Decision Matrix

| Voce | Decisione congelata | Owner |
|---|---|---|
| natura dell'entry point | provider-neutral | Application boundary |
| adapter ammessi | CLI, API, Scheduler, Job, Batch, Event Consumer | caller esterno |
| input operativo | business date esplicita e identità operativa riconosciuta | caller |
| business date | mai derivata dal Clock | caller e boundary |
| execution context | costruito internamente al boundary | Application boundary |
| actor | risolto dal boundary, mai inventato dall'adapter | Application boundary |
| reason | policy applicativa, non parametro esterno | Application boundary |
| correlation ID | acquisizione o generazione uniforme e propagazione invariata | Application boundary |
| confirmation | completata prima dell'invocazione | caller |
| simulation | esclusa dall'entry point operativo | contratto separato futuro |
| lifecycle RUN | governato esclusivamente dall'orchestratore | OperationalSchedulingOrchestrator |
| writer | unico writer PostgreSQL congelato | Infrastructure tramite Application |
| outcome | COMMITTED, FAILED, RECONCILIATION_REQUIRED | Application |
| error mapping | provider-neutral, senza parsing negli adapter | Application boundary |
| retry | mai automatico | tutti i layer |
| exit mapping | esclusivamente simbolico | adapter esterno |
| Bootstrap | grafo completo o runtime assente, sempre lazy | Bootstrap |
| dipendenze esposte | solo orchestratore operativo attraverso il boundary | Bootstrap e Application boundary |
| fallback | nessun fallback Google o provider alternativo | tutti i layer |

## 20. Conclusione

Ogni futuro entry point operativo deve adattarsi al contratto Application
congelato dal presente documento.

CLI, API, Scheduler, Job, Batch ed Event Consumer restano adapter esterni
intercambiabili. Nessuno di essi modifica input, lifecycle, execution context,
outcome, error boundary, writer o dipendenze Application per esigenze del
proprio canale.

Il contratto Application non viene modificato per adattarsi a uno specifico
adapter. Ogni modifica futura alle decisioni congelate in questo documento
richiede Architecture Review.
