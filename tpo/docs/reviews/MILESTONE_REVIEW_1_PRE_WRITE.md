# MILESTONE REVIEW 1 — ARCHITECTURE CHECKPOINT PRE-WRITE

**Stato:** APPROVED REVIEW v1.0

## Executive Summary

- Il nuovo TPO Core presenta una base architetturale solida.
- Domain, Application, Infrastructure, Bootstrap e CLI sono correttamente separati.
- Il Core è maturo per simulazione e preflight read-only.
- La scrittura produttiva non è ancora autorizzata.
- È autorizzata esclusivamente una scrittura controllata in ambiente sandbox.

## Decisione finale

GO FOR CONTROLLED WRITE (SANDBOX)

NON ANCORA GO FOR PRODUCTION.

## Condizioni del Controlled Write

- Spreadsheet Google dedicato esclusivamente ai test;
- un solo operatore;
- una sola istanza del sistema;
- esecuzione esclusivamente manuale tramite CLI;
- nessuna automazione pianificata;
- nessun ambiente produttivo;
- nessun accesso concorrente;
- nessun dato operativo reale;
- possibilità di eliminare integralmente il foglio sandbox dopo i test.

## Blocker prima della produzione

1. Policy persistente e concorrente per OrdineId e RunId.
2. Tracciabilità completa e persistente della RUN.
3. Write Plan con prepare, validate, commit e riconciliazione.
4. Protezione dell’idempotenza contro esecuzioni concorrenti.
5. Dismissione o isolamento dei writer legacy.
6. Allineamento formale dell’autorità documentale del Physical Schema.
7. Gestione degli errori di trasporto e degli esiti incerti dell’append.
8. Baseline globale dei test legacy chiaramente governata.

## Findings principali

### P1

- policy identificativi persistenti assente;
- idempotenza concorrente non garantita;
- commit applicativo e riconciliazione assenti;
- tracciabilità RUN incompleta;
- writer legacy ancora operativi.

### P2

- autorità documentale dello schema fisico divergente;
- 55 test legacy falliti;
- gestione errori di rete incompleta;
- isolamento errori per riga assente.

### P3/P4

- ApplicationSettings può essere suddivisa in futuro;
- coverage non ancora misurata;
- ricorrenza mensile nei mesi corti lasciata invariata in attesa di decisione architetturale.

## Stato test al momento della review

- Core: 604 test superati;
- suite completa: 55 falliti, 651 superati;
- working tree pulita;
- nessuna chiamata Google eseguita;
- nessuna credenziale letta;
- nessun file modificato durante la review.

## Roadmap correttiva

### Sprint A — Identity e RUN

- definire policy ID;
- implementare allocazione persistente;
- implementare tracciabilità RUN;
- completare SUCCESS / SUCCESS_WITH_WARNINGS / FAILED;
- isolare gli errori delle singole righe.

### Sprint B — Write Plan e Commit

- piano di scrittura immutabile;
- validazione;
- seconda verifica di schema e chiavi;
- append singola;
- riconciliazione post-append;
- gestione timeout e risposta incerta.

### Sprint C — Concorrenza e Legacy

- serializzazione delle RUN;
- test di doppia esecuzione;
- dismissione writer legacy;
- allineamento Physical Schema;
- baseline test globale;
- write controllato su sandbox.

## Conclusione

Il nuovo TPO Core è approvato per:

- simulazione;
- preflight read-only;
- test locali;
- controlled write esclusivamente su sandbox.

Non è approvato per:

- scrittura su fogli produttivi;
- automazioni;
- esecuzioni concorrenti;
- runtime unattended.
