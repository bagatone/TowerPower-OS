# OPERATIONAL WEB ADAPTER — GOVERNANCE FREEZE V1 (Fase 0)

**Stato:** OWNER-APPROVED ARCHITECTURE FREEZE (approvato 2026-09-09).
Owner Decision D1-D5 approvate al §4.
**Ambito:** Fase 0 di `docs/reviews/GESTIONALE_TPO_ROADMAP.md` §5 — apre
il boundary di governance per il nuovo adapter di lettura/scrittura web
`OPERATIONAL_WEB_ADAPTER`, come previsto e non ancora avviato dalla
roadmap stessa (§21.3: "resta esplicitamente rimandata a un round
dedicato successivo").
**Baseline:** stato del repository verificato per lettura diretta il
2026-09-09 (il bridge remoto non ha accesso alla root Git, che è la
cartella padre di `tpo`: l'hash di commit esatto non è verificabile da
qui e non viene inventato — Giulia può riportarlo con `git log -1`).

## 1. Scopo

Introdurre un'applicazione web locale che permetta a Giulia (e in futuro
al team) di consultare e — a partire dalla Fase 2 — registrare dati
operativi reali di TPO, sostituendo l'attuale dashboard Artifact (dati di
esempio) con la stessa interfaccia collegata al database Postgres/Supabase
reale già in uso. Non introduce un secondo Writer, non duplica la logica
applicativa già scritta e testata in `src/tpo_core`, e non espone nulla
su internet.

Questo documento risolve i cinque punti che la roadmap (§5, Fase 0) elenca
come necessari prima di scrivere codice: perimetro lettura/scrittura,
identità di chi scrive, mappatura esiti/errori, dove gira il servizio e
chi vi accede, standard di verifica.

## 2. Prior-art gate

Ricerca repository-wide su web/UI/dashboard/adapter/API, come richiesto da
`ARCHITECTURE_AUTHORITY_GOVERNANCE_FREEZE.md` §5.

| Fonte | Contenuto | Classificazione |
|---|---|---|
| `docs/reviews/GESTIONALE_TPO_ROADMAP.md` | Descrive esattamente questo boundary (nome di lavoro `OPERATIONAL_WEB_ADAPTER`, Fasi 0-5, vincolo di rete locale, login in Fase 3), e nomina la dashboard Artifact come "prima anteprima visiva" che ha già validato un linguaggio grafico. | **PRESERVED — è il mandato diretto di questo documento.** Nessuna decisione di quella roadmap viene riaperta qui. |
| Dashboard Artifact (`semina-control.html`, sessione Claude separata) | Interfaccia già in uso quotidiano da Giulia, con dati di esempio/manuali propri (non collegati a Postgres), linguaggio grafico già validato. | **PRESERVED come riferimento di UX**, non come fonte dati: Fase 1 la sostituisce con dati veri, non ne eredita il database (quello Artifact è un capability separato, non Postgres). |
| `docs/AGENTS.md`, sezioni Website Manager / Daily Briefing Agent / Farm Manager Agent | Organigramma di ruoli e disciplina comportamentale ("mai inventare", `DA CONFERMARE`, conferma esplicita prima di scrivere) per un'epoca a Google Sheets. | **PARTIALLY MIGRATED** — la disciplina comportamentale è preservata e riusata (§6); la meccanica a fogli Google è superata e non viene riportata: Fase 1/2 leggono/scrivono solo tramite `tpo_core`. |
| `docs/reviews/PROJECT_ARCHITECTURE_REVIEW_2026.md` §11, §18, §19 | Al 08/08 la CLI esponeva solo simulazione/preflight; "UI" maturità 0; nessun read model PG. | **MISSING FROM CORE, in parte colmato da allora** — verificato oggi (§3.1): esiste un solo servizio di lettura reale (`disponibilita_commerciale`); tutto il resto della CLI è comandi di scrittura. Confermato ancora vero per la parte "nessun read model generale". |
| `docs/architecture/AUTHORITY_REGISTRY.yaml` | Nessun `concept_id` per `OPERATIONAL_WEB_ADAPTER`, UI, API o agente conversazionale. | **CONFERMA IL GATE** — nessun predecessore da riconciliare; è dominio nuovo, non un duplicato. |
| `ARCHITECTURE_AUTHORITY_GOVERNANCE_FREEZE.md` §2.1 | "PostgreSQL Core è l'unica autorità runtime operativa attuale... nessun runtime può fare fallback o dual-write silenzioso" verso Google. | **PRESERVED, vincolante** — l'adapter web legge/scrive solo tramite `tpo_core` (Application layer), mai un secondo percorso verso Postgres o verso Google Sheets. |
| `src/tpo_core/cli/*.py`, `src/tpo_core/application/*` (verificato oggi, elenco completo in §3.1) | 14 gruppi di comandi CLI, tutti di scrittura (commissioning/registrazione), tranne `schedule preflight`/`schedule run --simulate`; un solo servizio applicativo di sola lettura (`disponibilita_commerciale`). | **VERIFICATO — stato reale, non presunto.** Base per il perimetro Fase 1 proposto al §5. |
| Autenticazione/autorizzazione a grana fine | Nessun sistema di ruoli/permessi esiste oggi in nessun punto del repository (confermato anche da `LISTINO_VARIETA_GOVERNANCE_FREEZE.md` §2, stessa lacuna). | **MISSING FROM CORE, esplicitamente in scope qui** — a differenza del freeze LISTINO_VARIETA che la rimandava, questo documento la deve affrontare (è la Fase 3 della roadmap stessa, ma il *contratto* minimo di identità va deciso da subito per Fase 2, §4.2). |

