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
