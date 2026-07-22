# TPO EVENT ENGINE

## 1. Scopo e responsabilità

Questo documento descrive il funzionamento logico dell'Event Engine di Tower Power Operations (TPO).

L'Event Engine ha una sola responsabilità:

> trasformare un evento operativo in un unico WritePlan coerente.

Per svolgere questa responsabilità, l'Event Engine:

- riceve un evento TPOL sintatticamente valido;
- seleziona il percorso applicabile;
- coordina Source Gate e motori specialistici;
- aggrega i risultati in un unico WritePlan;
- coordina dry-run, conferma, consegna al Writer e registrazione dell'esito;
- propaga blocchi ed errori senza nasconderli.

L'Event Engine non interpreta testo libero, non applica direttamente modifiche allo State, non sostituisce i motori specialistici e non scrive nei fogli ufficiali.

## 2. Evento TPOL

Un evento TPOL è una rappresentazione normalizzata, identificabile e tracciabile di un Fact operativo comunicato al TPO.

Le informazioni logiche minime sono:

- `event_id`;
- `event_type`;
- `payload`;
- `timestamp`;
- `operator`;
- `source`.

Questo elenco descrive il contenuto logico minimo, non tipi fisici, colonne o formati di persistenza.

L'evento entra nell'Event Engine già sintatticamente valido. La validazione sintattica verifica struttura e presenza delle informazioni logiche richieste; la validazione semantica avviene successivamente rispetto alle fonti e alle regole applicabili.

Il canale indicato da `source` documenta l'origine dell'input, ma non diventa automaticamente fonte autorevole dei dati operativi. L'autorevolezza viene verificata attraverso le fonti ufficiali del TPO.

`event_id` identifica stabilmente il Fact, non deve essere riutilizzato e permette di collegare evento, elaborazione, WritePlan ed esito.

Nel modello TPO:

- l'evento TPOL rappresenta un **Fact**;
- lo **State** è la proiezione operativa modificabile;
- la **Configuration** guida selezione e validazione;
- il **WritePlan** è la proposta controllata di modifica dello State.

## 3. Confini

### Input Boundary

Normalizza l'input, interpreta l'eventuale testo libero, costruisce TPOL ed esegue la validazione sintattica prima dell'ingresso nell'Event Engine. Non applica logica di dominio e non modifica lo State.

### Source Gate

Verifica la disponibilità delle fonti richieste dalla pipeline selezionata e fornisce dati ufficiali con provenance. Se una fonte obbligatoria non è disponibile, il flusso viene bloccato prima della produzione del WritePlan.

### Motori specialistici

Applicano la propria logica di dominio usando evento, Configuration e fonti ufficiali. Restituiscono risultati, proposte o errori all'Event Engine; non scrivono direttamente e non si sostituiscono all'orchestratore.

### Writer

Riceve il WritePlan verificato e confermato e lo applica senza reinterpretarlo, modificarlo o introdurre decisioni di dominio. La responsabilità dell'Event Engine termina con il coordinamento del processo e la registrazione dell'esito ricevuto.

## 4. Event Lifecycle

```text
EVENTO NORMALIZZATO
↓
VALIDAZIONE SINTATTICA
↓
EVENT ENGINE
↓
SELEZIONE DELLA PIPELINE
↓
SOURCE GATE
↓
VALIDAZIONE SEMANTICA
↓
MOTORI APPLICABILI
↓
WritePlan
↓
DRY-RUN
↓
CONFERMA
↓
WRITER
↓
PERSISTENZA
↓
ESITO E TRACCIABILITÀ
```

1. **Evento normalizzato:** l'Input Boundary rappresenta il Fact in TPOL senza completare dati mancanti.
2. **Validazione sintattica:** verifica che TPOL sia formalmente accettabile; un evento non valido non entra nell'Event Engine.
3. **Event Engine:** riceve l'evento e avvia l'orchestrazione senza modificare lo State.
4. **Selezione della pipeline:** determina fonti, controlli e motori applicabili.
5. **Source Gate:** rende disponibili le fonti obbligatorie o blocca il percorso.
6. **Validazione semantica:** confronta l'evento con State, Configuration e regole ufficiali.
7. **Motori applicabili:** producono risultati di dominio senza scrivere.
8. **WritePlan:** aggrega in una proposta unica tutte le modifiche necessarie.
9. **dry-run:** verifica il piano completo senza applicarlo.
10. **Conferma:** autorizza esclusivamente il WritePlan verificato.
11. **Writer:** riceve il piano autorizzato e tenta di applicarlo senza reinterpretazione.
12. **Persistenza:** rappresenta la modifica effettiva dei dati ufficiali, distinta dall'intenzione descritta dal WritePlan.
13. **Esito e tracciabilità:** registrano il risultato dell'applicazione e lo collegano all'evento e al piano.

Ogni passaggio può bloccare il ciclo senza trasformare il blocco in un successo apparente.

## 5. Selezione delle pipeline

Non esiste una pipeline universale che obblighi ogni evento ad attraversare tutti i motori.

L'Event Engine seleziona il percorso in base a:

- `event_type`;
- Configuration ufficiale;
- domini coinvolti;
- fonti richieste.

