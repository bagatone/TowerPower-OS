# TPO SYSTEM ARCHITECTURE

## Scopo

Questo documento descrive l'architettura logica ufficiale di Tower Power Operations (TPO): modello, confini, componenti, flussi e responsabilità.

Non definisce catalogo e ciclo di vita degli eventi, schema dei dati, regole operative, intestazioni dei fogli o stato del progetto. Questi contenuti appartengono ai documenti autorevoli indicati nella sezione finale.

## 1. Architectural Model

TPO adotta un'architettura **event-driven, modulare, orchestrata tramite pipeline selettive e con un solo Writer**.

- **Event-driven:** ogni modifica dello stato operativo nasce da un fatto rappresentato come evento TPOL.
- **Modulare:** ogni motore ha una responsabilità circoscritta e non scrive nei dati ufficiali.
- **Orchestrata:** l'Event Engine seleziona e coordina il percorso applicabile.
- **Pipeline selettive:** ogni evento attraversa soltanto controlli e motori pertinenti.
- **Single Writer:** il Google Sheets Writer è l'unico componente autorizzato ad applicare modifiche ai fogli ufficiali.

L'architettura distingue:

- **Facts:** eventi operativi immutabili;
- **State:** stato operativo corrente e proiezioni derivate;
- **Configuration:** parametri, schemi e regole ufficiali che determinano il comportamento del sistema.

I Facts devono essere ricostruibili attraverso un registro autorevole degli eventi, senza che questo documento ne imponga il supporto fisico. Lo State ufficiale risiede nei fogli Google del TPO. Le proiezioni derivate non sono fonti autonome. La Configuration proviene esclusivamente dalle fonti ufficiali.

Il sistema separa inoltre:

- **Write Path:** elabora un evento e produce modifiche controllate allo State;
- **Read Path:** legge lo State e produce viste o read model senza modificarlo.

## 2. Confini del sistema

### Elementi esterni

- operatore;
- canali di ingresso: chat, CLI, API e inserimento manuale;
- Google Sheets come piattaforma del datastore operativo ufficiale;
- documenti normativi e di configurazione.

Google Sheets è una piattaforma esterna, ma i fogli ufficiali appartengono al confine informativo del TPO.

### Componenti interni

- Event Engine;
- Source Gate;
- Rules Engine;
- Calendar Engine;
- Production Planner;
- Resource Engine;
- Google Sheets Writer;
- Photo Archivist;
- AGGIORNAMI, come consumer operativo del Read Path.

### Confine di ingresso

```text
CANALI ESTERNI
↓
NORMALIZZAZIONE DELL'INPUT
↓
EVENTO TPOL SINTATTICAMENTE VALIDO
↓
EVENT ENGINE
↓
SOURCE GATE
↓
VALIDAZIONE SEMANTICA
```

Il confine di ingresso interpreta l'eventuale testo libero, estrae soltanto i dati presenti e costruisce TPOL. Non applica regole di dominio, non completa dati mancanti e non scrive.

L'Event Engine riceve esclusivamente un evento TPOL sintatticamente valido: non interpreta testo libero e non costruisce TPOL. La validazione sintattica controlla il formato dell'evento; la validazione semantica avviene dopo il Source Gate rispetto alle fonti e alle regole applicabili.

## 3. Componenti e responsabilità

### Event Engine

È l'orchestratore del Write Path. Identifica il tipo di evento, seleziona percorso, fonti e motori applicabili, coordina l'elaborazione e aggrega i risultati in un unico WritePlan. Non applica logica specialistica e non scrive. I dettagli appartengono a `EVENT_ENGINE.md`.

### Source Gate

Verifica che le fonti obbligatorie per il percorso selezionato siano disponibili e lette, fornisce i dati ufficiali con provenance e blocca il flusso con `SOURCE_NOT_AVAILABLE` quando necessario. Non applica regole di dominio, non seleziona motori e non scrive.

### Rules Engine

Applica `OPERATING_RULES.md`, valida semanticamente l'evento e rileva dati mancanti, incoerenze e blocchi. Non definisce nuove regole e non scrive.

### Calendar Engine

È la fonte temporale unica. Normalizza il contesto temporale e produce date e scadenze per i percorsi che lo richiedono. Le regole temporali specifiche appartengono a `OPERATING_RULES.md`.

### Production Planner

Calcola le conseguenze produttive degli eventi applicabili usando parametri ufficiali e produce proposte per il WritePlan. Non viene eseguito per eventi estranei alla pianificazione e non scrive.

### Resource Engine

Calcola fabbisogni e disponibilità usando inventario, ricette e movimenti ufficiali; produce verifiche e proposte per il WritePlan. Non viene eseguito per eventi senza effetti sulle risorse e non scrive.

### Photo Archivist

Verifica il collegamento fra fotografie e lotti sulla base dell'identificazione fornita o confermata dall'operatore e produce una proposta tracciabile. Non deduce dati non osservabili, non modifica automaticamente altri domini e non scrive.

### Google Sheets Writer

È l'unico componente autorizzato ad applicare modifiche ai fogli ufficiali. Riceve il WritePlan, verifica struttura e precondizioni, esegue il dry-run e applica lo stesso piano soltanto dopo conferma esplicita. Restituisce un esito verificabile. Non interpreta eventi, non applica regole di dominio e non modifica il WritePlan.

### AGGIORNAMI

È un consumer del Read Path. Legge dati ufficiali o read model derivati e presenta la vista operativa giornaliera. Non è una fonte ufficiale, un motore di dominio o un Writer. Il contenuto della vista è governato da `OPERATING_RULES.md`.

## 4. Write Path

