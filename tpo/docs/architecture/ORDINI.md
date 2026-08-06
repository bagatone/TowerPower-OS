# ORDINI

**Stato:** ARCHITECTURE FREEZE v1.0

## Scopo

Il Register ORDINI definisce le richieste di prodotto registrate nel Tower Power Operations e ne preserva il riferimento operativo per la pianificazione delle CONSEGNE e per la gestione delle PRENOTAZIONI.

Il Register mantiene separata la richiesta di prodotto dalla vendita, dalla disponibilità fisica rappresentata nello STOCK e dall'esecuzione delle CONSEGNE.

## Definizione

Un ORDINE rappresenta esclusivamente una richiesta di prodotto e non una vendita.

Ogni ORDINE possiede un identificativo univoco, permanente e semanticamente neutro, appartiene ad un solo CLIENTE e può contenere una o più righe di prodotto.

Ogni riga di ORDINE fa riferimento ad una sola VARIETÀ.

L'ORDINE costituisce il riferimento operativo per la pianificazione delle CONSEGNE e per la gestione delle PRENOTAZIONI.

## Principi Architetturali

- ORDINI rappresenta esclusivamente richieste di prodotto e non vendite.
- Ogni ORDINE possiede un identificativo univoco, permanente e semanticamente neutro.
- Ogni ORDINE appartiene ad un solo CLIENTE.
- Un ORDINE può contenere una o più righe di prodotto.
- Ogni riga di ORDINE fa riferimento ad una sola VARIETÀ.
- L'ORDINE non modifica direttamente lo STOCK.
- L'ORDINE può generare PRENOTAZIONI di STOCK.
- La PRENOTAZIONE appartiene al dominio ORDINI e non costituisce un Register autonomo.
- La PRENOTAZIONE rappresenta esclusivamente una riserva logica della disponibilità e non modifica la quantità fisicamente disponibile nello STOCK.
- Una CONSEGNA può soddisfare l'intero ORDINE oppure una parte dell'ORDINE.
- Uno stesso ORDINE può essere evaso mediante una o più CONSEGNE.
- L'ORDINE è un fatto storico.
- La struttura dell'ORDINE non viene modificata dopo la registrazione.
- Gli errori vengono corretti preservando integralmente la tracciabilità.
- L'ORDINE costituisce il riferimento operativo per la pianificazione delle CONSEGNE e per la gestione delle PRENOTAZIONI.
- La generazione automatica degli ORDINI appartiene esclusivamente al Register PROGRAMMI_FORNITURA e allo Scheduling Engine. ORDINI non gestisce direttamente la ricorrenza.
- Ogni ORDINE generato automaticamente mantiene il riferimento permanente al PROGRAMMA_FORNITURA che lo ha originato.
- Ogni ORDINE dichiara esplicitamente un `OrdineCreationType`: `AUTOMATICO` oppure `MANUALE`.
- Il tipo di creazione non possiede un default, non viene dedotto da altri campi ed è immutabile dopo la registrazione.
- Un ORDINE AUTOMATICO è generato esclusivamente dallo Scheduling Engine, appartiene a una RUN, mantiene il riferimento al PROGRAMMA_FORNITURA, possiede data prevista e chiave idempotente e richiede almeno una provenance per ogni riga.
- Un ORDINE MANUALE è creato fuori dallo Scheduling Engine, non appartiene a una RUN, non riferisce un PROGRAMMA_FORNITURA, non usa la chiave idempotente di scheduling e non possiede provenance; la data prevista è facoltativa.
- Importazione e correzione sono processi e non tipi di ORDINE. Non trasformano un ORDINE AUTOMATICO in MANUALE o viceversa.
- Ogni commit automatico riceve un `CommitExecutionContext` esplicito con
  `ActorId`, reason e correlation ID, senza default o inferenza.
- `ordini.created_by` coincide con l'ActorId del contesto di commit.
- La registrazione produce un evento audit `ORDINE`/`INSERT` per ogni ORDINE,
  nell'ordine del WritePlan; la conclusione RUN auditata è sempre l'ultimo
  evento della stessa transazione.
- Un rollback non lascia eventi audit persistenti. Righe ORDINE e provenance
  non producono eventi autonomi.

## Ciclo di vita

L'ORDINE può assumere un solo stato ufficiale alla volta.

Il ciclo di vita ordinario è:

```text
APERTO
    ↓
PARZIALMENTE EVASO
    ↓
EVASO
```

L'ORDINE può inoltre assumere lo stato:

```text
ANNULLATO
```

