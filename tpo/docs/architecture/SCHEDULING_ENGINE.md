# SCHEDULING_ENGINE

**Stato:** ARCHITECTURE FREEZE v1.0

## Scopo

SCHEDULING_ENGINE definisce l'architettura dello Scheduling Engine del Tower Power Operations.

Lo Scheduling Engine esegue esclusivamente la logica di generazione automatica degli ORDINI a partire dai PROGRAMMI_FORNITURA autorizzati.

## Definizione

SCHEDULING_ENGINE non è un Register.

È un Engine applicativo che legge i Register autorizzati ed esegue la logica necessaria a determinare e generare gli ORDINI dovuti.

Ogni esecuzione dello Scheduling Engine costituisce una RUN.

Ogni RUN possiede un identificativo univoco e rappresenta esclusivamente una singola esecuzione dell'Engine.

La RUN costituisce il contenitore logico della tracciabilità dell'esecuzione, non appartiene ai Register e non modifica alcun Register.

Tutte le informazioni di log, errori, tempi di esecuzione ed esito appartengono alla RUN.

I Register conservano la verità del dominio. Gli Engine eseguono logica utilizzando i Register, senza assumerne le responsabilità.

## Principi Architetturali

- Lo Scheduling Engine legge esclusivamente i PROGRAMMI_FORNITURA nello stato ATTIVO.
- Un PROGRAMMA_FORNITURA nello stato SOSPESO o TERMINATO non genera nuovi ORDINI.
- Lo Scheduling Engine determina le occorrenze utilizzando la configurazione temporale della singola riga, la finestra operativa, l'orario di generazione, la data di inizio e la data di fine, quando presente.
- Ogni ORDINE generato automaticamente mantiene un riferimento permanente al PROGRAMMA_FORNITURA di origine e alla riga o alle righe che lo hanno originato.
- Lo Scheduling Engine raggruppa in un unico ORDINE le righe compatibili dello stesso PROGRAMMA_FORNITURA.
- Date previste di CONSEGNA differenti generano ORDINI distinti.
- Lo Scheduling Engine è idempotente.
- L'esecuzione ripetuta, automatica o manuale, non crea duplicati della stessa occorrenza.
- Lo Scheduling Engine non modifica direttamente PROGRAMMI_FORNITURA, STOCK, SEMINE, RACCOLTE, CONSEGNE o MOVIMENTI_MAGAZZINO.
- Lo Scheduling Engine crea esclusivamente ORDINI.
- Lo Scheduling Engine non crea direttamente PRENOTAZIONI.
- La PRENOTAZIONE e il calcolo del PRENOTATO appartengono al dominio ORDINI come conseguenza logica della registrazione dell'ORDINE.
- Il controllo `DISPONIBILE < PRENOTATO` non appartiene allo Scheduling Engine, ma al controllo di integrità dello STOCK o all'Alert Engine.
- Lo Scheduling Engine non costruisce direttamente il PIANO_SEMINE.
- Gli ORDINI generati costituiscono input del Planning Engine.
- L'errore isolato di una riga non blocca l'elaborazione delle altre righe valide.
- Ogni esecuzione dello Scheduling Engine è tracciata.
- L'orario predefinito di generazione è una configurazione di sistema con valore iniziale 05:00.
- Il singolo PROGRAMMA_FORNITURA può sovrascrivere l'orario predefinito di generazione.
- Il fuso orario ufficiale dello Scheduling Engine è Atlantic/Canary.
- Tutti i calcoli di calendario, data e ora utilizzano il fuso orario Atlantic/Canary.
- Le modifiche a un PROGRAMMA_FORNITURA hanno effetto esclusivamente sulle future occorrenze non ancora generate.
- La sospensione di un PROGRAMMA_FORNITURA non annulla né modifica automaticamente gli ORDINI già generati.
- Gli eventuali annullamenti appartengono al dominio ORDINI.
- La riattivazione di un PROGRAMMA_FORNITURA SOSPESO riprende la generazione dalle future occorrenze senza generare retroattivamente gli ORDINI saltati durante la sospensione.
- Un PROGRAMMA_FORNITURA TERMINATO non può essere riattivato e non viene elaborato dallo Scheduling Engine.
- Il recupero delle occorrenze scadute riguarda esclusivamente quelle ancora operative.
- Il recupero non genera ORDINI relativi a date previste di CONSEGNA già trascorse.
- Lo Scheduling Engine può essere eseguito automaticamente, manualmente da un operatore autorizzato o in modalità simulazione.
- La modalità simulazione non modifica alcun Register e non produce effetti operativi.

## Responsabilità

Lo Scheduling Engine è responsabile esclusivamente di:

- leggere i PROGRAMMI_FORNITURA ATTIVI;
- calcolare le occorrenze dovute;
- applicare finestra operativa, calendario e orario;
- raggruppare le righe compatibili;
- impedire la duplicazione delle occorrenze;
- creare ORDINI;
- costituire una RUN per ogni esecuzione;
- registrare nella RUN le informazioni di log, gli errori, i tempi di esecuzione e l'esito;
- supportare la modalità simulazione.