```text
EVENTO TPOL SINTATTICAMENTE VALIDO
↓
EVENT ENGINE
↓
SELEZIONE DEL PERCORSO APPLICABILE
↓
SOURCE GATE
↓
VALIDAZIONE SEMANTICA E RULES ENGINE
↓
MOTORI DI DOMINIO APPLICABILI
↓
WritePlan UNICO
↓
DRY-RUN
↓
CONFERMA ESPLICITA
↓
GOOGLE SHEETS WRITER
↓
FOGLI GOOGLE UFFICIALI
↓
REGISTRAZIONE DELL'ESITO
```

La pipeline è selettiva: un evento usa soltanto i motori necessari. La selezione dipende dal tipo di evento e dalla Configuration ufficiale, non da supposizioni.

I motori restituiscono risultati, provenance o errori senza modificare lo State. L'Event Engine li aggrega in un solo WritePlan. Se una validazione fallisce, il piano non viene applicato.

Il dry-run verifica l'intero WritePlan. La conferma vale soltanto per il piano verificato; ogni variazione richiede una nuova verifica e una nuova conferma.

L'esito dell'apply rimane collegato all'evento e al WritePlan nel registro autorevole degli eventi, senza alterare l'evento originario. Il supporto fisico del registro non è prescritto qui.

## 5. Read Path

```text
FOGLI GOOGLE UFFICIALI
↓
LETTURA E COMPOSIZIONE
↓
READ MODEL O VISTA DERIVATA
↓
CONSUMER
```

Il Read Path legge le fonti ufficiali e può produrre read model o viste derivate. Non modifica lo State.

Un read model deriva dalle fonti ufficiali, può essere rigenerato, non acquisisce autorità autonoma e non introduce regole operative proprie.

Sono consumer del Read Path AGGIORNAMI, dashboard, reportistica, API di lettura e interfacce future. I consumer non accedono alla logica interna dell'Event Engine e non modificano lo State. La loro aggiunta non cambia il Write Path.

## 6. Fonti autorevoli

I fogli Google del TPO costituiscono il datastore operativo ufficiale. Responsabilità, relazioni e campi appartengono a `TPO_DATA_DICTIONARY.md`; le intestazioni appartengono a `TPO_SHEETS_SCHEMA.md`.

A livello architetturale:

- ogni dato operativo viene letto dalla propria fonte ufficiale;
- ogni proiezione rimane riconducibile ai dati e agli eventi di origine;
- lo stock è una proiezione derivata governata dagli eventi e dai movimenti ufficiali;
- la Configuration proviene dalle fonti ufficiali e non viene duplicata nei motori;
- i documenti normativi governano principi e regole, ma non sostituiscono i dati operativi;
- il registro autorevole degli eventi conserva Facts, cronologia ed esiti senza imporre un nuovo datastore.

La mappatura dettagliata fra domini, fogli e proiezioni appartiene ai documenti dei dati.

## 7. Flussi architetturali principali

### Ciclo dell'ordine

```text
ORDINE
↓
IMPEGNO COMMERCIALE E PRENOTAZIONE
↓
PIANIFICAZIONE
↓
PRODUZIONE E LOTTI
↓
RACCOLTA
↓
MOVIMENTI E STOCK DERIVATO
↓
ASSEGNAZIONE
↓
CONSEGNA
↓
MOVIMENTO DI USCITA E AGGIORNAMENTO DELLE PROIEZIONI
```

Ogni passaggio è generato da un evento o da un effetto derivato previsto dall'architettura. Eventi atomici, entità, relazioni e regole di transizione appartengono ai documenti specialistici.

Il ciclo non è una catena di aggiornamenti manuali fra fogli: ogni evento attraversa il proprio Write Path selettivo e può aggiornare più proiezioni mediante un unico WritePlan.

### Documentazione fotografica

Una fotografia identificata dall'operatore entra come evento TPOL, viene verificata attraverso il Source Gate e usa il Photo Archivist come motore applicabile. L'eventuale aggiornamento confluisce nel WritePlan e raggiunge i fogli soltanto tramite il Writer.

## 8. Accoppiamento e dipendenze

I motori operano su concetti di dominio e dati forniti dal Source Gate. Non replicano la logica di accesso, non conoscono le intestazioni e non dipendono direttamente dall'API di Google Sheets.

La struttura fisica dei fogli rimane confinata alla lettura e al Google Sheets Writer ed è governata da `TPO_SHEETS_SCHEMA.md`.

L'Event Engine conosce i percorsi applicabili, ma non incorpora la logica dei motori. I motori non si richiamano circolarmente: il coordinamento avviene tramite l'orchestratore e i risultati confluiscono nel WritePlan.

I consumer dipendono dal Read Path, non dal core di scrittura. Questi confini non introducono servizi distribuiti, event bus, nuovi datastore o un Query Layer obbligatorio.

## 9. Autorità documentale

- Principi sovraordinati: `TPO_CORE_PRINCIPLES.md`.
- Comportamento, ciclo di vita e catalogo degli eventi: `EVENT_ENGINE.md`.
- Regole operative e temporali: `OPERATING_RULES.md`.
- Entità, significato dei dati e relazioni: `TPO_DATA_DICTIONARY.md`.
- Intestazioni e struttura fisica dei fogli: `TPO_SHEETS_SCHEMA.md`.
- Stato del progetto e baseline: `PROJECT_SNAPSHOT_v1.0.md`.
- Evoluzione e modifiche approvate: `CHANGELOG.md`.

In caso di conflitto, prevale la gerarchia stabilita da `TPO_CORE_PRINCIPLES.md`. Questo documento rimane l'autorità per modello logico, componenti, confini, flussi e responsabilità architetturali.
