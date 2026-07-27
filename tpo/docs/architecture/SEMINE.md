# SEMINE

**Stato:** ARCHITECTURE FROZEN v1.0

## Scopo

Il Register SEMINE definisce l'identità e il ciclo di vita delle SEMINE realmente eseguite nel Tower Power Operations e ne preserva la tracciabilità dal materiale di partenza ai risultati produttivi.

Il Register distingue l'esecuzione produttiva dalla pianificazione e mantiene separata l'identità della SEMINA dagli eventi, dalle osservazioni e dai risultati che si verificano durante il ciclo.

## Definizione

Una SEMINA rappresenta l'avvio di un ciclo produttivo identificabile e tracciabile, concluso esclusivamente dalla chiusura del ciclo stesso.

Ogni SEMINA ha un'identità permanente e rappresenta un unico ciclo produttivo omogeneo, definito da:

- CULTIVAR;
- USO PRODUTTIVO;
- LOTTO DI SEME;
- versione del PROTOCOLLO applicato;
- data e operazione di avvio.

La quantità appartiene alla SEMINA e non genera nuove SEMINE. Più unità produttive fisicamente separate possono appartenere alla stessa SEMINA quando restano omogenee rispetto agli elementi costitutivi del ciclo.

L'unità quantitativa ufficiale della SEMINA è il peso del seme espresso in grammi. Eventuali unità operative sono derivate dal PROTOCOLLO o dall'USO PRODUTTIVO e non costituiscono il dato fondamentale della SEMINA.

## Principi Architetturali

- La SEMINA nasce esclusivamente quando il ciclo produttivo viene realmente avviato. Le intenzioni e le attività future appartengono al PIANO_SEMINE.
- Ogni SEMINA possiede un identificativo univoco, permanente e semanticamente neutro. L'identificativo costituisce il riferimento ufficiale per le relazioni con gli altri Register.
- La SEMINA rappresenta un fatto storico. Le correzioni preservano la tracciabilità delle modifiche e non cancellano la storia del ciclo produttivo.
- La SEMINA può essere registrata non appena sono disponibili tutti i dati costitutivi del ciclo. Le informazioni non costitutive possono essere aggiunte successivamente senza modificarne l'identità.
- Ogni SEMINA si riferisce a un solo LOTTO DI SEME e a una sola versione di PROTOCOLLO. L'impiego di lotti o protocolli differenti determina SEMINE distinte.
- La versione del PROTOCOLLO applicata all'avvio resta associata alla SEMINA. Le successive evoluzioni del PROTOCOLLO non modificano retroattivamente le SEMINE già eseguite.
- La SEMINA mantiene i riferimenti ufficiali agli altri Register e conserva un'istantanea dei dati essenziali necessari a ricostruire il contesto del ciclo al momento dell'avvio.
- Ogni SEMINA conserva la propria causa di origine, quale produzione pianificata, ordine cliente, reintegro stock, test o sperimentazione. La causa di origine costituisce contesto storico della SEMINA e non ne modifica l'identità.
- L'USO PRODUTTIVO è una caratteristica costitutiva della SEMINA e non cambia retroattivamente. La destinazione commerciale successiva di un prodotto idoneo e vendibile non modifica l'origine né l'identità della SEMINA.
- La SEMINA è il nodo centrale del ciclo produttivo. I Register che descrivono eventi, osservazioni o risultati del ciclo fanno riferimento al suo identificativo, senza introdurre nel Register SEMINE dipendenze dirette verso ciascun Register utilizzatore.
- Lo stato del ciclo è distinto dagli eventi del ciclo. Lo stato indica la fase ufficiale in cui si trova la SEMINA; gli eventi descrivono ciò che accade durante il ciclo.
- La SEMINA possiede un unico stato finale: CHIUSA. Lo scarto totale costituisce un possibile esito della chiusura e non uno stato autonomo.
- La SEMINA conserva una sola identità anche quando comprende più unità produttive. Le unità non idonee sono segnalate come problema o perdita parziale e vengono scartate senza creare frazioni operative o nuove SEMINE.
- Due cicli produttivi avviati separatamente restano SEMINE distinte e non possono essere fusi, anche quando condividono CULTIVAR, LOTTO DI SEME, PROTOCOLLO o data.

## Ciclo di vita della SEMINA

La SEMINA può assumere un solo stato ufficiale alla volta. Gli stati del ciclo sono:

```text
AVVIATA
    ↓
GERMINAZIONE
    ↓
LUCE
    ↓
CRESCITA
    ↓
PRONTA ALLA RACCOLTA
    ↓
CHIUSA
```
Il diagramma rappresenta il flusso ordinario del ciclo produttivo.

