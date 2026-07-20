# TPO DATA DICTIONARY

**Versione:** 1.0  
**Data:** 20/07/2026

---

# SCOPO

Questo documento descrive la struttura completa del database di Tower Power Operations.

Per ogni foglio vengono definite:

- funzione del foglio;
- descrizione di ogni colonna;
- tipo di dato;
- obbligatorietà;
- relazioni con altri fogli;
- regole di compilazione;
- eventuali automazioni.

Questo documento rappresenta il riferimento ufficiale per lo sviluppo del sistema Apps Script.

---

# CONVENZIONI

## Tipi di dato

| Tipo | Significato |
|-------|-------------|
| TEXT | Testo |
| NUMBER | Numero |
| DATE | Data |
| DATETIME | Data e ora |
| BOOLEAN | Vero/Falso |
| ENUM | Valore scelto da elenco |
| ID | Identificatore univoco |
| MONEY | Importo monetario |

---

## Regole generali

- Tutti gli ID sono univoci.
- Gli ID non vengono mai modificati.
- Gli ID non vengono mai riutilizzati.
- Le relazioni avvengono esclusivamente tramite ID.
- Nessun dato viene duplicato se può essere ricavato tramite relazione.
- Ogni modifica ai dati operativi deve essere tracciabile.

---

# FOGLIO: CLIENTI

## Scopo

Contiene l'anagrafica completa dei clienti.

| Campo | Tipo | Obbligatorio | Descrizione |
|--------|------|--------------|-------------|
| ID_CLIENTE | ID | SI | Identificativo univoco del cliente |
| NOME | TEXT | SI | Nome commerciale |
| RAGIONE_SOCIALE | TEXT | NO | Ragione sociale |
| CIF_NIF | TEXT | NO | Codice fiscale / CIF |
| INDIRIZZO | TEXT | NO | Indirizzo |
| CITTÀ | TEXT | NO | Comune |
| TELEFONO | TEXT | NO | Telefono |
| EMAIL | TEXT | NO | Email |
| REFERENTE | TEXT | NO | Persona di riferimento |
| ATTIVO | BOOLEAN | SI | Cliente attivo o meno |
| NOTE | TEXT | NO | Annotazioni |
---

# FOGLIO: ORDINI_RICORRENTI

## Scopo

Definisce gli ordini periodici dei clienti e costituisce la base per la generazione automatica degli ordini futuri.

| Campo | Tipo | Obbligatorio | Descrizione |
|--------|------|--------------|-------------|
| ID_RICORRENZA | ID | SI | Identificativo della ricorrenza |
| ID_CLIENTE | ID | SI | Collegamento al cliente |
| VARIETA | TEXT | SI | Varietà richiesta |
| QUANTITA_SET | NUMBER | SI | Quantità espressa in set |
| FREQUENZA | ENUM | SI | Settimanale, quindicinale, mensile, ecc. |
| GIORNO_CONSEGNA | ENUM | SI | Giorno abituale di consegna |
| DATA_INIZIO | DATE | SI | Inizio della ricorrenza |
| DATA_FINE | DATE | NO | Eventuale termine della ricorrenza |
| ATTIVA | BOOLEAN | SI | Ricorrenza attiva |
| NOTE | TEXT | NO | Annotazioni |

---

# FOGLIO: ORDINI

## Scopo

Contiene tutti gli ordini ricevuti, sia generati automaticamente dalle ricorrenze sia inseriti manualmente.

| Campo | Tipo | Obbligatorio | Descrizione |
|--------|------|--------------|-------------|
| ID_ORDINE | ID | SI | Identificativo ordine |
| ID_CLIENTE | ID | SI | Cliente che effettua l'ordine |
| DATA_ORDINE | DATE | SI | Data ricezione ordine |
| DATA_CONSEGNA | DATE | SI | Data prevista di consegna |
| STATO_ORDINE | ENUM | SI | Pianificato, Produzione, Consegnato, Annullato |
| NOTE | TEXT | NO | Annotazioni |

---

# FOGLIO: PIANO_SEMINE

## Scopo

Raccoglie la pianificazione delle semine necessarie per soddisfare gli ordini.

