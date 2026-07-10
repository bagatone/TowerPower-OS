# SYSTEM_ARCHITECTURE.md

## Scopo

Questo documento descrive l'architettura logica ufficiale di TowerPower OS.

TowerPower OS deve essere comprensibile e verificabile sia dagli sviluppatori sia dagli agenti AI. Ogni componente deve rispettare le regole operative ufficiali e usare esclusivamente dati registrati nei fogli e nei documenti ufficiali.

## 1. Principio generale

TowerPower OS è organizzato intorno agli eventi operativi, non intorno ai singoli fogli Google Sheets.

L'utente comunica un evento reale, per esempio:

- nuovo cliente;
- nuovo ordine ricorrente;
- modifica ordine;
- cliente sospeso;
- semina;
- passaggio a luce;
- raccolta;
- consegna;
- cambio soluzione;
- acquisto materiale;
- rettifica inventario;
- nuova fotografia associata a un lotto.

Il sistema deve:

1. riconoscere l'evento;
2. estrarre i dati;
3. verificare i dati mancanti;
4. applicare le regole operative;
5. calcolare il calendario;
6. calcolare produzione e risorse;
7. generare un WritePlan;
8. eseguire dry-run;
9. scrivere solo dopo conferma esplicita.

## 2. Architettura dei motori

### Event Engine

L'Event Engine è il punto di ingresso degli eventi operativi.

Responsabilità:

- ricevere eventi da chat, CLI, API o inserimento manuale;
- normalizzare l'evento in un formato logico standard;
- coordinare il flusso tra i motori;
- non scrivere direttamente nei fogli ufficiali.

### Rules Engine

Il Rules Engine applica `OPERATING_RULES.md`.

Responsabilità:

- verificare che l'evento rispetti le regole operative;
- bloccare deduzioni, stime e dati inventati;
- rilevare dati mancanti;
- generare avvisi, priorità e blocchi;
- impedire modifiche parziali incoerenti.

### Calendar Engine

Il Calendar Engine è la fonte temporale unica del sistema.

Responsabilità:

- usare la timezone ufficiale `Atlantic/Canary`;
- determinare automaticamente data, giorno e ora;
- convertire date relative in date assolute;
- calcolare oggi, domani, ritardi e scadenze;
- richiedere conferma in caso di ambiguità temporale.

### Production Planner

Il Production Planner calcola la pianificazione produttiva.

Responsabilità:

- retrocalcolare idratazione, semina, germinazione, luce, raccolta e consegna;
- usare solo dati ufficiali da `MASTER_VARIETA` e fogli collegati;
- generare proposte operative senza scrivere direttamente nei fogli;
- segnalare parametri produttivi mancanti.

### Resource Engine

Il Resource Engine calcola fabbisogni e disponibilità di risorse.

Responsabilità:

- leggere `INVENTARIO`, `RICETTE_PRODUZIONE` e `MOVIMENTI_MAGAZZINO`;
- calcolare risorse richieste dagli eventi produttivi;
- verificare disponibilità, quantità impegnate e quantità disponibili reali;
- non modificare direttamente i fogli.

### Google Sheets Writer

Il Google Sheets Writer è l'unico componente autorizzato a scrivere nei fogli ufficiali.

Responsabilità:

- ricevere WritePlan già validati;
- eseguire dry-run obbligatorio;
- scrivere solo con apply esplicito;
- verificare schema, intestazioni, duplicati e righe invalide;
- applicare aggiornamenti atomici per quanto tecnicamente possibile.

Google Sheets non offre rollback transazionale completo. TowerPower OS riduce il rischio eseguendo tutte le verifiche prima della richiesta di scrittura.

### AGGIORNAMI

`AGGIORNAMI` è la dashboard operativa giornaliera.

Responsabilità:

- mostrare data, ora e timezone;
- evidenziare priorità, consegne, semine, ritardi, manutenzioni e allarmi;
- leggere i dati ufficiali;
- non inventare informazioni mancanti.

### Photo Archivist

Il Photo Archivist gestisce la documentazione fotografica dei lotti.

Responsabilità:

- associare fotografie solo dopo identificazione dell'operatore;
- non dedurre autonomamente lotto, varietà o fase;
- verificare coerenza con il database;
- aggiornare `PHOTO_BANK_INDEX` solo dopo conferma e validazione.

## 3. Flusso dati ufficiale

```text
UTENTE
↓
EVENT ENGINE
↓
RULES ENGINE
↓
CALENDAR ENGINE
↓
PRODUCTION PLANNER
↓
RESOURCE ENGINE
↓
WRITE PLAN
↓
GOOGLE SHEETS WRITER
↓
GOOGLE SHEETS
↓
AGGIORNAMI
```

Nessun modulo, tranne il Google Sheets Writer, può scrivere direttamente nei fogli ufficiali.

## 4. Tempo e calendario

Regole temporali ufficiali:

- timezone ufficiale: `Atlantic/Canary`;
- la data corrente viene ricavata automaticamente dal sistema;
- l'uso interno delle date deve essere in formato ISO `YYYY-MM-DD`;
- l'output leggibile deve includere il giorno della settimana quando utile;
- espressioni come "oggi", "domani", "tra tre giorni" e "venerdì prossimo" devono essere convertite in date assolute;
- in caso di ambiguità, il sistema deve richiedere conferma.

`AGGIORNAMI` deve aprire sempre con:

- data corrente;
- giorno della settimana;
- ora locale;
- timezone;
- attività di oggi;
- attività di domani;
- prossime scadenze;
- attività in ritardo.

