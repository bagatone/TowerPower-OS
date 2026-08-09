# AUTOMATED OPERATIONAL SCHEDULING ARCHITECTURE REVIEW

**Stato:** ARCHITECTURE REVIEW — OWNER DECISIONS REQUIRED
**Ambito:** invocazione unattended del Runtime Operativo PostgreSQL
**Baseline:** `1531802`

## 1. Obiettivo e verdetto

Questa review definisce il confine architetturale del primo scheduler
automatico del Tower Power Operations senza modificare il Runtime Operativo
congelato.

Il modello tecnico è determinabile: lo scheduler è esterno al Core e invoca
esclusivamente il comando ufficiale:

```text
tpo schedule execute \
  --settings SETTINGS \
  --business-date YYYY-MM-DD \
  --business-time HH:MM \
  --identity IDENTITY \
  --confirm
```

Il Core non diventa un daemon. Lo scheduler non importa, costruisce o invoca
Application, `OperationalSchedulingEntryPoint`, orchestratore, Committer,
repository o PostgreSQL direttamente.

Non è possibile emettere
`AUTOMATED_OPERATIONAL_SCHEDULING_FREEZE.md` in questa fase. Le fonti non
determinano:

1. cadenza e orario operativo iniziali;
2. policy per una vera esecuzione mancata;
3. valore concreto dell'identità tecnica unattended;
4. canale di escalation e retention dei log;
5. provisioning production dei segreti PostgreSQL.

Scegliere tali valori in questa review introdurrebbe decisioni business o di
deployment non presenti nei Freeze originari.

## 2. Fonti e invarianti preservati

La review applica integralmente:

- `OPERATIONAL_RUNTIME_FINAL_FREEZE.md`;
- `CLI_OPERATIONAL_ADAPTER_FREEZE.md`;
- `APPLICATION_OPERATIONAL_ENTRYPOINT_FREEZE.md`;
- `APPLICATION_OPERATIONAL_RUNTIME_FREEZE.md`.

Restano invariati:

- PostgreSQL unico writer autorevole;
- CLI unico ingresso dello scheduler;
- una invocazione esplicita per intenzione operativa;
- business reference esplicita nella timezone `Atlantic/Canary`;
- identity provider-neutral passata esclusivamente con `--identity`;
- `--confirm` obbligatorio e non interattivo;
- nessun retry automatico;
- nessun fallback Google;
- nessun doppio commit o lifecycle;
- outcome ed exit code congelati;
- runtime manuale e unattended semanticamente identici.

## 3. Scheduler owner

Lo scheduler appartiene al sistema operativo o a un adapter di automazione
esterno. Non appartiene a Domain, Application, Infrastructure PostgreSQL,
Bootstrap o CLI.

Il suo unico compito operativo è:

```text
policy temporale esterna
→ costruzione argomenti CLI espliciti
→ una invocazione di tpo schedule execute
→ acquisizione exit/output
→ logging e segnalazione esterni
```

Lo scheduler non governa RUN, non deduce outcome, non riconcilia, non esegue
retry e non chiama un percorso alternativo quando il comando fallisce.

Per il target macOS corrente il meccanismo raccomandato è `launchd`, mediante
un futuro LaunchAgent o LaunchDaemon determinato dai requisiti di deployment.
La scelta fra contesto utente e contesto di sistema non è assunta da questa
review.

## 4. Frequenza

Il Runtime supporta invocazioni esplicite multiple: Scheduling e PostgreSQL
applicano idempotenza e concorrenza senza trasformare invocazioni ulteriori in
retry interni. Questa capacità non stabilisce tuttavia la frequenza business.

Le opzioni da sottoporre all'owner sono:

| Opzione | Conseguenza |
|---|---|
| una volta al giorno | modello operativo semplice; l'orario deve essere scelto rispetto agli orari di generazione dei PROGRAMMI |
| più volte al giorno | riduce la latenza delle occorrenze; produce una RUN distinta per ogni invocazione e richiede una lista esplicita di orari |
| frequenza configurabile | consente evoluzione senza cambiare il Core; richiede ownership, validazione e governance della configurazione esterna |

Nessuna fonte congela un orario definitivo. Il valore iniziale `05:00` dello
Scheduling Engine è un orario predefinito di generazione delle occorrenze, non
una decisione sulla pianificazione del processo unattended. Non può essere
riutilizzato automaticamente come orario dello scheduler.

**Decisione richiesta all'owner:** cadenza iniziale e uno o più orari locali
espliciti.

## 5. Business date e business time

Per ogni invocazione lo scheduler deve calcolare i due argomenti dalla stessa
istantanea temporale locale nella timezone ufficiale `Atlantic/Canary`:

- `--business-date` nel formato `YYYY-MM-DD`;
- `--business-time` nel formato `HH:MM` a 24 ore.

La conversione avviene nel boundary esterno immediatamente prima di costruire
il comando. Non usa UTC implicita, timezone del processo non verificata,
mezzanotte predefinita, data della pianificazione nominale o un Clock interno
del Core.

Una invocazione eseguita dopo wake o avvio deve comunque dichiarare
esplicitamente quale business reference rappresenta. La scelta fra riferimento
effettivo del momento e riferimento nominale dell'esecuzione mancata dipende
dalla policy di missed execution e non può essere dedotta dal Runtime.

Scheduler e operatore manuale forniscono gli stessi argomenti e attraversano la
stessa validazione CLI.

## 6. Scheduler identity

Lo scheduler passa soltanto:

```text
--identity IDENTITY
```

L'identità unattended deve essere:

- esplicita;
- non vuota;
- provider-neutral;
- opaca;
- dedicata alla funzione operativa automatizzata;
- configurata esternamente per l'installazione.

Lo scheduler non costruisce `ActorId`, reason, correlation ID o
`CommitExecutionContext`. Non usa utente OS, hostname, email, label `launchd` o
fallback come identità implicita. L'Operational Entry Point continua a
trasformare internamente la recognized identity nel contesto Application.

Congelare nel codice o nel Core una stringa tecnica universale sarebbe
incompatibile con il divieto di default e inferenze. Il meccanismo corretto è
la configurazione esplicita. Il valore concreto non è derivabile dalle fonti.

**Decisione richiesta all'owner:** valore dell'identità tecnica riconosciuta
per l'installazione unattended.

## 7. Confirm

Ogni invocazione autorizzata include esplicitamente `--confirm`.

La conferma significa che la policy esterna ha autorizzato quella specifica
esecuzione di write. Non è un prompt, non viene ottenuta da stdin e non viene
sostituita da `--force`.

Se la configurazione dell'automazione non autorizza l'esecuzione, il comando
non viene invocato. Se `--confirm` manca, la CLI termina come
`OPERATION_INPUT_INVALID` prima di qualsiasi RUN o allocazione.

## 8. Single-run protection

La protezione ha tre livelli distinti.

### 8.1 Process-level

Appartiene all'adapter di automazione. Su macOS deve esistere una sola
definizione `launchd` caricata per la funzione e una sola label stabile. Non
devono essere configurati contemporaneamente cron, una seconda plist o wrapper
paralleli per la stessa pianificazione.

`launchd` gestisce l'identità e il lifecycle del job; una scadenza
`StartInterval` avvenuta mentre il job è ancora in esecuzione viene saltata.
La futura configurazione deve inoltre impedire che wrapper o strumenti esterni
avviino una seconda istanza della stessa automazione. Questa protezione non
viene implementata con lock Python nel Core.

La protezione process-level non può impedire a un operatore autorizzato di
avviare manualmente il comando. Tale concorrenza viene governata dai livelli
successivi, non da un mutex globale nel Runtime.

### 8.2 Runtime PostgreSQL

Il Runtime conserva CAS Identity, RUN lock, optimistic version, transazione
atomica e vincolo univoco delle chiavi idempotenti. Tentativi concorrenti non
producono doppio commit o dati parziali.

### 8.3 Idempotenza business

`RunScheduling` effettua il controllo applicativo e PostgreSQL costituisce la
barriera definitiva. Due RUN non equivalgono a un solo lifecycle, ma una stessa
occorrenza business non produce due ORDINI autorevoli.

I livelli database e business proteggono l'integrità; non sostituiscono la
protezione process-level e non autorizzano invocazioni duplicate intenzionali.

## 9. Missed execution

Le fonti non congelano la policy per una macchina spenta, un job non caricato o
un'esecuzione non avvenuta.

`launchd` distingue inoltre le proprie semantiche: un calendario
`StartCalendarInterval` scaduto durante sleep viene avviato al wake e più
scadenze vengono aggregate; `StartInterval` perde la scadenza durante sleep o
quando il job è già in esecuzione. Questa semantica tecnica non decide la
policy business per una vera esecuzione mancante.

Le opzioni obbligatorie sono:

| Opzione | Conseguenza |
|---|---|
| A. non recuperare | si attende la successiva esecuzione pianificata; Scheduling potrà valutare le occorrenze ancora operative secondo le proprie regole, senza ricreare la RUN mancata |
| B. recuperare | viene avviata una nuova RUN esplicita; occorre congelare quando, quante esecuzioni aggregate e quale business date/time usare |
| C. richiedere intervento | nessuna esecuzione automatica sostitutiva; viene emesso un alert e un operatore decide se usare la CLI manuale |

