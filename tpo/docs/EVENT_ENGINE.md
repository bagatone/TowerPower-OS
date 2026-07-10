# EVENT_ENGINE.md

## Event Engine v1

L'Event Engine è il cuore di TowerPower OS.

Questo documento non descrive il codice. Descrive esclusivamente il comportamento operativo del motore.

L'Event Engine riceve un evento TPOL validato e coordina tutti gli altri motori per produrre un unico WritePlan coerente.

## 1. Scopo

L'Event Engine ha una sola responsabilità:

trasformare un evento operativo in un unico WritePlan coerente.

L'Event Engine non scrive mai direttamente nei Google Sheets.

Ogni modifica ai fogli ufficiali deve passare attraverso un WritePlan, un dry-run, una conferma esplicita e il Google Sheets Writer.

## 2. Input

L'input dell'Event Engine è sempre un evento TPOL validato.

Formato logico:

```text
EVENTO
↓
event_id
event_type
payload
timestamp
operatore
source
```

L'Event Engine non interpreta testo libero.

La conversione da linguaggio naturale a evento TPOL avviene prima.

Un evento privo dei campi obbligatori non può entrare nel flusso operativo.

## 3. Output

L'output dell'Event Engine è sempre uno e uno solo:

```text
WritePlan
```

Il WritePlan rappresenta tutte le modifiche necessarie ai fogli ufficiali.

Il WritePlan non modifica direttamente alcun dato.

Il WritePlan deve essere leggibile, verificabile e applicabile solo dopo dry-run valido e conferma esplicita dell'operatore.

## 4. Flusso

Per ogni evento il motore esegue sempre questo ordine:

1. ricezione evento
2. validazione struttura
3. Rules Engine
4. Calendar Engine
5. Production Planner
6. Resource Engine
7. costruzione WritePlan
8. dry-run
9. richiesta conferma
10. Google Sheets Writer
11. apply

L'ordine non può essere modificato.

Ogni passaggio riceve dati dal passaggio precedente e può bloccare il flusso se rileva errori o incoerenze.

## 5. Responsabilità

L'Event Engine deve:

- coordinare i motori
- impedire flussi incompleti
- bloccare eventi non validi
- propagare gli errori
- produrre un solo WritePlan

L'Event Engine non deve:

- scrivere nei fogli
- inventare dati
- ignorare errori
- modificare direttamente lo stato operativo

L'Event Engine non sostituisce i motori specializzati. Coordina il loro lavoro e garantisce che il risultato finale sia unico, coerente e controllabile.

## 6. Eventi supportati v1

Implementazione iniziale:

- SEMINA
- RACCOLTA
- CONSEGNA
- NUOVO_CLIENTE
- NUOVO_ORDINE
- CLIENTE_SOSPESO
- CLIENTE_RIATTIVATO
- ACQUISTO_MATERIALE
- RETTIFICA_INVENTARIO
- CAMBIO_SOLUZIONE

Gli altri eventi potranno essere aggiunti senza modificare l'architettura.

L'elenco v1 rappresenta il perimetro minimo per dimostrare il funzionamento della pipeline operativa.

## 7. Errori

Qualsiasi motore può bloccare il flusso.

Esempi:

- varietà inesistente
- lotto inesistente
- cliente sconosciuto
- dati obbligatori mancanti
- stock insufficiente
- ricetta mancante
- calendario impossibile

In caso di errore:

- nessuna scrittura
- nessun WritePlan applicato
- errore leggibile

L'errore deve indicare cosa blocca il flusso e quale dato deve essere corretto o completato.

## 8. Atomicità

L'Event Engine considera ogni evento una singola operazione logica.

Tutti gli aggiornamenti vengono preparati insieme.

Se un controllo fallisce:

nessun aggiornamento viene applicato.

L'atomicità impedisce aggiornamenti parziali tra fogli ufficiali diversi.

Un evento operativo è considerato completato solo quando tutte le modifiche previste dal WritePlan sono state applicate correttamente dal Writer.

## 9. Esempio

Input:

> Ho seminato 6 set di cilantro.

Flusso:

```text
TPOL
↓
Evento SEMINA
↓
Rules Engine
↓
Calendar Engine
↓
Production Planner
↓
Resource Engine
↓
WritePlan
↓
Dry-run
↓
Conferma operatore
↓
Writer
↓
Google Sheets
```

L'Event Engine coordina il flusso, ma non scrive direttamente sui fogli.

## 10. Versione 1

L'obiettivo della prima implementazione non è supportare tutti gli eventi.

L'obiettivo è dimostrare il funzionamento completo del flusso con il minor numero possibile di eventi.

La prima milestone è considerata completata quando un evento reale attraversa con successo l'intera pipeline fino alla generazione di un WritePlan valido.

La versione 1 deve privilegiare chiarezza, sicurezza dei dati e verificabilità rispetto all'automazione completa.
