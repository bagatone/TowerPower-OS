# ROADMAP — Software Gestionale TPO (Tower Power Operations)

**Stato:** PROPOSTA DI PIANIFICAZIONE — non è un Freeze e non autorizza alcuna
implementazione. Va letta, corretta e approvata dall'owner prima che qualunque
fase inizi a scrivere codice.
**Tipo di documento:** analogo a `docs/reviews/PROJECT_ARCHITECTURE_REVIEW_2026.md`
— un documento di visione e sequenziamento, non una registrazione di autorità.
**Data:** 2026-09-03
**Autore:** sessione Claude, su richiesta dell'owner ("deve diventare una
parte indispensabile per TowerPower. deve essere il mio software gestionale").

## 1. Obiettivo dichiarato dall'owner

Non un'anteprima, non un cruscotto pubblico: un'applicazione di lavoro reale,
multi-utente, in rete locale, con cui l'owner e il team possano sia
consultare sia inserire/modificare dati operativi reali (semine, raccolte,
consegne, ordini — e in prospettiva il resto del dominio TPO). L'owner vuole
potersene fidare ciecamente e vuole che diventi lo strumento gestionale
quotidiano di Tower Power. Il sito pubblico (towerpower.green) verrà
collegato in un secondo momento, separatamente, a scopo di comunicazione —
non è oggetto di questa roadmap.

## 2. Cosa esiste già oggi (la fondamenta su cui si costruisce)

Questo non parte da zero. TPO ha già:

- **PostgreSQL come unica autorità runtime**, sancito da
  `POSTGRESQL_FOUNDATION_FINAL_FREEZE.md` e riaffermato ad ogni Freeze
  successivo: nessuna scrittura silenziosa altrove, nessun doppio percorso.
- **14 moduli CLI governati** (`src/tpo_core/cli/`), ciascuno collegato a un
  boundary Application/Domain/Infrastructure specifico e a un proprio
  documento di Freeze in `docs/architecture/`: onboarding, seed_lot, semente,
  semente_impiego, semina, raccolta, delivery (consegne/ordini), cliente,
  listino_varieta, fattura, production_planning, scheduling, operational,
  preflight.
- **Oltre 1350 test** automatizzati (dominio, applicazione, infrastruttura,
  integrazione PostgreSQL reale), con la stessa disciplina appena applicata a
  FATTURA: nessun boundary entra in produzione senza copertura completa e
  verifica su PostgreSQL reale.
- Un principio già scritto nel Freeze `APPLICATION_OPERATIONAL_ENTRYPOINT_FREEZE.md`:
  il contratto applicativo verso l'esterno è **provider-neutral** — esplicitamente
  pensato per essere usato, senza modifiche, da CLI, API, Scheduler, Job, Batch
  o Event Consumer. In altre parole: l'architettura attuale è già stata
  progettata prevedendo che un giorno arrivasse un adapter diverso dalla CLI.
  Il gestionale è quel giorno.
- Una prima anteprima visiva (la dashboard "Sala Operativa", con dati di
  esempio) che ha già validato un linguaggio grafico e un primo taglio di
  informazioni utili: produzione (semine/raccolte), consegne, ordini.