A seconda dell'evento possono non essere applicabili Calendar Engine, Production Planner, Resource Engine o Photo Archivist.

L'Event Engine conosce quali componenti coinvolgere, ma non incorpora la loro logica interna. I motori non si richiamano circolarmente, non scrivono nello State e restituiscono i propri risultati all'orchestratore.

La selezione deve essere deterministica: lo stesso evento, lo stesso State e la stessa Configuration producono lo stesso percorso applicabile.

## 6. WritePlan

Il WritePlan è l'unica proposta coerente di modifica prodotta dall'elaborazione di un singolo evento.

L'Event Engine produce il WritePlan aggregando i risultati dei motori applicabili. Il piano:

- è collegato all'evento di origine;
- contiene tutte le modifiche proposte per quella elaborazione;
- è unico per quella elaborazione;
- non costituisce un esito;
- non modifica direttamente lo State;
- può non essere prodotto quando il flusso è bloccato.

Il percorso di autorizzazione è:

```text
WritePlan PROPOSTO
↓
DRY-RUN
↓
WritePlan VERIFICATO
↓
CONFERMA
↓
APPLY
↓
ESITO DELL'APPLICAZIONE
```

La conferma vale esclusivamente per il WritePlan verificato. Se il piano cambia, il dry-run deve essere ripetuto e la conferma precedente non è più valida.

Il WritePlan proposto descrive un'intenzione, il WritePlan verificato descrive l'intenzione sottoposta ai controlli e l'esito applicato descrive ciò che il Writer ha effettivamente persistito.

## 7. Validazioni, errori ed esiti

Il ciclo deve distinguere almeno queste categorie concettuali:

- evento sintatticamente non valido;
- fonte non disponibile;
- errore semantico;
- regola operativa violata;
- conflitto con lo State;
- conferma assente, scaduta o non valida;
- errore di scrittura;
- duplicato o doppio apply.

Il documento non assegna codici specifici a queste categorie e non ridefinisce le regole dei singoli domini.

Gli esiti minimi dell'applicazione sono:

- **riuscito:** tutte le modifiche previste sono state applicate;
- **fallito senza modifiche:** nessuna modifica prevista è stata applicata;
- **parziale:** soltanto una parte delle modifiche previste è stata applicata.

L'obiettivo è l'atomicità logica: tutte le modifiche necessarie vengono preparate e verificate nello stesso WritePlan. Il datastore può non garantire atomicità fisica completa; un esito parziale deve quindi essere rilevato, registrato e mai presentato come riuscito.

Ogni errore deve indicare il punto del ciclo in cui si è verificato e impedire che un'elaborazione incompleta venga rappresentata come completata.

## 8. Idempotenza e duplicati

Uno stesso Fact non deve produrre due applicazioni involontarie.

`event_id` permette di riconoscere un evento già ricevuto o elaborato. Un retry dello stesso evento non costituisce automaticamente un nuovo Fact e deve rimanere collegato alla stessa identità.

Un WritePlan già applicato non deve essere applicato nuovamente. Prima dell'apply deve essere possibile riconoscere almeno:

- evento già elaborato;
- elaborazione già in corso;
- WritePlan già applicato;
- tentativo precedente fallito o parziale.

Ogni tentativo, incluso un retry, deve essere riconoscibile e tracciato. Questo requisito è logico e non impone un meccanismo fisico specifico.

## 9. Registro autorevole e tracciabilità

Il registro autorevole degli eventi è un requisito logico del TPO. Questo documento non prescrive che sia realizzato come foglio, database, file, tabella, event bus o datastore aggiuntivo.

Il registro deve consentire di ricostruire:

```text
EVENTO
↓
IDENTITÀ E ORIGINE
↓
FONTI CONSULTATE
↓
VALIDAZIONI
↓
PIPELINE SELEZIONATA
↓
MOTORI ESEGUITI
↓
WritePlan
↓
DRY-RUN
↓
CONFERMA
↓
TENTATIVI DI APPLY
↓
ESITO
↓
EVENTUALI RETTIFICHE
```

Il Fact originario è immutabile e non viene corretto mediante sovrascrittura. Una rettifica deve essere rappresentata da un nuovo Fact collegato all'evento precedente. Una nuova elaborazione autorizzata deve conservare il collegamento all'identità e alla cronologia originarie.

Evento, fonti, WritePlan, conferma, tentativi ed esito devono rimanere correlabili per audit e ricostruzione dello State.

## 10. Autorità documentale

- `TPO_CORE_PRINCIPLES.md` governa i principi sovraordinati.
- `SYSTEM_ARCHITECTURE.md` governa il modello architetturale generale, i componenti, il Write Path e il Read Path.
- `OPERATING_RULES.md` governa le regole operative.
- `TPO_DATA_DICTIONARY.md` governa la struttura logica dei dati.
- `TPO_SHEETS_SCHEMA.md` governa il mapping fisico sui fogli.
- `PROJECT_SNAPSHOT_v1.0.md` governa lo stato e il perimetro della baseline.

Questo documento governa il comportamento logico dell'Event Engine. Non governa schema fisico, regole di dominio, implementazione o stato del progetto.