La capacità dello Scheduling Engine di recuperare occorrenze scadute ancora
operative non equivale a una policy di recupero della RUN pianificata e non
consente di scegliere automaticamente B.

**Decisione richiesta all'owner:** A, B o C. Se viene scelta B, devono essere
definiti anche finestra di recupero, aggregazione e business reference.

## 10. OPERATION_FAILED

Exit `1` termina l'invocazione corrente.

Lo scheduler:

- non ripete il comando;
- non crea una seconda RUN;
- conserva exit code, stdout e stderr sanitizzati;
- conserva RunId e stato finale quando presenti;
- emette una segnalazione operativa esterna;
- attende una nuova esecuzione pianificata o un intervento esplicito secondo la
  policy approvata.

La notifica non riclassifica `FAILED`, non interpreta errori PostgreSQL e non
deduce se l'operatore debba eseguire una nuova RUN.

## 11. RECONCILIATION_REQUIRED

Exit `4` richiede obbligatoriamente:

- nessun retry;
- nessuna seconda esecuzione automatica;
- nessuna conclusione della RUN come `FAILED`;
- escalation operativa immediata;
- conservazione integrale dell'output pubblico di riconciliazione;
- conservazione di RunId, correlation ID, requested_at, idempotency keys e
  conteggi attesi quando disponibili;
- sospensione di qualunque recupero automatico riferito alla stessa intenzione
  fino a riconciliazione esplicita.

Lo scheduler non consulta direttamente il database, non deduce l'esito fisico
e non trasforma la riconciliazione in successo o failure.

## 12. INTERNAL_ERROR

Exit `5` termina l'invocazione senza retry automatico.

Lo scheduler conserva il messaggio generico e provider-neutral della CLI,
registra il contesto esterno dell'invocazione ed esegue escalation. Non tenta
di ottenere o mostrare traceback, causa tecnica, SQL o dettagli provider.

L'errore resta un exit del boundary CLI e non diventa un nuovo outcome
Application.

## 13. RUNTIME_UNAVAILABLE

Exit `3` termina l'invocazione corrente e produce una segnalazione operativa.
Non viene eseguito retry immediato, loop, backoff o fallback Google.

La successiva scadenza ordinaria può invocare nuovamente il comando: è una
nuova esecuzione pianificata, non un retry interno. Qualunque recupero della
scadenza fallita resta soggetto alla policy di missed execution ancora da
approvare.

## 14. INPUT_INVALID

Exit `2` indica un errore di configurazione o costruzione dell'invocazione. Il
comando non ha aperto RUN né allocato RunId.

Lo scheduler non corregge automaticamente i valori e non usa default. Registra
l'errore sanitizzato, esegue escalation e attende la correzione della
configurazione prima di una nuova invocazione autorizzata.

## 15. Output e logging

Per ogni invocazione il sistema esterno di automazione conserva almeno:

- timestamp dell'invocazione nella timezone `Atlantic/Canary`;
- identificativo della definizione scheduler;
- exit code numerico;
- classificazione esterna corrispondente all'exit;
- stdout e stderr sanitizzati;
- RunId quando esposto;
- correlation ID e contesto pubblico quando esposti;
- stato finale renderizzato quando disponibile.

Non vengono mai registrati:

- password o credenziali;
- DSN o URL PostgreSQL;
- host o dettagli di connessione non autorizzati;
- SQL;
- traceback provider-specific;
- cause tecniche non esposte dal boundary;
- PK interne.

Lo scheduler non estrae dati mediante accesso privato al Runtime e non
ricostruisce correlation ID o stato dal database. Formato persistente,
destinazione, retention, rotazione e canale di notifica appartengono alla
policy di deployment.

**Decisione richiesta all'owner:** destinazione di logging, retention e canale
di escalation.

## 16. Environment

Il processo unattended riceve esplicitamente:

- path assoluto dell'eseguibile o entry point CLI;
- working directory, se necessaria;
- path assoluto del file settings;
- configurazione PostgreSQL congelata;
- identity tecnica configurata;
- timezone operativa verificata;
- path autorizzati per output e log.

Non legge `.env.local` implicitamente. Non dipende dalla shell interattiva,
dall'utente OS, da variabili ereditate casualmente, da path relativi ambigui o
da fallback Google.

La configurazione PostgreSQL continua a usare esclusivamente le variabili già
congelate dal Runtime. Nessuna nuova variabile Application viene introdotta da
questa review. Il modo production di fornire segreti al processo non è definito
dai Freeze correnti e deve evitare credenziali in plist, argomenti CLI, log e
repository.

