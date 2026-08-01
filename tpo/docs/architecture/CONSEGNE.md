# CONSEGNE

**Stato:** ARCHITECTURE FREEZE v1.0

## Scopo

Il Register CONSEGNE rappresenta esclusivamente gli eventi logistici di consegna del prodotto ai CLIENTI nel Tower Power Operations.

Il Register mantiene separato l'evento logistico dalla richiesta del CLIENTE, dalla vendita, dall'evento fiscale e dagli eventi che modificano lo STOCK.

## Definizione

Una CONSEGNA rappresenta esclusivamente l'evento logistico reale mediante il quale il prodotto viene consegnato a un CLIENTE.

Ogni CONSEGNA possiede un identificativo univoco, permanente e semanticamente neutro, appartiene ad un solo CLIENTE e contiene una o più righe di prodotto.

Ogni riga della CONSEGNA fa riferimento ad una sola VARIETÀ.

CONSEGNE non rappresenta un ORDINE, una vendita, una FATTURA o un MOVIMENTO_MAGAZZINO.

## Principi Architetturali

- CONSEGNE rappresenta esclusivamente gli eventi logistici di consegna del prodotto ai CLIENTI.
- La CONSEGNA rappresenta il momento in cui il prodotto lascia la responsabilità operativa di Tower Power ed entra nella disponibilità del CLIENTE.
- Ogni CONSEGNA possiede un identificativo univoco, permanente e semanticamente neutro.
- Ogni CONSEGNA appartiene ad un solo CLIENTE.
- Le CONSEGNE ordinarie fanno riferimento a uno o più ORDINI e possono soddisfarli integralmente oppure parzialmente.
- Le CONSEGNE straordinarie, quali omaggi, campioni, sostituzioni e reintegri, possono essere registrate senza un ORDINE, purché la motivazione sia registrata.
- Uno stesso ORDINE può essere soddisfatto da una CONSEGNA o da più CONSEGNE.
- Una CONSEGNA contiene una o più righe di prodotto.
- Una CONSEGNA deve contenere almeno una riga di prodotto.
- Una CONSEGNA ordinaria può contenere esclusivamente prodotti presenti negli ORDINI che essa soddisfa.
- Ogni riga della CONSEGNA fa riferimento ad una sola VARIETÀ.
- La CONSEGNA non modifica direttamente lo STOCK.
- La diminuzione dello STOCK appartiene esclusivamente a MOVIMENTI_MAGAZZINO.
- Una CONSEGNA può originare automaticamente uno o più MOVIMENTI_MAGAZZINO. Un MOVIMENTO_MAGAZZINO non origina una CONSEGNA.
- Una CONSEGNA può essere registrata anche senza FATTURA.
- La FATTURA non appartiene al Register CONSEGNE.
- Ogni CONSEGNA possiede uno stato.
- Gli stati iniziali sono PROGRAMMATA, IN_PREPARAZIONE, CONSEGNATA e ANNULLATA.
- Una CONSEGNA nello stato ANNULLATA non produce MOVIMENTI_MAGAZZINO.
- Ogni CONSEGNA possiede una data prevista e una data effettiva.
- Una CONSEGNA può avere un operatore responsabile.
- Una CONSEGNA può possedere una destinazione fisica diversa dall'indirizzo principale del CLIENTE.
- Una CONSEGNA già CONSEGNATA non può essere modificata.
- Gli errori vengono corretti mediante nuovi documenti, preservando integralmente la tracciabilità.
- Una CONSEGNA può contenere prodotti provenienti da più RACCOLTE.
- La composizione della CONSEGNA è indipendente dalle RACCOLTE.
- Le RACCOLTE rappresentano la provenienza del prodotto. La CONSEGNA rappresenta esclusivamente il prodotto realmente consegnato al CLIENTE.
- La CONSEGNA costituisce il riferimento operativo della futura fatturazione.
- La FATTURA fa riferimento ad una o più CONSEGNE.
- La CONSEGNA non genera direttamente la FATTURA.
- L'ORDINE rappresenta la richiesta del CLIENTE, la CONSEGNA rappresenta l'evento logistico reale e la FATTURA rappresenta l'evento fiscale.
- ORDINE, CONSEGNA e FATTURA sono Register distinti, con responsabilità autonome, collegati mediante riferimenti permanenti e indipendenti tra loro.

## Natura del Register

CONSEGNE registra esclusivamente eventi logistici di consegna.

Non rappresenta:

- un ORDINE;
- una vendita;
- una FATTURA;
- un MOVIMENTO_MAGAZZINO.

Ogni CONSEGNA assume uno dei seguenti stati iniziali:

- PROGRAMMATA;
- IN_PREPARAZIONE;
- CONSEGNATA;
- ANNULLATA.

Una CONSEGNA nello stato CONSEGNATA rappresenta un evento logistico reale e non può essere modificata.

Una CONSEGNA nello stato ANNULLATA non produce MOVIMENTI_MAGAZZINO.

Una CONSEGNA può essere registrata anche senza FATTURA, compresi i casi di:

