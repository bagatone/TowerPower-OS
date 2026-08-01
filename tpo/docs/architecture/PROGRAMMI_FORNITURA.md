# PROGRAMMI_FORNITURA

**Stato:** ARCHITECTURE FREEZE v1.0

## Scopo

Il Register PROGRAMMI_FORNITURA rappresenta il Master Register della pianificazione operativa del Tower Power Operations.

Il Register definisce esclusivamente gli accordi operativi continuativi tra Tower Power e i CLIENTI e mantiene tali accordi separati da ORDINI, CONSEGNE, PRENOTAZIONI e pianificazione produttiva.

## Definizione

Un PROGRAMMA_FORNITURA rappresenta esclusivamente un accordo operativo continuativo tra Tower Power e un CLIENTE.

Ogni PROGRAMMA_FORNITURA possiede un identificativo univoco, permanente e semanticamente neutro, appartiene ad un solo CLIENTE e contiene una o più righe di prodotto.

Ogni riga fa riferimento ad una sola VARIETÀ e possiede una configurazione temporale indipendente. Righe differenti dello stesso PROGRAMMA_FORNITURA possono avere frequenze differenti.

PROGRAMMI_FORNITURA non rappresenta un ORDINE, una CONSEGNA, una PRENOTAZIONE o una pianificazione produttiva.

## Principi Architetturali

- PROGRAMMI_FORNITURA è il Master Register della pianificazione operativa.
- Ogni PROGRAMMA_FORNITURA possiede un identificativo univoco, permanente e semanticamente neutro.
- Ogni PROGRAMMA_FORNITURA appartiene ad un solo CLIENTE.
- Ogni CLIENTE possiede un solo PROGRAMMA_FORNITURA attivo.
- Possono esistere uno o più PROGRAMMI_FORNITURA TERMINATI appartenenti allo stesso CLIENTE, preservando integralmente lo storico dei rapporti commerciali.
- Un PROGRAMMA_FORNITURA TERMINATO non viene riattivato né riutilizzato.
- La definizione di un nuovo accordo operativo genera sempre un nuovo PROGRAMMA_FORNITURA con un nuovo identificativo permanente.
- Un PROGRAMMA_FORNITURA contiene una o più righe di prodotto.
- Ogni riga fa riferimento ad una sola VARIETÀ.
- Ogni riga possiede una configurazione temporale indipendente.
- Righe differenti possono avere frequenze differenti all'interno dello stesso PROGRAMMA_FORNITURA.
- Ogni PROGRAMMA_FORNITURA possiede una data di inizio e può possedere una data di fine.
- Ogni PROGRAMMA_FORNITURA possiede uno stato.
- Gli stati iniziali sono ATTIVO, SOSPESO e TERMINATO.
- Ogni PROGRAMMA_FORNITURA possiede un orario di generazione.
- Il valore predefinito di sistema dell'orario di generazione è 05:00 e può essere modificato per il singolo PROGRAMMA_FORNITURA.
- Ogni PROGRAMMA_FORNITURA possiede una finestra operativa che determina l'anticipo con cui devono essere generati gli ORDINI rispetto alla data prevista della CONSEGNA.
- PROGRAMMI_FORNITURA non genera direttamente ORDINI.
- La generazione degli ORDINI appartiene esclusivamente allo Scheduling Engine.
- Ogni ORDINE generato mantiene il riferimento permanente al PROGRAMMA_FORNITURA che lo ha originato.
- Le modifiche a un PROGRAMMA_FORNITURA influenzano esclusivamente gli ORDINI futuri.
- Gli ORDINI già generati rimangono immutabili.
- PROGRAMMI_FORNITURA non conosce direttamente STOCK, RACCOLTE, SEMINE, CONSEGNE o FATTURE.
- Lo Scheduling Engine legge PROGRAMMI_FORNITURA e genera automaticamente gli ORDINI quando il calendario lo richiede.
- Il Planning Engine utilizza gli ORDINI generati per costruire automaticamente il PIANO_SEMINE, il fabbisogno produttivo, il forecast e il briefing giornaliero.
- La costruzione del PIANO_SEMINE, del fabbisogno produttivo, del forecast e del briefing giornaliero non appartiene al Register PROGRAMMI_FORNITURA.
- Tutti gli Engine di pianificazione leggono PROGRAMMI_FORNITURA e non lo modificano.
- I Register conservano la verità del dominio. Gli Engine eseguono logica utilizzando esclusivamente i Register.

## Natura del Register

PROGRAMMI_FORNITURA è il Master Register della pianificazione operativa.

Rappresenta esclusivamente l'accordo operativo continuativo tra Tower Power e un CLIENTE.

Non rappresenta:

- un ORDINE;
- una CONSEGNA;
- una PRENOTAZIONE;
- una pianificazione produttiva.

Ogni PROGRAMMA_FORNITURA assume uno dei seguenti stati iniziali:

- ATTIVO;
- SOSPESO;
- TERMINATO.

Ogni CLIENTE possiede un solo PROGRAMMA_FORNITURA nello stato ATTIVO.

Possono esistere uno o più PROGRAMMI_FORNITURA nello stato TERMINATO appartenenti allo stesso CLIENTE, allo scopo di preservare integralmente lo storico dei rapporti commerciali.