RACCOLTA non è uno stato della SEMINA. È un evento del ciclo produttivo che può verificarsi una o più volte prima della chiusura.

PROGRAMMATA non è uno stato della SEMINA: appartiene al PIANO_SEMINE e precede l'eventuale avvio reale del ciclo.

Una SEMINA è CHIUSA quando non esiste più alcuna quantità produttiva attiva riconducibile al ciclo. La chiusura registra uno dei seguenti esiti finali:

- raccolta completa;
- raccolta parziale con scarto;
- scarto totale;
- interruzione.

La chiusura può avvenire da qualunque stato attivo quando il ciclo produttivo termina definitivamente. Gli esiti straordinari, tra cui lo scarto totale o l'interruzione, possono determinare la chiusura anche prima della normale conclusione del flusso ordinario.

La chiusura non richiede necessariamente una RACCOLTA. L'identità della SEMINA resta invariata per l'intero ciclo e dopo la sua conclusione.

## Relazioni Architetturali

### VARIETA

La SEMINA non duplica l'identità generale della VARIETA. La relazione con VARIETA è determinata dalla CULTIVAR associata al ciclo e conserva il contesto storico esistente all'avvio.

### CULTIVAR

Ogni SEMINA è riferita a una sola CULTIVAR. La CULTIVAR è un elemento costitutivo dell'omogeneità del ciclo e il relativo riferimento ufficiale è accompagnato dall'istantanea dei dati essenziali necessari alla ricostruzione storica.

### USO PRODUTTIVO

Ogni SEMINA è riferita a un solo USO PRODUTTIVO, fissato all'avvio del ciclo. L'USO PRODUTTIVO determina l'obiettivo produttivo e il contesto di applicazione del PROTOCOLLO e non viene riscritto da una successiva destinazione commerciale.

### LOTTI DI SEME

Ogni SEMINA utilizza un solo LOTTO DI SEME e registra il peso effettivamente impiegato in grammi. LOTTI DI SEME rappresenta il materiale fisico di partenza; SEMINE ne registra l'utilizzo in uno specifico ciclo produttivo. L'impiego di LOTTI DI SEME differenti richiede SEMINE distinte.

### PROTOCOLLI

Ogni SEMINA applica una sola versione specifica di PROTOCOLLO. Il riferimento e l'istantanea iniziale preservano la procedura effettivamente applicata, indipendentemente dalle versioni successive. L'applicazione di PROTOCOLLI o versioni differenti richiede SEMINE distinte.

### RACCOLTE

Una SEMINA può produrre una, più o nessuna RACCOLTA. Ogni RACCOLTA si riferisce a una sola SEMINA e conserva l'origine del prodotto. L'eventuale aggregazione di prodotti provenienti da più RACCOLTE e da più SEMINE appartiene ai Register logistici o commerciali successivi.

### PIANO_SEMINE

PIANO_SEMINE registra ciò che deve essere eseguito; SEMINE registra ciò che è stato realmente avviato. Una voce programmata diventa una SEMINA soltanto con l'esecuzione fisica del ciclo. La SEMINA conserva la propria causa di origine senza confondere pianificazione ed esecuzione.
## Dati Minimi Obbligatori

Ogni SEMINA deve poter essere identificata e ricostruita nel tempo attraverso almeno i seguenti dati:

- identificativo permanente della SEMINA;
- data di avvio;
- CULTIVAR;
- USO PRODUTTIVO;
- LOTTO DI SEME;
- peso del seme utilizzato (grammi);
- versione del PROTOCOLLO applicato;
- stato corrente;
- causa di origine della SEMINA.

Gli altri dati operativi, osservazioni, misurazioni, eventi e risultati appartengono ai rispettivi Register specialistici.

## Integrità Storica

L'identità della SEMINA non cambia nel tempo.

Gli eventi registrati durante il ciclo descrivono ciò che accade alla SEMINA senza modificarne l'identità.

Le correzioni devono preservare la tracciabilità storica.

Una SEMINA può essere eliminata esclusivamente nel caso di registrazione errata prima dell'effettivo avvio fisico del ciclo produttivo. Dopo l'avvio, ogni errore viene corretto preservando la storia del Register.

La chiusura del ciclo non modifica né elimina l'identità della SEMINA.

## Principi di Evoluzione

Nuove informazioni potranno essere aggiunte esclusivamente se:

- non modificano il significato architetturale della SEMINA;
- non alterano l'identità del ciclo produttivo;
- non compromettono la compatibilità con le versioni precedenti;
- rispettano i principi definiti nel REGISTER_GOVERNANCE.

Ogni modifica architetturale segue integralmente il workflow di governance del Tower Power Operations.

---

**Stato documento:** ARCHITECTURE FROZEN v1.0