**Conseguenza pratica:** il gestionale non è un progetto nuovo scritto da zero.
È un nuovo *adapter* (un'interfaccia web) che si appoggia sulla stessa
Application e sullo stesso Domain già scritti, testati e in uso dalla CLI —
mai una loro reinvenzione o duplicazione. Questo è anche ciò che permette di
fidarsi: la logica di business che deciderà se una raccolta è valida, se una
consegna può cambiare stato, se un numero di fattura è coerente, resta
esattamente quella già collaudata da centinaia di test — l'app non la
riscrive, la richiama.

## 3. Il vincolo che decide la forma tecnica

Una pagina "Artifact" pubblicata online (come la dashboard di anteprima) gira
nel browser di chiunque la apra e non può collegarsi in modo sicuro a un
database di produzione privato. Un gestionale vero, multi-utente, in rete
locale, richiede invece un'applicazione a sé: un piccolo servizio che gira
sul tuo computer o su una macchina della rete locale, collegato direttamente
al database TPO, più un'interfaccia web che ci parla dalla stessa rete.
Nessuna delle due parti sarà esposta su internet in questa fase — coerente
con la tua richiesta ("non deve essere online").

## 4. Principio guida per ogni fase

Le stesse regole già in vigore per tutto il resto di TPO si applicano al
gestionale, senza eccezioni:

- **Nessuna invenzione silenziosa.** Ogni nuovo boundary (il "motore" del
  gestionale, l'identità degli utenti, ogni nuova operazione di scrittura)
  passa prima dalla ricognizione prior-art e da un documento di Freeze
  owner-approved, esattamente come `FATTURA_AUTHORITY_FREEZE.md`.
- **Un boundary alla volta.** Non si costruisce "tutto il gestionale" in un
  colpo solo: si aggiunge una funzione, la si copre di test fino allo stesso
  livello già raggiunto altrove, la rivedi, e solo allora entra in uso reale.
- **Lettura prima di scrittura.** Ogni nuova area del gestionale nasce in
  sola lettura (vedi dati reali, non può ancora modificarli) e passa alla
  scrittura solo dopo revisione esplicita.
- **Nessuna logica duplicata.** L'app non decide da sola le regole del
  business: chiama sempre l'Application già esistente, la stessa che usa la
  CLI. Se la CLI oggi impedisce di far tornare indietro una consegna già
  "CONSEGNATA", l'app rispetta lo stesso vincolo perché passa dallo stesso
  codice.
- **Tu resti il proprietario del via libera.** Come per FATTURA, il commit e
  il push restano sempre operazioni tue, dal tuo terminale.

## 5. Le fasi

### Fase 0 — Governance del nuovo boundary (prossimo passo immediato)

Prima di scrivere una sola riga di codice dell'app, prepariamo (io la bozza,
tu la revisione e l'approvazione) un documento di Freeze per il nuovo
boundary — nome di lavoro `OPERATIONAL_WEB_ADAPTER` — che risolve, come
hanno già fatto gli altri Freeze:

- quali operazioni sono esposte in lettura e quali in scrittura, boundary per
  boundary, e in che ordine;
- come si identifica ogni utente che scrive (oggi la CLI richiede sempre un
  `--identity`/`--actor` esplicito: il gestionale userà un vero login, ma il
  principio — nessuna scrittura anonima — resta identico);
- come gli esiti e gli errori dell'Application (già definiti in modo
  provider-neutral) si traducono in risposte per l'interfaccia web, senza
  inventare nuove regole di validazione lato app;
- dove gira il servizio (solo rete locale), chi vi accede e con quali
  permessi;
- come si verifica ogni nuova funzione (stesso standard: test dominio,
  applicazione, PostgreSQL reale).

Questa fase produce un documento, non codice.

### Fase 1 — Fondamenta tecniche in sola lettura

Un piccolo servizio locale che espone, in sola lettura, esattamente ciò che
oggi già puoi interrogare da riga di comando: stato delle semine e del ciclo
di produzione, raccolte, consegne, ordini. Nessuna scrittura ancora. Obiettivo
concreto: sostituire la dashboard con dati di esempio con la stessa dashboard
collegata ai dati veri, sempre aggiornata, a rischio zero perché non può
modificare nulla.

### Fase 2 — Prime scritture, a basso rischio

Una o due operazioni per volta (candidate naturali: segnare l'avanzamento di
una raccolta, aggiornare lo stato di una consegna), ciascuna portata allo
stesso livello di test già visto per FATTURA prima di essere collegata
all'interfaccia. Si parte da ciò che ha conseguenze più contenute in caso di
errore, non da fatture o pagamenti.

### Fase 3 — Identità e permessi per il team

Un vero sistema di accesso (login) per te e per le persone del team che
useranno l'app in rete locale, così che ogni inserimento/modifica porti con
sé in modo tracciabile chi l'ha fatto — lo stesso principio di responsabilità
già richiesto oggi da ogni comando CLI, reso comodo per un'interfaccia
condivisa.

### Fase 4 — Copertura progressiva del resto del dominio

Boundary dopo boundary, tutto ciò che oggi è raggiungibile da CLI
(clienti, listino varietà, semente, fatture, pianificazione produzione...)
diventa raggiungibile anche dall'app, mantenendo sempre la sequenza:
ricognizione → Freeze di boundary → implementazione → test completi →
revisione tua → attivazione. Le aree più delicate (fatture, e in futuro
pagamenti/incassi) restano per ultime e con revisione ancora più stringente.

### Fase 5 — Fuori roadmap, esplicitamente rimandata

Il collegamento con il sito pubblico towerpower.green per finalità di
comunicazione/pubblicità è un progetto distinto, con un pubblico diverso
(visitatori esterni, non il team). Non userà mai lo stesso canale di
scrittura del gestionale interno e mostrerà solo contenuti curati,
esplicitamente approvati per essere pubblici — mai una vista diretta sul
database di produzione. Ne parliamo quando questa roadmap avrà prodotto
qualcosa di stabile da mostrare.

## 6. Perché questo approccio merita la fiducia che chiedi

Non te lo prometto a parole: te lo dimostra il precedente che abbiamo appena
chiuso insieme. FATTURA V1 è arrivata in produzione solo dopo domain,
application, infrastruttura, CLI e integrazione PostgreSQL reale
completamente testati, con tre round di correzioni verificate dai tuoi stessi
`pytest` fino a 1928 test passati e zero falliti, e con revisione e comando
di commit sempre nelle tue mani. Il gestionale seguirà esattamente lo stesso
percorso, boundary per boundary — è l'unico modo, in questo progetto, per
guadagnarsi il diritto di essere "indispensabile".

## 7. Prossimo passo concreto

Se questa sequenza ti convince, il passo immediato è che io prepari la bozza
del Freeze di Fase 0 (`OPERATIONAL_WEB_ADAPTER`, o il nome che preferisci),
seguendo la stessa procedura di ricognizione prior-art già vista per FATTURA,
da rivedere e approvare prima che si scriva la prima riga di codice
dell'applicazione.


## 8. Addendum — decisione owner: sequenza pre-gestionale (2026-09-03)

L'owner ha deciso di **non** avviare la Fase 0 di questa roadmap subito. Prima
si chiudono le lacune di dominio più critiche già emerse dal registro di
autorità, nell'ordine seguente (dal repository, non da questa roadmap: la
gestionale resta successiva):