**Esito:** `PRIOR ART REVIEW PASSED`. Nessun predecessore non classificato,
nessuna duplicazione, nessun conflitto sul boundary stesso. Restano cinque
decisioni owner aperte (§4), come già anticipato dalla roadmap.

## 3. Stato reale verificato (non presunto)

### 3.1 Superficie CLI/Application attuale

Comandi disponibili oggi (`src/tpo_core/cli/main.py`), tutti scrittura
salvo dove indicato:

```text
schedule run --simulate     (lettura, simulazione Google)
schedule preflight          (lettura, verifica Google read-only guarded)
schedule execute            (scrittura — il comando delle 06:00)
production-planning ...     (scrittura — genera PIANO_SEMINE)
onboarding customer/variety/supply-program/...
semente commission
semente-impiego commission
seed-lot commission
semina commission/transition
delivery fulfil
fattura emetti/rettifica
listino-varieta set
cliente fatturazione
raccolta record/correggi
movimento carica-raccolta / movimento-articolo ...
articolo commissiona
assegnazione registra
incasso registra/correggi
uscita registra/correggi
```

**Nessun comando di lettura/elenco esiste per nessuno di questi domini**
(nessun "list", "get", "show"). L'unico servizio applicativo di sola
lettura oggi è `disponibilita_commerciale` (PRENOTATO/VENDIBILE),
`src/tpo_core/application/disponibilita_commerciale/` — pensato come
query pura fin dall'origine (`STOCK_DISPONIBILITA_COMMERCIALE_FREEZE.md`).

**Conseguenza diretta per la Fase 1**: non si tratta di "esporre sul web
letture che la CLI già fa" — vanno *costruiti* nuovi servizi applicativi
di sola lettura, uno per boundary, sullo stesso modello già collaudato da
`disponibilita_commerciale` (query pura, nessun writer, nessuna nuova
regola di dominio). È lavoro nuovo, non un semplice collegamento.

### 3.2 Tabelle Postgres esistenti (verificate nelle migrazioni)