**Decisione richiesta all'owner/deployment:** meccanismo autorizzato di
provisioning dei segreti e permessi del processo.

## 17. launchd versus cron

| Criterio | launchd | cron |
|---|---|---|
| integrazione macOS | meccanismo nativo principale | supportato, ma la documentazione Darwin rimanda a launchd |
| calendario | `StartCalendarInterval` | espressione crontab |
| sleep | scadenze calendarizzate avviate al wake e aggregate | scadenze durante sleep saltate |
| lifecycle job | label, dominio, stdout/stderr e supervisione nativi | esecuzione shell più semplice, minore integrazione |
| ambiente | esplicito nella definizione del job | ambiente cron ristretto e separato dalla shell interattiva |
| aderenza al modello | adapter esterno, senza daemon Core | adapter esterno, senza daemon Core |

Per macOS il target iniziale raccomandato è **launchd** con
`StartCalendarInterval`, non `StartInterval`, perché il requisito è una
pianificazione civile nella timezone operativa e il comportamento durante
sleep è esplicito. La configurazione concreta non viene implementata in questa
review.

La raccomandazione non decide automaticamente il recupero business: il wake
coalescing di `launchd` deve essere accettato o limitato dalla policy owner
prima del Freeze.

## 18. Compatibilità manuale

La CLI manuale resta disponibile e semanticamente identica:

```text
operatore ─┐
           ├→ tpo schedule execute → Runtime Operativo PostgreSQL
launchd ───┘
```

Entrambi i caller:

- forniscono business date e business time esplicite;
- forniscono identity riconosciuta esplicita;
- forniscono `--confirm`;
- ricevono gli stessi exit code e lo stesso rendering;
- attraversano lo stesso Entry Point e lo stesso writer;
- non dispongono di fallback o retry automatico.

Non viene introdotto un comando scheduler-specifico, un flag unattended o un
percorso Application alternativo.

## 19. Decisioni determinabili

| Area | Decisione determinabile |
|---|---|
| owner scheduler | adapter esterno al Core |
| target macOS | launchd raccomandato |
| ingresso | esclusivamente `tpo schedule execute` |
| Core daemon | vietato |
| business timezone | `Atlantic/Canary` |
| business reference | date e time esplicite, nessun default |
| identity boundary | solo `--identity`, nessun ActorId esterno |
| confirmation | `--confirm` esplicito, nessun prompt |
| process overlap | responsabilità adapter; nessun lock Python nel Core |
| integrità concorrente | CAS, lock, version e idempotenza PostgreSQL |
| retry | vietato per tutti gli exit non-success |
| reconciliation | escalation e sospensione, nessuna seconda esecuzione |
| Google | nessun fallback e nessuna costruzione |
| manual CLI | invariata e sul medesimo percorso |

## 20. Decisioni richieste all'owner

| Decisione | Opzioni o dato richiesto | Perché blocca il Freeze |
|---|---|---|
| cadenza | giornaliera, multipla o configurabile | determina numero di RUN e comportamento operativo |
| orario | uno o più orari `Atlantic/Canary` | non coincide automaticamente con l'orario di generazione dei PROGRAMMI |
| missed execution | A non recuperare, B recuperare, C intervento | determina se e come nasce una nuova RUN dopo una scadenza mancata |
| identity unattended | valore provider-neutral riconosciuto | actor deve essere esplicito e non può avere fallback |
| logging | destinazione e retention | necessario per esercizio unattended governato |
| escalation | canale e destinatario operativo | necessario per FAILED, reconciliation, internal error e runtime unavailable |
| secret provisioning | meccanismo e permessi | i Freeze vietano `.env.local` implicito e leakage, ma non definiscono il deployment |
| launchd domain | LaunchAgent o LaunchDaemon | dipende da utente, sessione, privilegi e disponibilità richiesta |

## 21. Conseguenze per il prossimo passo

Fino all'approvazione delle decisioni owner:

- non viene creato `AUTOMATED_OPERATIONAL_SCHEDULING_FREEZE.md`;
- non viene aggiunta alcuna plist;
- non viene aggiunto cron;
- non viene implementato wrapper, lock, retry, daemon o notifier;
- non viene modificato il Runtime Operativo;
- la CLI manuale resta l'unico adapter operativo concreto approvato.

Dopo l'approvazione, l'Editing potrà consolidare esclusivamente le decisioni
assunte in un Freeze dedicato. L'implementazione dell'adapter `launchd` resterà
uno sprint successivo separato e non richiederà modifiche al Core se rispetterà
questa review e i Freeze originari.