## Confini dell'Engine

Lo Scheduling Engine non è responsabile di:

- modificare PROGRAMMI_FORNITURA;
- gestire direttamente PRENOTAZIONI;
- verificare o correggere lo STOCK;
- generare ALLARMI ROSSI;
- costruire il PIANO_SEMINE;
- creare SEMINE;
- registrare RACCOLTE;
- creare CONSEGNE;
- creare MOVIMENTI_MAGAZZINO;
- emettere FATTURE;
- annullare automaticamente ORDINI già generati.

## Input

Gli input architetturali dello Scheduling Engine comprendono almeno:

- CURRENT_SYSTEM_DATE ufficiale del sistema;
- fuso orario Atlantic/Canary;
- modalità di esecuzione;
- configurazione di sistema;
- PROGRAMMI_FORNITURA ATTIVI;
- righe e relative configurazioni temporali;
- ORDINI già esistenti necessari alla verifica di idempotenza.

CURRENT_SYSTEM_DATE rappresenta il riferimento temporale ufficiale utilizzato da tutti gli Engine del Tower Power Operations.

Tutte le decisioni temporali vengono calcolate utilizzando CURRENT_SYSTEM_DATE e il fuso orario Atlantic/Canary.

CURRENT_SYSTEM_DATE non coincide necessariamente con l'ora di avvio del processo, ma rappresenta il riferimento temporale ufficiale dell'elaborazione.

## Output

Gli output architetturali dello Scheduling Engine comprendono almeno:

- ORDINI generati;
- anteprima degli ORDINI in modalità simulazione;
- esito dell'esecuzione;
- righe elaborate;
- righe saltate;
- errori;
- log e tracciabilità dell'esecuzione.

## Regole di Selezione

Lo Scheduling Engine seleziona esclusivamente i PROGRAMMI_FORNITURA nello stato ATTIVO.

Per ogni riga determina le occorrenze da generare utilizzando:

- configurazione temporale della singola riga;
- finestra operativa;
- orario di generazione;
- data di inizio;
- data di fine, quando presente.

Un PROGRAMMA_FORNITURA nello stato SOSPESO o TERMINATO non viene selezionato per la generazione di nuovi ORDINI.

Le modifiche a un PROGRAMMA_FORNITURA si applicano esclusivamente alle future occorrenze non ancora generate.

## Regole di Raggruppamento

Quando più righe dello stesso PROGRAMMA_FORNITURA:

- appartengono allo stesso CLIENTE;
- hanno la stessa data prevista di CONSEGNA;
- devono essere generate nella stessa occorrenza;

lo Scheduling Engine le raggruppa in un unico ORDINE.

Date previste di CONSEGNA differenti generano ORDINI distinti.

Ogni ORDINE generato conserva il riferimento permanente al PROGRAMMA_FORNITURA e alla riga o all'insieme di righe che lo hanno originato.

## Idempotenza

Lo Scheduling Engine deve essere idempotente.

L'esecuzione ripetuta, automatica o manuale, non deve creare duplicati della stessa occorrenza.

Prima della generazione, lo Scheduling Engine verifica che non esista già un ORDINE corrispondente alla stessa combinazione logica di:

- PROGRAMMA_FORNITURA;
- riga o insieme di righe di origine;
- occorrenza;
- data prevista di CONSEGNA.

## Gestione Temporale

L'orario predefinito di generazione è una configurazione di sistema.

Il valore iniziale è 05:00.

Il singolo PROGRAMMA_FORNITURA può sovrascrivere il valore predefinito.

Il fuso orario ufficiale dello Scheduling Engine è Atlantic/Canary.

Tutti i calcoli di calendario, data e ora utilizzano il fuso orario Atlantic/Canary.

La sospensione di un PROGRAMMA_FORNITURA non annulla né modifica automaticamente gli ORDINI già generati. Gli eventuali annullamenti appartengono al dominio ORDINI.

La riattivazione di un PROGRAMMA_FORNITURA SOSPESO riprende la generazione dalle future occorrenze. Gli ORDINI saltati durante il periodo di sospensione non vengono generati retroattivamente.

Un PROGRAMMA_FORNITURA TERMINATO non può essere riattivato e non viene elaborato dallo Scheduling Engine.

## Recupero delle Occorrenze

Se lo Scheduling Engine non viene eseguito all'orario previsto, alla successiva esecuzione recupera le occorrenze scadute ma ancora operative.

Il recupero non genera ORDINI retroattivi ormai inutili e non genera un ORDINE quando la relativa data prevista di CONSEGNA è già trascorsa.

Le regole di recuperabilità sono deterministiche e tracciabili.

## Gestione degli Errori

Se una singola riga di PROGRAMMA_FORNITURA è temporalmente invalida o incompleta:

- l'ORDINE relativo a quella riga non viene generato;
- l'errore viene registrato;
- l'elaborazione delle altre righe valide continua.

Un errore isolato non blocca l'intera esecuzione.

## Modalità di Esecuzione

Lo Scheduling Engine può essere eseguito:

- automaticamente secondo pianificazione;
- manualmente da un operatore autorizzato;
- in modalità simulazione.