`clienti`, `varieta`, `cultivar`, `cultivar_usi`, `listino_varieta`,
`sementi`, `semente_impieghi`, `lotti_seme`, `semine`,
`semina_lifecycle_eventi`, `raccolte`, `stock`, `stock_articoli`,
`articoli`, `movimenti_magazzino`, `programmi_fornitura`,
`programmi_fornitura_versioni`, `righe_programma_fornitura`, `ordini`,
`righe_ordine`, `consegne`, `righe_consegna`, `consegne_ordini`,
`assegnazioni_fisiche`, `fatture`, `righe_fattura`, `fatture_consegne`,
`incassi`, `uscite`, `runs`, `run_log`, `run_messaggi`, `audit_eventi`,
oltre alle tabelle di richiesta/idempotenza e planning interne. Questo è
l'inventario reale su cui i nuovi servizi di lettura leggeranno.

## 4. Owner Decision — approvate 2026-09-09

Questi sono i cinque punti che la roadmap stessa (§5, Fase 0) richiede di
risolvere. Tutte e cinque approvate da Giulia il 2026-09-09.

### D1 — Perimetro e ordine della Fase 1 (sola lettura): APPROVATA, tutto insieme

**Decisione owner: costruire tutti i nove boundary di lettura insieme,
non in ordine sequenziale a rilascio incrementale.** Restano comunque un
elenco esplicito (serve per governance e per i test, boundary per
boundary), e l'ordine di implementazione tecnica dentro questo lavoro
resta quello che segue — non perché sia un rilascio a tappe verso
Giulia, ma perché è l'ordine di dipendenza più sicuro (partire da ciò
che esiste già, poi le aree con meno dipendenze incrociate):

1. `disponibilita_commerciale` — già esiste, solo da collegare (rischio
   zero, nessun nuovo servizio da scrivere).
2. CLIENTI (anagrafica + stato relazione).
3. VARIETA / LISTINO_VARIETA (prezzi correnti).
4. SEMENTE / SEMENTE_IMPIEGO / LOTTO_SEME.
5. SEMINA (stato lifecycle) + RACCOLTA.
6. STOCK / MOVIMENTO_MAGAZZINO / ARTICOLO.
7. PROGRAMMI_FORNITURA / ORDINI / CONSEGNA / ASSEGNAZIONE_FISICA.
8. FATTURA / INCASSO / USCITA.
9. `runs`/`run_log` — vista sullo stato delle esecuzioni schedulate delle
   06:00 (utile per verificare se un'esecuzione è avvenuta, senza dover
   controllare da terminale).

Tutti e nove entrano in questo stesso giro di lavoro; nessuno slitta a un
round successivo salvo problemi tecnici imprevisti che verranno segnalati
singolarmente, mai passati sotto silenzio.

### D2 — Identità di chi scrive (rilevante da subito per la Fase 2): APPROVATA

Ogni comando `tpo_core` oggi richiede un `ActorId` esplicito e non vuoto
(nessuna scrittura anonima, stesso principio di `AGENTS.md`). Un vero
login (Fase 3 della roadmap) arriva dopo. **Proposta per la Fase 2**: un
identificativo utente fisso e configurato lato server (es.
`giulia@towerpower`), mai una stringa libera immessa dall'interfaccia —
così ogni scrittura resta tracciabile e conforme, anche prima che esista
un vero sistema di account.

**Decisione owner: APPROVATA come proposta.** Identificativo fisso lato
server per la Fase 2; login vero rimandato alla Fase 3.

### D3 — Mappatura esiti/errori verso l'interfaccia web: APPROVATA

`tpo_core` restituisce già codici di esito tipizzati (`OperationalExitCode`:
`OPERATION_COMMITTED`, `OPERATION_FAILED`, `OPERATION_INPUT_INVALID`,
`OPERATION_RECONCILIATION_REQUIRED`, ecc.) e messaggi come
`RACCOLTA_FAILED: <code>: <messaggio>`. **Proposta**: il servizio web
traduce questi codici in messaggi comprensibili per l'interfaccia, senza
inventare nuove categorie di errore né nuove regole di validazione — se
un'operazione fallisce, l'interfaccia mostra il motivo che l'Application
ha già prodotto, non una propria interpretazione.