| Campo | Tipo | Obbligatorio | Descrizione |
|--------|------|--------------|-------------|
| ID_PIANO | ID | SI | Identificativo del piano |
| DATA_CREAZIONE | DATE | SI | Data generazione piano |
| VARIETA | TEXT | SI | Varietà da seminare |
| SET_DA_PRODURRE | NUMBER | SI | Quantità prevista |
| DATA_SEMINA | DATE | SI | Data prevista della semina |
| PRIORITA | ENUM | SI | Bassa, Media, Alta, Urgente |
| STATO | ENUM | SI | Da eseguire, In corso, Completato |
| NOTE | TEXT | NO | Annotazioni |

---

# FOGLIO: SEMINE

## Scopo

Registra ogni operazione reale di semina eseguita.

| Campo | Tipo | Obbligatorio | Descrizione |
|--------|------|--------------|-------------|
| ID_SEMINA | ID | SI | Identificativo della semina |
| ID_PIANO | ID | SI | Collegamento al piano semine |
| DATA_SEMINA | DATE | SI | Data effettiva della semina |
| VARIETA | TEXT | SI | Varietà seminata |
| SET_SEMINATI | NUMBER | SI | Numero di set seminati |
| OPERATORE | TEXT | NO | Operatore responsabile |
| NOTE | TEXT | NO | Annotazioni |
---

# FOGLIO: LOTTI

## Scopo

Ogni semina genera uno o più lotti. Il lotto rappresenta l'unità produttiva che verrà seguita fino alla raccolta.

| Campo | Tipo | Obbligatorio | Descrizione |
|--------|------|--------------|-------------|
| ID_LOTTO | ID | SI | Identificativo univoco del lotto |
| ID_SEMINA | ID | SI | Collegamento alla semina di origine |
| VARIETA | TEXT | SI | Varietà coltivata |
| DATA_SEMINA | DATE | SI | Data della semina |
| DATA_PREVISTA_RACCOLTA | DATE | SI | Data prevista di raccolta |
| STATO | ENUM | SI | Germinazione, Luce, Pronto, Raccolto, Scartato |
| OPERATORE | TEXT | NO | Operatore responsabile |
| NOTE | TEXT | NO | Annotazioni |

---

# FOGLIO: RACCOLTI

## Scopo

Registra tutte le operazioni di raccolta effettuate sui lotti.

| Campo | Tipo | Obbligatorio | Descrizione |
|--------|------|--------------|-------------|
| ID_RACCOLTA | ID | SI | Identificativo della raccolta |
| ID_LOTTO | ID | SI | Lotto di provenienza |
| DATA_RACCOLTA | DATE | SI | Data della raccolta |
| SET_RACCOLTI | NUMBER | SI | Numero di set raccolti |
| QUALITA | ENUM | SI | Ottima, Buona, Sufficiente, Scarto |
| DESTINAZIONE | ENUM | SI | Stock, Cliente, Test, Scarto |
| OPERATORE | TEXT | NO | Operatore che ha effettuato la raccolta |
| NOTE | TEXT | NO | Annotazioni |

---

# FOGLIO: ASSEGNAZIONI

## Scopo

Associa ogni raccolta agli ordini dei clienti.

Una raccolta può essere suddivisa tra più ordini e una consegna può contenere più assegnazioni.

| Campo | Tipo | Obbligatorio | Descrizione |
|--------|------|--------------|-------------|
| ID_ASSEGNAZIONE | ID | SI | Identificativo assegnazione |
| ID_RACCOLTA | ID | SI | Raccolta di origine |
| ID_ORDINE | ID | SI | Ordine cliente |
| ID_CONSEGNA | ID | NO | Collegamento alla consegna |
| VARIETA | TEXT | SI | Varietà assegnata |
| SET_ASSEGNATI | NUMBER | SI | Quantità assegnata |
| DATA_ASSEGNAZIONE | DATE | SI | Data assegnazione |
| NOTE | TEXT | NO | Annotazioni |

---

### Relazioni

SEMINE → LOTTI → RACCOLTI → ASSEGNAZIONI

Questa è la catena principale di tracciabilità produttiva del sistema Tower Power Operations.s