Lo stato dell'ORDINE evolve esclusivamente in funzione delle CONSEGNE registrate oppure dell'ANNULLAMENTO.

Lo stato PARZIALMENTE EVASO rappresenta un ORDINE soddisfatto soltanto in parte mediante una CONSEGNA. Lo stato EVASO rappresenta un ORDINE soddisfatto interamente mediante una o più CONSEGNE.

## Relazioni Architetturali

### CLIENTI

Ogni ORDINE appartiene ad un solo CLIENTE.

Il riferimento al CLIENTE non modifica l'identità permanente dell'ORDINE.

### VARIETÀ

Ogni riga di ORDINE fa riferimento ad una sola VARIETÀ.

Un ORDINE può contenere una o più righe di prodotto.

### STOCK

L'ORDINE non modifica direttamente lo STOCK.

La quantità fisicamente disponibile appartiene allo STOCK e non viene modificata dalla richiesta di prodotto o dalla PRENOTAZIONE.

La verifica della disponibilità dello STOCK costituisce esclusivamente un controllo operativo e non modifica l'ORDINE.

### PRENOTAZIONI

L'ORDINE può generare PRENOTAZIONI di STOCK.

La PRENOTAZIONE appartiene al dominio ORDINI e non costituisce un Register autonomo.

La PRENOTAZIONE non costituisce un evento storico autonomo ma una conseguenza logica dell'ORDINE.

La PRENOTAZIONE rappresenta esclusivamente una riserva logica della disponibilità e non modifica la quantità fisicamente disponibile nello STOCK.

### CONSEGNE

Una CONSEGNA può soddisfare l'intero ORDINE oppure una parte dell'ORDINE.

Uno stesso ORDINE può essere evaso mediante una o più CONSEGNE.

L'ORDINE costituisce il riferimento operativo per la pianificazione delle CONSEGNE.

## Dati Minimi Obbligatori

Ogni ORDINE deve poter essere identificato e rappresentato attraverso almeno i seguenti dati:

- identificativo permanente dell'ORDINE;
- riferimento al CLIENTE;
- una o più righe di prodotto;
- riferimento ad una sola VARIETÀ per ciascuna riga;
- data dell'ORDINE;
- stato dell'ORDINE.
- tipo di creazione esplicito dell'ORDINE.

## Tipo di creazione

La matrice ufficiale è:

| Tipo | RUN | PROGRAMMA_FORNITURA | Data prevista | Chiave idempotente | Provenance |
|---|---|---|---|---|---|
| `AUTOMATICO` | obbligatoria | obbligatorio | obbligatoria | obbligatoria | almeno una origine per ogni riga |
| `MANUALE` | assente | assente | facoltativa | assente | vietata |

Il `PostgreSQLCommitRepository` costituisce il writer autorevole degli ORDINI AUTOMATICI prodotti dal percorso Scheduling → WritePlan. Un futuro caso d'uso manuale deve essere separato e non attraversa il WritePlan dello Scheduling.

Nessun valore `IMPORTATO`, `CORRETTIVO`, `LEGACY` o `AMMINISTRATIVO` appartiene a `OrdineCreationType`. Un import deve dichiarare uno dei due tipi ufficiali e soddisfarne integralmente gli invarianti; una correzione preserva il tipo originario e viene auditata.

## Integrità Storica

L'ORDINE rappresenta un fatto storico.

L'identità dell'ORDINE non cambia nel tempo.

La struttura dell'ORDINE non viene modificata dopo la registrazione.

Gli errori vengono corretti preservando integralmente la tracciabilità.

L'evoluzione dello stato, le CONSEGNE che soddisfano l'ORDINE e le PRENOTAZIONI gestite nel dominio ORDINI costituiscono parte della storia dell'ORDINE e non ne alterano l'identità permanente.

## Principi di Evoluzione

Nuove informazioni potranno essere aggiunte esclusivamente se:

- non modificano il significato architetturale dell'ORDINE come richiesta di prodotto;
- non trasformano l'ORDINE in una vendita;
- non consentono modifiche dirette dello STOCK;
- mantengono la PRENOTAZIONE nel dominio ORDINI e distinta dalla disponibilità fisica;
- non alterano la relazione tra ciascuna riga di ORDINE e una sola VARIETÀ;
- non alterano l'immutabilità della struttura dell'ORDINE registrato;
- mantengono la compatibilità con le versioni precedenti;
- rispettano integralmente REGISTER_GOVERNANCE.

ORDINI deve continuare a rappresentare esclusivamente le richieste di prodotto e il riferimento operativo per la pianificazione delle CONSEGNE e la gestione delle PRENOTAZIONI.