Un PROGRAMMA_FORNITURA TERMINATO non viene riattivato né riutilizzato. La definizione di un nuovo accordo operativo genera sempre un nuovo PROGRAMMA_FORNITURA con un nuovo identificativo permanente.

Ogni riga del PROGRAMMA_FORNITURA possiede una configurazione temporale indipendente, che può essere:

- settimanale;
- ogni 15 giorni;
- mensile;
- ogni X giorni;
- relativa a giorni specifici della settimana.

## Relazioni Architetturali

### CLIENTI

Ogni PROGRAMMA_FORNITURA appartiene ad un solo CLIENTE.

Il PROGRAMMA_FORNITURA rappresenta il rapporto operativo continuativo tra Tower Power e il CLIENTE.

Ogni CLIENTE possiede un solo PROGRAMMA_FORNITURA attivo.

Possono esistere uno o più PROGRAMMI_FORNITURA TERMINATI appartenenti allo stesso CLIENTE, preservando integralmente lo storico dei rapporti commerciali.

### VARIETÀ

Ogni riga del PROGRAMMA_FORNITURA fa riferimento ad una sola VARIETÀ.

Righe differenti possono riferirsi a VARIETÀ differenti e possedere configurazioni temporali differenti all'interno dello stesso PROGRAMMA_FORNITURA.

### ORDINI

PROGRAMMI_FORNITURA non genera direttamente ORDINI.

Ogni ORDINE generato mantiene il riferimento permanente al PROGRAMMA_FORNITURA che lo ha originato.

Le modifiche a un PROGRAMMA_FORNITURA influenzano esclusivamente gli ORDINI futuri. Gli ORDINI già generati rimangono immutabili.

### Scheduling Engine

Lo Scheduling Engine legge PROGRAMMI_FORNITURA e genera automaticamente gli ORDINI quando il calendario lo richiede.

La generazione degli ORDINI appartiene esclusivamente allo Scheduling Engine e non al Register PROGRAMMI_FORNITURA.

### Planning Engine

Il Planning Engine utilizza gli ORDINI generati per costruire automaticamente:

- PIANO_SEMINE;
- fabbisogno produttivo;
- forecast;
- briefing giornaliero.

Queste responsabilità non appartengono al Register PROGRAMMI_FORNITURA.

### STOCK, RACCOLTE, SEMINE, CONSEGNE e FATTURE

PROGRAMMI_FORNITURA non conosce direttamente:

- STOCK;
- RACCOLTE;
- SEMINE;
- CONSEGNE;
- FATTURE.

## Dati Minimi Obbligatori

Ogni PROGRAMMA_FORNITURA deve poter essere identificato e rappresentato attraverso almeno i seguenti dati:

- identificativo permanente del PROGRAMMA_FORNITURA;
- riferimento al CLIENTE;
- una o più righe di prodotto;
- riferimento ad una sola VARIETÀ per ciascuna riga;
- configurazione temporale indipendente per ciascuna riga;
- data di inizio;
- data di fine, facoltativa;
- stato;
- orario di generazione;
- finestra operativa.

L'orario di generazione assume il valore predefinito di sistema 05:00, salvo modifica per il singolo PROGRAMMA_FORNITURA.

La finestra operativa determina l'anticipo con cui devono essere generati gli ORDINI rispetto alla data prevista della CONSEGNA.

## Integrità Storica

L'identità del PROGRAMMA_FORNITURA non cambia nel tempo.

Ogni ORDINE generato conserva permanentemente il riferimento al PROGRAMMA_FORNITURA che lo ha originato.

Gli ORDINI storici continuano a mantenere il riferimento al PROGRAMMA_FORNITURA originario che li ha generati.

Un PROGRAMMA_FORNITURA TERMINATO non viene riattivato né riutilizzato.

Un PROGRAMMA_FORNITURA TERMINATO continua a costituire parte dello storico dei rapporti commerciali tra Tower Power e il CLIENTE e non viene riutilizzato per nuovi accordi operativi.

La definizione di un nuovo accordo operativo genera sempre un nuovo PROGRAMMA_FORNITURA con un nuovo identificativo permanente.

Le modifiche a un PROGRAMMA_FORNITURA producono effetti esclusivamente sugli ORDINI futuri e non modificano gli ORDINI già generati.

Gli ORDINI già generati rimangono immutabili.

## Principi di Evoluzione

Nuove informazioni potranno essere aggiunte esclusivamente se:

- non modificano il significato architetturale del PROGRAMMA_FORNITURA come accordo operativo continuativo;
- non trasformano PROGRAMMI_FORNITURA in ORDINI, CONSEGNE, PRENOTAZIONI o pianificazione produttiva;
- non attribuiscono al Register la generazione diretta degli ORDINI;
- non introducono conoscenza diretta di STOCK, RACCOLTE, SEMINE, CONSEGNE o FATTURE;
- non consentono agli Engine di modificare PROGRAMMI_FORNITURA;
- non modificano retroattivamente gli ORDINI già generati;
- mantengono la compatibilità con le versioni precedenti;
- rispettano integralmente REGISTER_GOVERNANCE.

PROGRAMMI_FORNITURA deve continuare a costituire il Master Register della pianificazione operativa. I Register conservano la verità del dominio e gli Engine eseguono logica utilizzando esclusivamente i Register.