1. **Correzione/annullamento** di RACCOLTA, SEMENTE, SEMENTE_IMPIEGO,
   SEED_LOT — oggi append-only senza percorso governato per correggere un
   errore di inserimento. Priorità più alta: rischio quotidiano più diretto,
   perimetro più circoscritto (si estendono boundary già esistenti e
   testati, non se ne inventano di nuovi).
2. **PRODOTTO vs Varieta** — conflitto di modellazione oggi aperto in
   ORDINE, STOCK e implicitamente nel LISTINO_VARIETA; risolverlo presto
   evita di dover rifare lavoro sui punti successivi.
3. **Governo del LISTINO_VARIETA** (prezzi) — oggi Configuration liberamente
   modificabile, senza autorizzazione né storicizzazione.
4. **PAGAMENTO/INCASSO** — il pezzo economicamente più rilevante, costruito
   dopo che Prodotto e Listino sono stabili.
5. **RectifyFattura** — naturale seguito di Pagamento/Incasso.
6. **Tracciabilità CONSEGNA → RACCOLTA** e riconciliazione STOCK /
   MOVIMENTO_MAGAZZINO — importanti ma meno urgenti per l'uso quotidiano.

Rimangono esplicitamente fuori scope, come già deciso dall'owner:
DOCUMENTO_DI_VENDITA ed elettronica (SII/Verifactu/SDI).

Ogni punto sopra segue comunque la stessa disciplina già in uso in tutto TPO:
ricognizione prior-art → bozza di Freeze di boundary → revisione e
approvazione owner → implementazione con test completi (dominio,
applicazione, PostgreSQL reale) → commit/push sempre a cura dell'owner. Le
Fasi 0-5 di questa roadmap (il software gestionale vero e proprio) restano
valide come descritte sopra e riprendono una volta chiuso questo lavoro.

**Prossimo passo concreto in corso:** ricognizione prior-art e bozza di
Freeze per la correzione/annullamento di RACCOLTA (punto 1).


## 9. Stato di avanzamento — punto 1 completato (2026-09-03)

`RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md` approvato e implementato: domain,
application, migrazione `20260903_0027`, writer PostgreSQL, CLI (`tpo raccolta
correggi`) e test a ogni livello. Suite completa verificata dall'owner con
`python -m pytest` reale: **1969 passed, 8 skipped, 0 failed**. Prossimo
punto della sequenza (§8, addendum 2026-09-03): **2. PRODOTTO vs Varieta**.
