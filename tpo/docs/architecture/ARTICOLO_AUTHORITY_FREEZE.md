# ARTICOLO (E MOVIMENTO/STOCK GENERICO) AUTHORITY V1 FREEZE

## 1. Scope

Congela `ARTICOLO` come Configuration distinta da VARIETA e PRODOTTO
(`TPO_DATA_DICTIONARY.md` §6.1), e risolve il conflitto in
`MOVIMENTI_MAGAZZINO.md`/`STOCK.md` ("generic article inventory remains
unmigrated") estendendo MOVIMENTO_MAGAZZINO/STOCK a operare anche su un
ARTICOLO, non solo su una VARIETA (Owner Decision: estensione completa,
non solo commissioning dell'identità).

Restano esplicitamente fuori scope (§6.2-6.4 di `TPO_DATA_DICTIONARY.md`,
non richiesti da questa decisione): Ricetta di produzione, Fornitore,
Inventario aggregato, Problema Operativo. ARTICOLO qui è solo la referenza
anagrafica più il suo STOCK/MOVIMENTO; nessuna di queste relazioni viene
costruita ora.

**Chiarimento owner sulla semantica di dominio** (non cambia il design
tecnico di questo freeze, ma ne precisa lo scope): ARTICOLO identifica i
materiali che servono alla catena produttiva perché la catena funzioni —
substrati, fertilizzante, packaging, e simili — mentre VARIETA identifica
i semi, parte fondamentale e distinta della catena. Le due identità
restano quindi concettualmente separate esattamente come già congelato
(nessuna sovrapposizione VARIETA/ARTICOLO); il modello di §3-5 sotto vale
invariato per qualunque materiale di questo tipo (substrato, fertilizzante,
packaging, ecc.), senza distinzioni di sotto-categoria in V1 — un'eventuale
tipizzazione di ARTICOLO (es. "substrato" vs "packaging" come Configuration
separate) resta deferred, non richiesta ora.

## 2. Prior-art gate

- `TPO_DATA_DICTIONARY.md` §6.1: ARTICOLO è "qualsiasi referenza gestita da
  TPO", identità concettuale "distinta da Varietà e Prodotto", non
  necessariamente un Prodotto.
- `AUTHORITY_REGISTRY.yaml` — `ARTICOLO`: conflitto "Legacy article codes
  overlap semantically with current identity prefixes"; decisione aperta
  "Freeze generic article and inventory authority before migration".
  `MOVIMENTO_MAGAZZINO`: conflitto "generic article inventory remains
  unmigrated"; decisione aperta "Define the boundary between product stock
  movements and generic inventory movements".
- `MOVIMENTI_MAGAZZINO.md` dichiara oggi come principio congelato: "Ogni
  MOVIMENTO modifica esclusivamente lo STOCK di una sola VARIETÀ."
  `tpo.stock.varieta_id` è PRIMARY KEY (una riga per VARIETA).
  **Decisione owner esplicita**: questo principio viene esteso (non
  sostituito) a coprire anche ARTICOLO, senza toccare la forma esistente di
  `tpo.stock`/le sue righe VARIETA — vedi §4 per come si ottiene questo
  senza rischio sulle tabelle già in produzione.
- Prefissi identità già registrati (verificati via `AUTHORITY_REGISTRY.yaml`):
  ALL, CLI, CON, INC, LSE, MOV, ORD, PF, PP, PV, RAC, RO, RPP, RPS, RUN, RVP,
  SEM, USC, VAR. `ART` è libero, nessuna collisione (risolve il conflitto
  sui prefissi legacy sopra).

## 3. Decisioni tecniche (derivate, non nuove Owner Decision — conseguenze
   dirette della scelta "estensione completa" già confermata)

- **Nessuna modifica alla forma di `tpo.stock` esistente**: PRIMARY KEY
  `varieta_id` resta invariata. Il supporto ad ARTICOLO vive in una tabella
  **parallela** `tpo.stock_articoli` (stessa forma di `tpo.stock`: PK
  `articolo_id`, `disponibile`, `unita_misura`, `ultimo_movimento_id`,
  `updated_at`, `version`) — zero rischio di regressione sui writer/test
  VARIETA esistenti (CONSEGNA, CARICO, production planning), che continuano
  a vedere `tpo.stock` esattamente come prima.
- `tpo.movimenti_magazzino.varieta_id` diventa **nullable** (rilassamento,
  non restrittivo: tutte le righe esistenti hanno già un valore). Nuova
  colonna nullable `articolo_id` con FK verso `tpo.articoli.id`. Nuovo
  CHECK `ck_movimenti_magazzino_risorsa_xor`: esattamente una tra
  `varieta_id`/`articolo_id` deve essere valorizzata (mai entrambe, mai
  nessuna) — stesso stile del già esistente `MOVIMENTO_ORIGIN_REFERENCE_CHECK`.
  Nuova FK composita `(articolo_id, unita_misura) -> stock_articoli
  (articolo_id, unita_misura)`, con `UNIQUE(articolo_id, unita_misura)` su
  `stock_articoli` (stesso precedente/stessa lezione già imparata per
  `movimento_carico_requests`: una FK composita richiede un vincolo UNIQUE
  che copra esattamente quelle colonne).
- La FK composita esistente `(varieta_id, unita_misura) -> stock(varieta_id,
  unita_misura)` non richiede modifiche: con `varieta_id` NULL su una riga
  ARTICOLO, Postgres non verifica quella FK su quella riga (semantica
  MATCH SIMPLE, comportamento standard per FK composite con colonne NULL).
- `MOVIMENTO_ORIGIN_REFERENCE_CHECK` (origine RACCOLTA/CONSEGNA) non
  richiede modifiche: un movimento ARTICOLO usa `origine_tipo` fuori da
  quell'insieme (`'ARTICOLO_MOVIMENTO'`), già ammesso dal ramo generico
  esistente del CHECK.
- Nessun movimento ARTICOLO deriva da RACCOLTA/CONSEGNA (quelle origini
  restano VARIETA-specifiche per definizione fisica). Per V1, l'unico
  comando applicativo è un movimento genericamente autorizzato
  (equivalente a un CARICO/SCARICO/RETTIFICA manuale), non un evento
  derivato da un altro Register.

## 4. Modello

```text
ARTICOLO (Configuration: id, public_id ART-######, denominazione, unita_misura, ...)
   │
   ▼
MOVIMENTO_MAGAZZINO (stesso Register, ora anche origine_tipo='ARTICOLO_MOVIMENTO'
                      su un ARTICOLO invece che su una VARIETA)
   │
   ▼
STOCK_ARTICOLI.disponibile += / -= quantità, per l'ARTICOLO
```

### ARTICOLO — commissioning

```text
CommissionArticolo(
    denominazione: str,
    unita_misura: UnitOfMeasure,   # unità di riferimento per lo stock di quell'ARTICOLO
    authority: ArticoloCommissioningAuthority(actor, reason, correlation_id, idempotency_key),
) -> ArticoloId
```

`ArticoloId` (prefix `ART`) allocato dal writer nella stessa transazione
(stesso schema `tpo.id_sequences` di ogni altra identità). Idempotenza via
tabella di reservation dedicata (`tpo.articolo_commissioning_requests`,
stesso pattern reserve-or-replay già usato ovunque in questo progetto).
`denominazione` non vuota; nessuna unicità imposta su `denominazione`
(due Articoli possono avere nomi simili — nessun business-key naturale
dichiarato da `TPO_DATA_DICTIONARY.md` oltre l'identità stessa).

### ARTICOLO — movimento di magazzino

```text
RegistraMovimentoArticolo(
    articolo_id: ArticoloId,
    tipo: MovimentoType,           # CARICO | SCARICO | RETTIFICA
    quantita: Decimal,             # > 0, il verso è dato da tipo/direzione
    unita_misura: UnitOfMeasure,   # deve combaciare con quella di commissioning
    effective_at: datetime,
    motivo: str,
    authority: MovimentoArticoloAuthority(actor, reason, correlation_id, idempotency_key),
) -> RegistraMovimentoArticoloResult
```

`direzione` è derivata da `tipo` (CARICO/SCARICO fissi POSITIVO/NEGATIVO;
RETTIFICA richiede una direzione esplicita nel comando, coerente con
`MOVIMENTI_MAGAZZINO.md`: "Il verso della variazione ... è distinto dal
tipo di MOVIMENTO"). Se `tpo.stock_articoli` non ha ancora una riga per
quell'ARTICOLO, il writer la crea contestualmente (`disponibile=0` prima
della variazione, `unita_misura` presa dal comando); se la riga esiste già
con un'unità diversa, il comando fallisce chiuso (stesso pattern di
`MovimentoCaricoStockUnitMismatchError`). Un movimento SCARICO/RETTIFICA
negativa che porterebbe `disponibile` sotto zero viene rifiutato (stesso
`ck_stock_disponibile_nonnegative`, replicato su `stock_articoli`).

## 5. Schema (migrazione additiva)

Nessuna modifica a `tpo.stock`, `tpo.raccolte`, `tpo.consegne`. Modifiche a
`tpo.movimenti_magazzino`: `varieta_id` diventa nullable, nuova colonna
`articolo_id` nullable + FK, nuovo CHECK XOR risorsa, nuova FK composita
verso `stock_articoli`. Nuove tabelle: `tpo.articoli` (Configuration),
`tpo.stock_articoli` (stesso schema di `tpo.stock`), `tpo.articolo_commissioning_requests`
e `tpo.movimento_articolo_requests` (reservation/idempotenza, stesso schema
delle altre request table di questo progetto).

## 6. Fuori scope (deferred)

- Ricetta di produzione, Fornitore, Inventario aggregato, Problema
  Operativo (`TPO_DATA_DICTIONARY.md` §6.2-6.4) — nessuna relazione
  costruita ora.
- Qualunque business-key/unicità su `denominazione` di ARTICOLO.
- Origine RACCOLTA/CONSEGNA per un movimento ARTICOLO (fisicamente non
  applicabile).
- Riconciliazione/aggregazione tra STOCK (VARIETA) e STOCK_ARTICOLI in
  un'unica vista di "Inventario" — restano due Register/tabelle distinte.

## 7. Implementazione

Dominio: nuovo `ArticoloId` (prefix `ART`). Applicazione:
`src/tpo_core/application/articolo/` (commissioning) e
`src/tpo_core/application/movimento_articolo/` (movimento). Infrastruttura:
`src/tpo_core/infrastructure/postgresql/articolo.py`,
`.../movimento_articolo.py`. Bootstrap e CLI coerenti con lo stile
esistente (`tpo articolo commissiona`, `tpo movimento carica-articolo` /
`scarica-articolo` / `rettifica-articolo`). Test: stesso livello di
copertura di ogni altro boundary di questo progetto (dominio, applicazione,
CLI, migrazione, integrazione PostgreSQL reale).

Amendment ai freeze esistenti: `MOVIMENTI_MAGAZZINO.md` riceve
un'appendice che estende (non sostituisce) il principio "una sola VARIETÀ"
a "una sola VARIETÀ o un solo ARTICOLO"; `STOCK.md` resta invariato (governa
solo `tpo.stock`/VARIETA); `STOCK_ARTICOLI` come concetto viene descritto
nella stessa appendice, mirror dei principi di STOCK.md applicati ad
ARTICOLO.