## 5. Eventi atomici

### Produzione

- `INIZIO_IDRATAZIONE`
- `SEMINA`
- `PASSAGGIO_GERMINAZIONE`
- `PASSAGGIO_LUCE`
- `RACCOLTA`
- `SCARTO_LOTTO`
- `CHIUSURA_LOTTO`

### Commerciale

- `NUOVO_CLIENTE`
- `CLIENTE_SOSPESO`
- `CLIENTE_RIATTIVATO`
- `NUOVO_ORDINE`
- `MODIFICA_ORDINE`
- `CANCELLAZIONE_ORDINE`
- `CONSEGNA_EFFETTUATA`
- `PAGAMENTO_RICEVUTO`

### Magazzino

- `ACQUISTO_MATERIALE`
- `RICEZIONE_MATERIALE`
- `CONSUMO_MATERIALE`
- `RETTIFICA_INVENTARIO`
- `SCARTO_MATERIALE`

### Impianto

- `CAMBIO_SOLUZIONE`
- `LAVAGGIO_VASCA`
- `MANUTENZIONE`
- `GUASTO`

### Photo Bank

- `FOTO_IDENTIFICATA`
- `FOTO_ASSOCIATA`
- `FOTO_VALIDATA`

### Sistema

- `AGGIORNAMI`
- `CONTROLLO_COERENZA`
- `AUDIT`
- `BACKUP`

## 6. Struttura standard evento

Formato logico:

```json
{
  "event_id": "EVT-IDENTIFICATIVO-UNIVOCO",
  "event_type": "TIPO_EVENTO",
  "timestamp": "YYYY-MM-DDTHH:MM:SS",
  "timezone": "Atlantic/Canary",
  "operatore": "nome",
  "source": "chat|cli|api|manuale",
  "payload": {},
  "status": "BOZZA|VALIDATO|CONFERMATO|PRONTO|APPLICATO|BLOCCATO"
}
```

Regole:

- ogni evento deve ricevere un `event_id` univoco e immutabile;
- `payload` varia per evento;
- solo i campi obbligatori mancanti bloccano il flusso;
- i campi facoltativi possono rimanere vuoti;
- nessun valore può essere inventato;
- `CONFERMATO` indica che l'operatore ha approvato esplicitamente i dati estratti;
- `PRONTO` indica che tutte le verifiche e il dry-run sono stati completati con esito positivo;
- `APPLICATO` indica che il Writer ha completato la scrittura;
- l'evento deve conservare identità, stato e cronologia.

## 7. Esempio ufficiale

Caso d'uso:

> Ristorante Buenaonda vuole una cassa ogni due venerdì: 1 set basilico, 1 set amaranto, 1 set cilantro, 1 set finocchietto. Prima consegna venerdì 15 settembre.

Il sistema deve:

1. riconoscere un nuovo cliente con ordine ricorrente;
2. verificare anno e giorno della settimana;
3. verificare esistenza varietà;
4. verificare parametri produttivi;
5. preparare gli aggiornamenti per `CLIENTI` e `CONSEGNE`;
6. retrocalcolare il calendario;
7. preparare gli aggiornamenti per `PIANO_SEMINE` e `CALENDARIO_PRODUZIONE`;
8. impegnare risorse;
9. segnalare dati mancanti;
10. generare un unico WritePlan;
11. mostrare dry-run prima di apply.

Nessuno dei motori coinvolti scrive direttamente nei fogli. Gli aggiornamenti per `CLIENTI`, `CONSEGNE`, `PIANO_SEMINE` e `CALENDARIO_PRODUZIONE` confluiscono in un unico WritePlan. Il Writer applica il WritePlan solo dopo conferma esplicita e dry-run valido.

Se una varietà, un parametro produttivo, una data o un dato cliente manca dai fogli ufficiali, il sistema deve bloccare il flusso e richiedere completamento.

## 8. Garanzie di sistema

TowerPower OS deve garantire:

- nessuna deduzione;
- nessuna scrittura diretta fuori dal Writer;
- nessuna modifica parziale se genera incoerenze;
- nessuna alterazione dello storico;
- ogni lotto mantiene lo stesso ID;
- ogni movimento di inventario è tracciato;
- ogni data relativa viene convertita in data assoluta;
- ogni errore deve essere leggibile;
- ogni apply deve essere esplicito.

## 9. Roadmap ufficiale

### FASE 1 — FONDAMENTA — COMPLETATA

- repository;
- GitHub;
- SSH;
- Operating Rules;
- schema ufficiale;
- Loader;
- Validator;
- Writer;
- Resource Engine;
- venv;
- test automatici.

### FASE 2 — CORE ENGINE

1. `SYSTEM_ARCHITECTURE.md`
2. `EVENT_ENGINE.md`
3. `CALENDAR_ENGINE.md`
4. Event Engine v1
5. Calendar Engine v1
6. Rules Engine v1
7. Production Planner v2
8. Inventory Manager
9. Auto Update
10. AGGIORNAMI v2

Auto Update è il collegamento controllato tra Event Engine, Rules Engine, Calendar Engine, Production Planner, Resource Engine e Google Sheets Writer. Non costituisce un accesso diretto ai fogli e deve rispettare sempre preflight, dry-run, conferma esplicita e apply.

### FASE 3 — INTELLIGENZA

- agenti specializzati;
- analytics;
- forecast;
- ottimizzazione;
- dashboard;
- interfaccia mobile;
- automazione impianti.