- omaggio;
- campione;
- sostituzione;
- reintegro.

## Relazioni Architetturali

### CLIENTI

Ogni CONSEGNA appartiene ad un solo CLIENTE.

La destinazione fisica della CONSEGNA può essere diversa dall'indirizzo principale del CLIENTE.

### ORDINI

Le CONSEGNE ordinarie fanno riferimento a uno o più ORDINI e possono soddisfarli integralmente oppure parzialmente.

Le CONSEGNE straordinarie, quali omaggi, campioni, sostituzioni e reintegri, possono essere registrate senza un ORDINE, purché la motivazione sia registrata.

Uno stesso ORDINE può essere soddisfatto da una CONSEGNA o da più CONSEGNE.

Il collegamento tra CONSEGNA e PROGRAMMI_FORNITURA è ricostruibile esclusivamente attraverso gli ORDINI.

CONSEGNE non mantiene una relazione diretta con PROGRAMMI_FORNITURA.

L'ORDINE rappresenta la richiesta del CLIENTE; la CONSEGNA rappresenta l'evento logistico reale.

### VARIETÀ

Ogni riga della CONSEGNA fa riferimento ad una sola VARIETÀ.

Una CONSEGNA contiene una o più righe di prodotto.

### STOCK

La CONSEGNA non modifica direttamente lo STOCK.

La diminuzione dello STOCK appartiene esclusivamente a MOVIMENTI_MAGAZZINO.

### MOVIMENTI_MAGAZZINO

Una CONSEGNA può originare automaticamente uno o più MOVIMENTI_MAGAZZINO.

Un MOVIMENTO_MAGAZZINO non origina una CONSEGNA.

MOVIMENTI_MAGAZZINO rappresenta gli eventi che determinano la variazione dello STOCK e non l'evento logistico di consegna.

### RACCOLTE

Una CONSEGNA può contenere prodotti provenienti da più RACCOLTE.

La composizione della CONSEGNA è indipendente dalle RACCOLTE.

Le RACCOLTE rappresentano la provenienza del prodotto. La CONSEGNA rappresenta esclusivamente il prodotto consegnato al CLIENTE.

### FATTURE

La CONSEGNA costituisce il riferimento operativo della futura fatturazione.

La FATTURA fa riferimento ad una o più CONSEGNE.

La CONSEGNA non genera direttamente la FATTURA e può essere registrata anche senza FATTURA.

La FATTURA rappresenta l'evento fiscale e non appartiene al Register CONSEGNE.

## Dati Minimi Obbligatori

Ogni CONSEGNA deve poter essere identificata e rappresentata attraverso almeno i seguenti dati:

- identificativo permanente della CONSEGNA;
- riferimento al CLIENTE;
- riferimento all'ORDINE o agli ORDINI soddisfatti, per le CONSEGNE ordinarie;
- una o più righe di prodotto;
- riferimento ad una sola VARIETÀ per ciascuna riga;
- stato;
- data prevista;
- data effettiva.

Una CONSEGNA deve contenere almeno una riga di prodotto. Una CONSEGNA ordinaria può contenere esclusivamente prodotti presenti negli ORDINI che essa soddisfa.

Per una CONSEGNA straordinaria registrata senza un ORDINE, la motivazione è obbligatoria.

Possono inoltre essere registrati:

- operatore responsabile;
- destinazione fisica diversa dall'indirizzo principale del CLIENTE.

## Integrità Storica

L'identità della CONSEGNA non cambia nel tempo.

Il CLIENTE associato ad una CONSEGNA non può essere modificato dopo la registrazione dell'evento.

Una CONSEGNA già CONSEGNATA non può essere modificata.

Gli errori vengono corretti mediante nuovi documenti, preservando integralmente la tracciabilità.

I riferimenti permanenti collegano ORDINI, CONSEGNE e FATTURE senza confonderne le rispettive responsabilità.

I MOVIMENTI_MAGAZZINO originati dalla CONSEGNA restano eventi distinti dalla CONSEGNA che li ha originati.

## Principi di Evoluzione

Nuove informazioni potranno essere aggiunte esclusivamente se:

- non modificano il significato architetturale della CONSEGNA come evento logistico reale;
- non trasformano la CONSEGNA in un ORDINE, una vendita, una FATTURA o un MOVIMENTO_MAGAZZINO;
- non consentono alla CONSEGNA di modificare direttamente lo STOCK;
- non invertono la relazione di origine tra CONSEGNA e MOVIMENTI_MAGAZZINO;
- non attribuiscono a RACCOLTE la composizione della CONSEGNA;
- non attribuiscono alla CONSEGNA la generazione diretta della FATTURA;
- non alterano l'immutabilità delle CONSEGNE già CONSEGNATE;
- mantengono la compatibilità con le versioni precedenti;
- rispettano integralmente REGISTER_GOVERNANCE.

CONSEGNE deve continuare a rappresentare esclusivamente gli eventi logistici di consegna del prodotto ai CLIENTI.
