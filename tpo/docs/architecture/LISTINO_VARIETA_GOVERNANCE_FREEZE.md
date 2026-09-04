# LISTINO_VARIETA GOVERNANCE FREEZE — PROPOSTA V1

**Stato:** FREEZE — OWNER APPROVED (2026-09-04).
**Ambito:** chiude il punto lasciato esplicitamente aperto da
`FATTURA_AUTHORITY_FREEZE.md` §9 e §17: "LISTINO_VARIETA commissioning/
versioning/history (chi può cambiare un prezzo, quando, con quale
autorizzazione) — V1 tratta LISTINO_VARIETA come Configuration
direttamente modificabile, senza un proprio boundary di governance."
**Baseline:** branch `sprint-4.4-production-planning`, commit `fcd5450`.

## 1. Scopo

Oggi `PostgreSQLListinoVarietaWriter.set_prezzo()` (CLI `tpo listino-varieta
set`) esegue un semplice UPSERT su `tpo.listino_varieta`: il vecchio prezzo
viene sovrascritto senza lasciare traccia, non produce alcun evento in
`tpo.audit_eventi`, non richiede reason né correlation-id, e accetta come
`actor` qualunque stringa non validata. Questa proposta introduce
governance senza cambiare la natura di LISTINO_VARIETA come Configuration
(non diventa un Authoritative Register, FATTURA continua a leggerne il
valore corrente esattamente come oggi).

## 2. Prior-art gate

| Fonte | Contenuto | Classificazione |
|---|---|---|
| `FATTURA_AUTHORITY_FREEZE.md` §9, §17 | Dichiara esplicitamente deferred "chi può cambiare un prezzo, quando, con quale autorizzazione" per V1. | **CONFERMA IL GATE** — questa proposta è l'implementazione mancante dichiarata. |
| `docs/TPO_REGISTER_CATALOG.md` §5.13 | "Nei Configuration Registers le modifiche sono applicabili esclusivamente dal Writer secondo le autorizzazioni previste" — un Configuration Register richiede comunque autorizzazioni definite, anche se non Facts append-only. | **PRESERVED** — motiva l'aggiunta di autorizzazione/audit senza richiedere di trasformare LISTINO_VARIETA in un Register event-sourced. |
| `docs/TPO_CORE_PRINCIPLES.md` PRINCIPIO 4 | Gli eventi sono immutabili; una correzione è un nuovo evento di rettifica. | **PRESERVED, applicato per analogia solo alla parte di audit** — non si applica a LISTINO_VARIETA stesso (è Configuration, non un Fact), ma motiva l'aggiunta di un evento di audit per ogni cambio, cosicché lo storico dei prezzi non vada comunque perso, anche se la tabella conserva solo il valore corrente. |
| `tpo.audit_eventi` (pattern già usato da RACCOLTA, FATTURA, SEMENTE...) | Ogni comando governato del repository produce un evento di audit con actor/reason/correlation-id. `set_prezzo` è l'unica eccezione rimasta. | **DUPLICATED GAP** — allineare LISTINO_VARIETA allo stesso standard già in uso ovunque, non un'invenzione. |
| Un sistema di ruoli/permessi (RBAC) per "chi è autorizzato" | Nessuna autenticazione/autorizzazione a grana fine esiste in nessun punto del repository oggi. | **MISSING FROM CORE, esplicitamente fuori scope qui** — introdurlo è un lavoro distinto (coincide con la Fase 3 "identità e permessi per il team" della roadmap gestionale). Questa proposta richiede un `ActorId` esplicito e non vuoto e lo audita, ma non decide chi *può* usarlo. |

**Esito:** `PRIOR ART REVIEW PASSED`.

## 3. Cosa cambia

- `set_prezzo` diventa un comando tipizzato `ImpostaPrezzoListinoVarieta`
  (per analogia con gli altri comandi Configuration già governati), con
  `ActorId` (riuso del value object esistente, non una stringa libera),
  `reason` obbligatorio non vuoto, `correlation_id` obbligatorio.
- Ogni esecuzione riuscita produce **un evento in `tpo.audit_eventi`** con:
  `VARIETA` interessata, prezzo/aliquota precedenti (se esisteva una riga),
  prezzo/aliquota nuovi, actor, reason, correlation-id, timestamp. Questo
  ricrea lo storico dei cambi di prezzo senza trasformare
  `tpo.listino_varieta` in un Register a Facts: la tabella resta "valore
  corrente", la storia vive nell'audit — stesso principio già usato altrove
  nel repository per distinguere stato corrente da storico.
- `tpo.listino_varieta` guadagna la stessa transazione atomica già standard
  (lettura VARIETA, UPSERT, insert audit — un'unica transazione, non due
  scritture separate come oggi).
- Nessuna idempotency key/reservation: il comando resta un set diretto del
  valore corrente (non un Fact da riconciliare in replay), coerente con la
  sua natura di Configuration — l'idempotenza naturale è che impostare due
  volte lo stesso prezzo produce lo stesso stato finale, non un conflitto.
- CLI (`tpo listino-varieta set`) guadagna `--reason` e `--correlation-id`
  obbligatori, oltre ai parametri già esistenti.

## 4. Owner Decision D1 — soglia di allarme su variazioni ampie (RISOLTA)

**Decisione owner (2026-09-04): confermato, nessuna soglia bloccante in V1.**
Qualunque prezzo non negativo resta accettabile (il vincolo
`prezzo_unitario >= 0` esiste già). Un controllo su variazioni sospette
(es. "prezzo dimezzato rispetto al precedente, richiedi conferma") resta
un secondo livello di governance, rimandabile a quando ci sarà
un'interfaccia in cui abbia senso mostrare una conferma — non fa parte di
questa implementazione.

## 5. Fuori scope

- Autorizzazione a grana fine (chi ha il permesso di cambiare i prezzi) —
  richiede un sistema di identità/ruoli che non esiste ancora nel
  repository (coincide con la Fase 3 della roadmap gestionale).
- Versionamento come Authoritative Register (storico interrogabile
  direttamente su LISTINO_VARIETA, non solo via audit) — resta Configuration
  "valore corrente" più audit, non un Register a Facts.
- Qualunque modifica a come FATTURA legge/snapshotta il prezzo
  (`FATTURA_AUTHORITY_FREEZE.md` §9, invariato).

## 6. Prossimo passo

D1 confermata. Si procede con l'implementazione: comando tipizzato
`ImpostaPrezzoListinoVarieta` (application layer nuovo,
`src/tpo_core/application/listino_varieta/`), estensione del writer
esistente (stessa tabella `tpo.listino_varieta`, transazione atomica con
audit in `tpo.audit_eventi`), CLI (`--reason`/`--correlation-id`
obbligatori), test a ogni livello — stesso standard di FATTURA e RACCOLTA
CORREZIONE, ma perimetro molto più piccolo (nessuna nuova tabella, nessuna
nuova identità pubblica).