**Decisione owner: APPROVATA come proposta.** Nessuna nuova logica di
validazione lato web.

### D4 — Dove gira il servizio e chi vi accede: APPROVATA

Coerente con la roadmap (§3-4): nessuna esposizione su internet in questa
fase. **Proposta**: un servizio che gira sul tuo Mac (o su una macchina
della rete locale della farm), raggiungibile solo da dispositivi sulla
stessa rete Wi-Fi/LAN — non dal dominio pubblico towerpower.green, che
resta un progetto separato (Fase 5, esplicitamente fuori scope).

**Decisione owner: APPROVATA come proposta.** Solo rete locale in questa
fase, nessuna esposizione internet.

### D5 — Standard di verifica: APPROVATA

**Proposta**: stesso standard già in uso in tutto TPO — test di dominio,
applicazione e integrazione Postgres reale per ogni nuovo servizio di
lettura, verificati con `pytest` reale da te prima che qualunque boundary
entri in uso, esattamente come per FATTURA e RACCOLTA CORREZIONE.

**Decisione owner: APPROVATA come proposta.** Stesso standard di test
per ogni boundary, senza eccezioni.

## 5. Guardie permanenti (valgono indipendentemente dalle risposte a D1-D5)

- L'adapter web non è mai un secondo Writer: ogni scrittura passa
  esclusivamente per `tpo_core` Application, mai per query dirette a
  Postgres dal livello web.
- Nessuna lettura diretta di Google Sheets: il datastore autorevole resta
  esclusivamente Postgres.
- Nessuna scrittura anonima: ogni comando di scrittura richiede un
  `ActorId` non vuoto, secondo la soluzione scelta in D2.
- Nessuna nuova regola di dominio nel livello web: valida, calcola e
  decide solo l'Application layer già scritto e testato.
- Fase 1 resta a rischio zero per costruzione: nessun nuovo servizio di
  lettura può scrivere.

## 6. Riuso della disciplina comportamentale di `AGENTS.md`

Il ruolo "Daily Briefing" e la regola "mai inventare, usa un segnaposto
quando manca un dato" restano validi e si applicano anche a qualunque
assistente conversazionale che in futuro leggerà/scriverà tramite questo
adapter (fuori scope implementativo qui, ma il principio è già deciso e
va rispettato quando arriverà quel lavoro).

## 7. Fuori scope di questa proposta

- Fase 2 (prime scritture) e oltre: nessuna scrittura è autorizzata da
  questo documento, solo il perimetro di lettura Fase 1 una volta
  approvate D1-D5.
- Login/permessi veri per il team (Fase 3 della roadmap) — qui si decide
  solo la soluzione-ponte D2 per la Fase 2.
- Collegamento al sito pubblico towerpower.green (Fase 5, fuori roadmap).
- Un agente AI conversazionale collegato al database — richiede un
  proprio documento successivo, che si appoggerà a questo boundary una
  volta che Fase 1/2 esistono.
- Qualunque modifica a `tpo_core`, alle sue regole di dominio o ai freeze
  già approvati: questo documento introduce solo un nuovo *consumer* del
  Read Path e, in Fase 2, nuove chiamate al *Write Path* già esistente.

## 8. Prossimo passo

Freeze approvato (D1-D5, 2026-09-09). Implementazione autorizzata: nove
nuovi servizi applicativi di sola lettura (domain query, dove serve;
application layer; infrastruttura Postgres read-only; test a ogni
livello — dominio, applicazione, integrazione Postgres reale), nello
stesso standard già raggiunto per FATTURA e RACCOLTA CORREZIONE.
`AUTHORITY_REGISTRY.yaml` andrà aggiornato con un nuovo concept_id
`OPERATIONAL_WEB_ADAPTER` (status `IMPLEMENTED` per la parte Fase 1) a
implementazione completata e verificata da Giulia con `pytest` reale.
Commit e push restano sempre a cura di Giulia.
