# RACCOLTE

**Stato:** ARCHITECTURE FREEZE v1.0

## Scopo

Il Register RACCOLTE definisce gli eventi di raccolta realmente eseguiti nel Tower Power Operations e garantisce la tracciabilità del prodotto ottenuto a partire da una specifica SEMINA.

Il Register registra esclusivamente gli eventi produttivi di raccolta e mantiene separata l'identità della RACCOLTA dalla SEMINA, dallo STOCK, dalle CONSEGNE e dagli altri Register specialistici.

## Definizione

Una RACCOLTA rappresenta un evento produttivo che registra il prelievo definitivo di una quantità di prodotto proveniente da una sola SEMINA.

La RACCOLTA costituisce un fatto storico immutabile e documenta esclusivamente il prodotto effettivamente ottenuto durante una specifica operazione di raccolta.

Ogni RACCOLTA appartiene ad una sola SEMINA.

Una SEMINA può generare zero, una o molte RACCOLTE.

Una RACCOLTA non appartiene mai contemporaneamente a più SEMINE.

## Principi Architetturali

- La RACCOLTA è un evento produttivo e non rappresenta uno stato del ciclo di produzione.
- La RACCOLTA possiede un identificativo univoco, permanente e semanticamente neutro.
- Ogni RACCOLTA appartiene esclusivamente ad una sola SEMINA.
- Una SEMINA può produrre più RACCOLTE nel corso del proprio ciclo di vita.
- La RACCOLTA non modifica l'identità della SEMINA.
- La RACCOLTA registra esclusivamente il prodotto effettivamente raccolto.
- L'unità quantitativa principale della RACCOLTA è il SET raccolto.
- Eventuali misure aggiuntive, come il peso reale, costituiscono informazioni complementari e non modificano il significato architetturale del Register.
- Gli SCARTI non appartengono al Register RACCOLTE.
- La RACCOLTA non genera automaticamente disponibilità nello STOCK.
- La RACCOLTA non determina automaticamente una CONSEGNA.
- La RACCOLTA non incorpora informazioni commerciali definitive.
- Il cliente non costituisce parte dell'identità della RACCOLTA.
- Può essere registrata una DESTINAZIONE PREVISTA o ALLOCAZIONE INIZIALE esclusivamente come informazione operativa.
- La RACCOLTA è immutabile dopo la registrazione dell'evento fisico.
- Gli errori vengono corretti preservando integralmente la tracciabilità storica.

## Natura dell'evento

La RACCOLTA è un evento puntuale.

Non possiede un proprio ciclo di vita.

Non esistono stati quali:

- APERTA;
- IN CORSO;
- CHIUSA.

L'evento si considera concluso nel momento in cui il prelievo è terminato e la quantità raccolta è stata registrata.

La RACCOLTA non può essere annullata dopo il verificarsi dell'evento reale.

Una registrazione completamente errata può essere eliminata esclusivamente quando l'evento fisico non è mai avvenuto.

## Relazioni Architetturali

### SEMINE

Ogni RACCOLTA appartiene ad una sola SEMINA.

La RACCOLTA mantiene il collegamento permanente con la SEMINA di origine senza modificarne identità, stato o caratteristiche.

### STOCK

La RACCOLTA non determina automaticamente la disponibilità nello STOCK.

Lo STOCK registra esclusivamente il prodotto effettivamente disponibile per l'utilizzo operativo o commerciale.

La disponibilità del prodotto appartiene al Register STOCK e non al Register RACCOLTE.

### CONSEGNE

Una CONSEGNA può aggregare prodotto proveniente da una o più RACCOLTE.

L'aggregazione commerciale non modifica le RACCOLTE che ne costituiscono l'origine.

La RACCOLTA non conosce la composizione finale della CONSEGNA.

L'aggregazione commerciale appartiene esclusivamente al Register CONSEGNE.

### SCARTI

Gli SCARTI non appartengono al Register RACCOLTE.

Le perdite produttive vengono registrate nel Register specialistico dedicato e non modificano la RACCOLTA.

## Dati Minimi Obbligatori

Ogni RACCOLTA deve poter essere identificata attraverso almeno i seguenti dati:

- identificativo permanente della RACCOLTA;
- riferimento alla SEMINA;
- data della raccolta;
- quantità raccolta;
- unità di misura;
- operatore, facoltativo;
- DESTINAZIONE PREVISTA o ALLOCAZIONE INIZIALE, facoltativa;
- note, facoltative.

## Integrità Storica

La RACCOLTA rappresenta un evento realmente avvenuto.

L'identità della RACCOLTA non cambia nel tempo.

La RACCOLTA non viene modificata dopo la registrazione dell'evento.

Eventuali correzioni devono preservare integralmente la tracciabilità storica.

L'eliminazione è consentita esclusivamente nel caso di una registrazione completamente errata quando l'evento fisico non è mai avvenuto.

## Principi di Evoluzione

Nuove informazioni potranno essere aggiunte esclusivamente se:

- non modificano il significato architetturale della RACCOLTA;
- non alterano la relazione con SEMINE;
- non introducono responsabilità appartenenti ad altri Register;
- mantengono la compatibilità con le versioni precedenti;
- rispettano integralmente REGISTER_GOVERNANCE.