Le esecuzioni automatiche e manuali applicano le medesime regole di selezione, raggruppamento, idempotenza, gestione temporale, recupero e gestione degli errori.

## Modalità Simulazione

La modalità simulazione:

- applica le stesse regole di selezione e raggruppamento;
- mostra gli ORDINI che verrebbero generati;
- mostra le righe saltate e gli errori;
- non crea ORDINI;
- non crea PRENOTAZIONI;
- non modifica alcun Register;
- non produce effetti operativi.

## Tracciabilità delle Esecuzioni

Ogni esecuzione dello Scheduling Engine costituisce una RUN.

Ogni RUN possiede un identificativo univoco e rappresenta esclusivamente una singola esecuzione dell'Engine.

La RUN costituisce il contenitore logico della tracciabilità dell'esecuzione. Non appartiene ai Register e non modifica alcun Register.

Tutte le informazioni di log, errori, tempi di esecuzione ed esito appartengono alla RUN.

Ogni RUN deve essere tracciata attraverso almeno:

- identificativo univoco della RUN;
- data e ora di avvio;
- data e ora di conclusione;
- modalità di esecuzione;
- programmi analizzati;
- righe analizzate;
- ORDINI creati;
- righe saltate;
- errori;
- esito finale.

Ogni RUN possiede uno dei seguenti stati finali iniziali:

- SUCCESS;
- SUCCESS_WITH_WARNINGS;
- FAILED.

Lo stato finale rappresenta esclusivamente l'esito complessivo della RUN.

Lo stato della RUN non modifica gli ORDINI, i PROGRAMMI_FORNITURA o alcun altro Register.

## Relazioni Architetturali

### PROGRAMMI_FORNITURA

Lo Scheduling Engine legge esclusivamente i PROGRAMMI_FORNITURA nello stato ATTIVO e non li modifica.

PROGRAMMI_FORNITURA conserva gli accordi operativi continuativi e le configurazioni necessarie alla determinazione delle occorrenze.

### ORDINI

Lo Scheduling Engine crea esclusivamente ORDINI.

Ogni ORDINE generato automaticamente mantiene il riferimento permanente al PROGRAMMA_FORNITURA e alla riga o alle righe che lo hanno originato.

Lo Scheduling Engine non annulla né modifica automaticamente gli ORDINI già generati.

### PRENOTAZIONI

Lo Scheduling Engine non crea direttamente PRENOTAZIONI.

La PRENOTAZIONE e il calcolo del PRENOTATO appartengono al dominio ORDINI come conseguenza logica della registrazione dell'ORDINE.

### STOCK

Lo Scheduling Engine non verifica né corregge lo STOCK e non lo modifica.

Il controllo `DISPONIBILE < PRENOTATO` appartiene al controllo di integrità dello STOCK o all'Alert Engine.

### Planning Engine

Gli ORDINI generati costituiscono input del Planning Engine.

Lo Scheduling Engine non costruisce direttamente il PIANO_SEMINE.

### SEMINE, RACCOLTE, CONSEGNE e MOVIMENTI_MAGAZZINO

Lo Scheduling Engine non modifica direttamente:

- SEMINE;
- RACCOLTE;
- CONSEGNE;
- MOVIMENTI_MAGAZZINO.

Non crea SEMINE, non registra RACCOLTE, non crea CONSEGNE e non crea MOVIMENTI_MAGAZZINO.

### FATTURE

Lo Scheduling Engine non emette FATTURE.

## Invarianti

- Nessun ORDINE duplicato per la stessa occorrenza.
- Nessuna scrittura sui Register non autorizzati.
- Nessuna elaborazione di PROGRAMMI_FORNITURA SOSPESI o TERMINATI.
- Nessuna generazione retroattiva relativa a CONSEGNE già trascorse.
- Nessun effetto persistente in modalità simulazione.
- Ogni ORDINE automatico conserva l'origine completa.
- L'errore di una riga non blocca le altre righe valide.
- Tutti i calcoli temporali utilizzano Atlantic/Canary.

## Principi di Evoluzione

Lo Scheduling Engine può evolvere esclusivamente se:

- continua a leggere esclusivamente i Register autorizzati;
- continua a creare esclusivamente ORDINI;
- non assume responsabilità appartenenti ai Register o ad altri Engine;
- mantiene l'idempotenza della generazione;
- mantiene il riferimento permanente all'origine di ogni ORDINE automatico;
- mantiene separata la gestione delle PRENOTAZIONI;
- non modifica PROGRAMMI_FORNITURA, STOCK, SEMINE, RACCOLTE, CONSEGNE o MOVIMENTI_MAGAZZINO;
- non costruisce direttamente il PIANO_SEMINE;
- preserva la tracciabilità delle esecuzioni;
- mantiene privi di effetti persistenti i risultati della modalità simulazione;
- utilizza Atlantic/Canary per tutti i calcoli temporali;
- rispetta integralmente REGISTER_GOVERNANCE.

I Register conservano la verità del dominio. Lo Scheduling Engine esegue esclusivamente la logica di generazione automatica degli ORDINI utilizzando i Register autorizzati.
