# STOCK

**Stato:** ARCHITECTURE FREEZE v1.0

## Scopo

Il Register STOCK rappresenta esclusivamente la disponibilità operativa attuale di prodotto utilizzabile dal sistema Tower Power.

Il Register mantiene separata la disponibilità corrente dalla produzione, dalle RACCOLTE, dagli ORDINI, dalle CONSEGNE e dal magazzino fisico.

## Definizione

Lo STOCK rappresenta esclusivamente il prodotto realmente disponibile per l'utilizzo operativo o commerciale.

Lo STOCK non rappresenta:

- la produzione;
- la raccolta;
- gli ordini;
- le consegne;
- il magazzino fisico;
- il prodotto raccolto;
- il prodotto prenotato;
- il prodotto ordinato.

## Principi Architetturali

- Ogni record di STOCK appartiene ad una sola VARIETÀ.
- Lo STOCK non appartiene ad una SEMINA.
- Una stessa VARIETÀ può essere alimentata da più RACCOLTE.
- Lo STOCK non nasce autonomamente.
- Lo STOCK può aumentare esclusivamente attraverso processi autorizzati che rendono disponibile prodotto fisicamente accertato, inclusi prodotto realmente raccolto o rientro fisico reale esplicitamente registrato.
- La RACCOLTA non modifica automaticamente lo STOCK.
- Lo STOCK può diminuire esclusivamente tramite operazioni autorizzate.
- Le CONSEGNE ordinarie effettive, gli SCARTI, le rettifiche fisiche autorizzate e le future operazioni definite dall'architettura possono diminuire lo STOCK esclusivamente tramite operazioni autorizzate.
- Ogni modifica dello STOCK deve essere tracciabile.
- Le prenotazioni non modificano la disponibilità fisica.
- DISPONIBILE e PRENOTATO rappresentano concetti distinti.

## Natura dello Stato

Lo STOCK rappresenta esclusivamente lo stato corrente del sistema.

Non costituisce un evento storico.

Lo STOCK non registra gli eventi che lo modificano.

Gli eventi che modificano lo STOCK appartengono al Register MOVIMENTI_MAGAZZINO o al Register che ne assumerà formalmente la responsabilità.

Lo storico appartiene a tali eventi e non al Register STOCK, che conserva esclusivamente la fotografia corrente della disponibilità.

## Relazioni Architetturali

### VARIETÀ

```text
VARIETÀ
↓
STOCK
```

### SEMINE

Lo STOCK non appartiene ad una SEMINA.

### RACCOLTE

```text
RACCOLTE
↓
processo autorizzato
↓
STOCK
```

### CONSEGNE, SCARTI E RETTIFICHE FISICHE

```text
CONSEGNE
SCARTI
RETTIFICHE FISICHE ESPLICITE
↓
variazione autorizzata dello STOCK
```

CONSEGNE ordinarie e SCARTI determinano una riduzione. Una rettifica fisica
esplicita applica la direzione del fatto fisico realmente accertato e non quella
della rettifica commerciale eventualmente correlata.

Una rettifica commerciale signed registrata in `tpo.righe_consegna` non è una
rettifica fisica e non modifica automaticamente lo STOCK. Il suo segno non
dimostra restituzione, rientro, nuova uscita o scarto. Se esiste anche una
variazione fisica, questa viene registrata come fatto STOCK esplicito mediante
il vocabolario vigente, senza introdurre automaticamente nuovi movement type.

La CONSEGNA ordinaria effettiva è la sola relazione automatica V1: produce nello
stesso commit il movimento di uscita origine CONSEGNA e la riduzione coerente
dello STOCK. Le CONSEGNE correttive producono per default soltanto effetti
commerciali; un fatto fisico correlato appartiene all'authority STOCK e deve
essere richiesto esplicitamente.

## Dati Minimi Obbligatori

Ogni record di STOCK deve poter rappresentare almeno i seguenti dati:

- riferimento alla VARIETÀ;
- quantità disponibile;
- unità di misura.

Può inoltre essere registrato, come dato opzionale ma raccomandato:

- ultima data/ora di aggiornamento dello stato.

L'ultima data/ora di aggiornamento non rappresenta uno storico, ma esclusivamente il timestamp dell'ultima fotografia dello stato corrente.

## Integrità

Lo STOCK non può assumere valori negativi.

Qualunque operazione che produrrebbe una disponibilità negativa deve essere rifiutata.

Quando:

```text
DISPONIBILE < PRENOTATO
```

deve essere generato automaticamente:

```text
ALLARME ROSSO / PRIORITÀ ASSOLUTA
```

L'ALLARME ROSSO costituisce un controllo di integrità. Non modifica lo STOCK, non corregge automaticamente lo STOCK e segnala esclusivamente una condizione di incoerenza operativa.

## Principi di Evoluzione

Nuove informazioni potranno essere aggiunte esclusivamente se:

- non modificano il significato architetturale dello STOCK;
- non trasformano lo STOCK in un evento storico;
- non introducono responsabilità appartenenti ad altri Register;
- mantengono la distinzione tra DISPONIBILE e PRENOTATO;
- mantengono la compatibilità con le versioni precedenti;
- rispettano integralmente REGISTER_GOVERNANCE.

Le future evoluzioni non devono attribuire allo STOCK responsabilità proprie dei Register:

- CLIENTI;
- ORDINI;
- CONSEGNE;
- MOVIMENTI_MAGAZZINO.

Lo STOCK deve continuare a rappresentare esclusivamente lo stato corrente della disponibilità.
