# macOS LaunchAgent — Operational Scheduler

## Scopo

Il LaunchAgent V1 avvia una volta al giorno il comando operativo ufficiale:

```text
tpo schedule execute
```

L'adapter non modifica il Runtime, non usa Google e non invoca direttamente
Application o PostgreSQL.

## Prerequisiti

- macOS con timezone di sistema `Atlantic/Canary`;
- repository installato in un path stabile;
- virtualenv disponibile in `<ROOT>/.venv`;
- file locale `<ROOT>/config/settings.yaml` creato manualmente;
- file locale `<ROOT>/runtime/secrets/operational-scheduler.env` creato
  manualmente e protetto con permessi `0600`;
- permessi utente su `<ROOT>/runtime/` e `~/Library/LaunchAgents/`.

Il file `config/settings.example.yaml` è soltanto un template. Launcher e
installer non lo copiano e non creano `config/settings.yaml`.

I valori sensibili restano locali, fuori dal repository, dal plist e dai log.
Il processo non carica implicitamente `.env.local` o altri file dotenv.

## Provisioning dei segreti

L'operatore crea manualmente:

```text
<ROOT>/runtime/secrets/operational-scheduler.env
```

e applica:

```text
chmod 600 <ROOT>/runtime/secrets/operational-scheduler.env
```

Il file usa esclusivamente righe `KEY=VALUE` per le variabili PostgreSQL del
Runtime: host, porta, database, utente, password, sslmode e connect timeout.
Il launcher accetta soltanto i corrispondenti nomi `TPO_DATABASE_*`, tratta i
valori letteralmente e rifiuta chiavi arbitrarie, direttive `export`, command
substitution ed espressioni shell. Non inserire spazi intorno a `=`.

Installer e launcher non creano, copiano o correggono il file. Il file non
entra nel plist. Se secrets o settings mancano, oppure i permessi dei secrets
non sono esattamente `0600`, la CLI non viene invocata e non viene eseguito
alcun retry o fallback.

## Timezone e pianificazione

`launchd` interpreta `StartCalendarInterval` nella timezone locale del Mac.
Prima dell'installazione la timezone del Mac deve quindi essere
`Atlantic/Canary`.

La pianificazione è una sola volta al giorno alle 06:00. Il launcher calcola
separatamente la business date con `TZ=Atlantic/Canary` e passa sempre
`--business-time 06:00`; non usa offset UTC statici.

Una partenza successiva alle 06:00 non esegue catch-up. L'evento viene
registrato e un eventuale recupero viene avviato manualmente con la CLI.

## Launcher

Il launcher è:

```text
scripts/run_operational_schedule.sh
```

Costruisce esclusivamente:

```text
<ROOT>/.venv/bin/python -m src.tpo_core.cli.main \
  schedule execute \
  --settings <ROOT>/config/settings.yaml \
  --business-date <YYYY-MM-DD Atlantic/Canary> \
  --business-time 06:00 \
  --identity towerpower-scheduler \
  --confirm
```

Se settings o virtualenv mancano, il runtime non viene invocato.

## Installazione

L'installazione deve essere avviata esplicitamente dall'operatore:

```text
scripts/install_operational_launchagent.sh
```

L'installer valida launcher, template, virtualenv e settings, crea le directory
locali necessarie, materializza il plist in
`~/Library/LaunchAgents/com.towerpower.operational-scheduler.plist` e registra
il job nel dominio utente corrente. Non installa segreti e non modifica aree di
sistema.

In reinstallazione l'installer completa prima di ogni mutazione la validazione
di launcher, Python, template, settings, secrets e candidate plist. Preserva il
plist precedente e rileva se il job era loaded; soltanto dopo esegue `bootout`,
sostituzione atomica e `bootstrap` del nuovo job.

Se sostituzione o bootstrap falliscono, ripristina una sola volta il plist
precedente e re-bootstrap il job precedente soltanto quando era già loaded. Un
job precedentemente unloaded resta unloaded. Se il rollback fallisce,
l'installer conserva il backup e richiede recovery manuale. In first install,
un bootstrap fallito causa un solo tentativo di rimozione del nuovo plist. Se
la rimozione riesce, lo stato finale è **Not Installed**, l'installazione resta
fallita e l'installer termina con exit non-zero. Se la rimozione fallisce,
l'installer riporta `CLEANUP FAILED` e `MANUAL RECOVERY REQUIRED`, preserva lo
stato residuo per il recovery manuale e termina con exit non-zero, senza retry
né ulteriori mutazioni automatiche.

Se la cancellazione del backup dopo il bootstrap del nuovo job fallisce, la
reinstallazione è considerata fallita e attiva Full State Restoration. Per un
job precedentemente loaded l'installer ripristina il vecchio plist ed esegue
un singolo re-bootstrap del vecchio job; per un job precedentemente unloaded
ripristina soltanto il vecchio plist. Anche un rollback riuscito mantiene
l'installazione fallita con exit non-zero. Se il rollback fallisce, l'installer
riporta `ROLLBACK FAILED` e `MANUAL RECOVERY REQUIRED` e conserva il backup
soltanto quando serve al recovery manuale.

Settings, secrets e log non vengono rimossi o modificati.

## Stato

Lo stato del job utente può essere ispezionato con:

```text
launchctl print gui/$(id -u)/com.towerpower.operational-scheduler
```

Questa operazione non avvia una RUN.

## Log e retention

I log sono salvati in:

```text
<ROOT>/runtime/logs/operational-scheduler-*.log
```

Ogni file contiene timestamp di invocazione, business date, business time,
stdout e stderr sanitizzati ed exit code. Password, URL database, SQL, cause
tecniche private e traceback non vengono conservati.

Il launcher rimuove esclusivamente i propri log riconosciuti più vecchi di 30
giorni. Non cancella altri file runtime.

## Lock

Il lock process-level è una directory atomica:

```text
<ROOT>/runtime/operational-scheduler.lock
```

Un lock già presente blocca la seconda invocazione senza retry. Il launcher
rilascia il lock acquisito in uscita e sui segnali shell gestibili. Non rimuove
automaticamente un lock preesistente in base alla sola età.

## Exit code

| Codice | Esito | Azione automatica |
|---:|---|---|
| 0 | COMMITTED | registra e conclude |
| 1 | FAILED | registra, nessun retry |
| 2 | INPUT_INVALID | registra errore di configurazione, nessun retry |
| 3 | RUNTIME_UNAVAILABLE | registra e attende la prossima scadenza ordinaria |
| 4 | RECONCILIATION_REQUIRED | registra il contesto pubblico, nessun retry o seconda esecuzione |
| 5 | INTERNAL_ERROR | registra, nessun retry |

Il launcher propaga senza riclassificazione gli exit code restituiti dalla CLI.
Non esistono fallback, retry immediati o recovery automatico.

## Esecuzione mancata e recovery

Una esecuzione mancata non viene recuperata automaticamente. L'operatore
valuta i log e, se autorizzato, usa manualmente lo stesso comando
`tpo schedule execute` con business reference, identity e conferma esplicite.

La riconciliazione resta manuale. Il launcher non consulta il database e non
deduce l'esito di un commit incerto.

## Disinstallazione

La rimozione deve essere avviata esplicitamente:

```text
scripts/uninstall_operational_launchagent.sh
```

Lo script esegue il bootout nel dominio utente e rimuove soltanto il plist
installato. Conserva `config/settings.yaml`, `runtime/logs/`, lock e altri file
runtime. Non rimuove segreti o configurazioni locali.
