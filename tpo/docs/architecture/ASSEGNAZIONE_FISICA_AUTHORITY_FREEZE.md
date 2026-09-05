# ASSEGNAZIONE_FISICA V1 FREEZE

## 1. Scope

Congela `ASSEGNAZIONE_FISICA` come nuovo Authoritative Register
(`AUTHORITY_REGISTRY.yaml` — status attuale `UNKNOWN / OWNER DECISION
REQUIRED`, preserved_rule "A physical assignment links one Raccolta
quantity to one Riga Ordine and is not merely a reservation", conflitto
"Production Planning ALL identities are predictive allocations, not
physical assignments"). V1 copre solo la **Fact di creazione**
(registrazione di un'assegnazione RACCOLTA↔RIGA_ORDINE); variazione,
rettifica, riallocazione e annullamento — già previsti concettualmente da
`ASSEGNAZIONI.md` — sono esplicitamente deferred a un boundary successivo,
stesso pattern già usato per RACCOLTA (RACCOLTA_CORREZIONE separata) e
FATTURA (RECTIFY_FATTURA separata).

## 2. Prior-art gate

- `ASSEGNAZIONI.md`: ASSEGNAZIONE rappresenta solo fatti di assegnazione;
  lega obbligatoriamente Raccolta + Riga Ordine, opzionalmente Consegna;
  Fact append-only immutabile, nessuno stato diretto; una Riga Ordine può
  avere zero/una/più Assegnazioni; una Raccolta può alimentare zero/più
  Assegnazioni; contenuto vietato: fatti di Riga Ordine/Raccolta/Consegna,
  documenti commerciali, Stock commerciale, Configuration; la sezione
  rettifica/aggiornamento elenca esplicitamente variazione/rettifica/
  riallocazione/annullamento come eventi futuri distinti (non V1).
- `AUTHORITY_REGISTRY.yaml` — `PRODUCTION_PLANNING`/`ALL` (Allocazione):
  le identità ALL sono allocazioni *predittive* (pianificazione), non
  assegnazioni fisiche — conflitto esplicito già registrato, confermato
  qui: ASSEGNAZIONE_FISICA è un concetto **nuovo e distinto**, non una
  promozione delle identità ALL a "reali". Nessuna relazione/FK tra
  `assegnazioni_fisiche` e le tabelle di production planning.
- Owner Decision (questo giro): **nessun vincolo di capienza/quantità**
  imposto dal sistema — `raccolta_id` su un'Assegnazione è puro riferimento
  di tracciabilità/audit, mai un vincolo quantitativo verificato contro la
  quantità SET della RACCOLTA (stesso precedente di D12 per
  `raccolta_id` su MOVIMENTO_CARICO). Coerente con `ASSEGNAZIONI.md`, che
  non impone un vincolo di capienza come regola di dominio.
- Prefissi identità registrati (rivisti in `AUTHORITY_REGISTRY.yaml`): ALL,
  ART (nuovo, riservato da `ARTICOLO_AUTHORITY_FREEZE.md`), CLI, CON, INC,
  LSE, MOV, ORD, PF, PP, PV, RAC, RO, RPP, RPS, RUN, RVP, SEM, USC, VAR.
  `ASF` è libero, nessuna collisione.
- Schema esistente: `tpo.righe_ordine(id, ordine_id, posizione, varieta_id,
  quantita, unita_misura, public_id NULLABLE)` — `public_id` (`RO-######`,
  `RigaOrdineId`) è stato aggiunto da `20260811_0005_production_planning_foundation.py`
  ed è allocato pigramente (`order_line_identity.py`), non da subito su ogni
  riga: una Riga Ordine senza `public_id` ancora allocato non è referenziabile
  da un'Assegnazione Fisica finché non ne riceve uno (limite di
  implementazione preesistente, non una regola nuova introdotta qui).
  `tpo.raccolte(id, public_id, semina_id, quantita, unita_misura='SET', ...)`
  e `tpo.consegne(id, public_id, ...)` sono invece referenziabili per
  `public_id` sempre presente. Precedente diretto per il pattern "risolvi
  per public_id, blocca per id interno": `PostgreSQLMovimentoCaricoWriter._lock_raccolta`.

## 3. Decisioni tecniche (derivate)

- Nuova tabella `tpo.assegnazioni_fisiche`: Register append-only, una riga
  per Fact di assegnazione. Colonne: `id` (PK interno), `public_id`
  (`ASF-######`), `raccolta_id` FK → `tpo.raccolte.id` (obbligatorio),
  `riga_ordine_id` FK → `tpo.righe_ordine.id` (obbligatorio),
  `consegna_id` FK → `tpo.consegne.id` (nullable — opzionale, per
  `ASSEGNAZIONI.md`), `quantita_assegnata NUMERIC(20,6)` CHECK `> 0`,
  `unita_misura`, `effective_at`, `motivo`, `created_at`, `created_by`.
  Nessun vincolo di somma/capienza contro `raccolte.quantita` (Owner
  Decision di cui sopra) né contro `righe_ordine.quantita` (una Riga
  Ordine può avere più Assegnazioni per definizione — `ASSEGNAZIONI.md`
  non impone che la somma coincida con la quantità ordinata; imporlo ora
  sarebbe una regola non richiesta dall'owner e non presente nel Register
  doc).
- Nessuna FK verso le identità ALL di production planning (per il
  conflitto già registrato — sono concetti distinti, nessun accoppiamento).
- `unita_misura` sull'Assegnazione non è vincolata a coincidere con quella
  della RACCOLTA (SET) o della Riga Ordine (GRAM di norma) — è un campo
  puramente descrittivo della quantità dichiarata in questa Fact,
  coerente con l'assenza di vincolo di capienza; nessuna conversione
  automatica introdotta (stesso principio di D11 per MOVIMENTO_CARICO:
  nessuna Configuration di conversione SET↔GRAM).
- Idempotenza via tabella di reservation dedicata
  `tpo.assegnazione_fisica_requests` (stesso pattern reserve-or-replay già
  usato ovunque in questo progetto).

## 4. Modello

```text
RegistraAssegnazioneFisica(
    raccolta_id: RaccoltaId,
    riga_ordine_id: RigaOrdineId,   # risolto per public_id (RO-######), FOR SHARE
    consegna_id: Optional[ConsegnaId],
    quantita_assegnata: Decimal,    # > 0
    unita_misura: UnitOfMeasure,
    effective_at: datetime,
    motivo: str,
    authority: AssegnazioneFisicaAuthority(actor, reason, correlation_id, idempotency_key),
) -> RegistraAssegnazioneFisicaResult
```

Nessuna verifica di capienza contro `raccolta.quantita` o
`riga_ordine.quantita` (Owner Decision). Verifiche minime: la RACCOLTA e
la RIGA_ORDINE devono esistere (per `public_id`); se `consegna_id` è
fornito, la CONSEGNA deve esistere ed essere collegata alla stessa
`riga_ordine_id` — verificato con una query diretta su
`tpo.righe_consegna` (`SELECT 1 ... WHERE consegna_id=? AND riga_ordine_id=?`),
coerenza referenziale minima, non una regola di business nuova — impedisce
solo un'Assegnazione palesemente incoerente, es. una Consegna di un'altra
Riga Ordine.

## 5. Schema (migrazione additiva)

Nuove tabelle: `tpo.assegnazioni_fisiche`,
`tpo.assegnazione_fisica_requests` (reservation/idempotenza, stesso schema
delle altre request table). Nessuna modifica a tabelle esistenti. Nuovo
identifier `AssegnazioneFisicaId` (prefix `ASF`), seed dedicato in
`tpo.id_sequences` nella stessa migrazione (stesso pattern di
`20260830_0022_raccolta_authority.py`).

## 6. Fuori scope (deferred)

- Variazione, rettifica, riallocazione, annullamento di
  un'Assegnazione (eventi futuri distinti, già previsti concettualmente
  da `ASSEGNAZIONI.md` ma non costruiti ora — stesso pattern
  RACCOLTA/RACCOLTA_CORREZIONE, FATTURA/RECTIFY_FATTURA).
- Qualunque vincolo di capienza/quantità (esplicitamente escluso da Owner
  Decision, non solo rimandato).
- Riconciliazione con le identità ALL di production planning.
- Un calcolo aggregato "quanto è già assegnato" per Riga Ordine o Raccolta
  (nessuna proiezione derivata richiesta ora — a differenza di
  PRENOTATO/VENDIBILE per STOCK, qui non c'è una Owner Decision che lo
  richieda).

## 7. Implementazione

Dominio: nuovo `AssegnazioneFisicaId` (prefix `ASF`); riuso di
`RigaOrdineId`/`ConsegnaId`/`RaccoltaId` già esistenti. Applicazione:
`src/tpo_core/application/assegnazione_fisica/{models,ports,service,errors}.py`.
Infrastruttura: `src/tpo_core/infrastructure/postgresql/
assegnazione_fisica.py` (stesso schema reserve-or-replay di
`PostgreSQLRaccoltaWriter.record`, con la risoluzione RACCOLTA/RIGA_ORDINE/
CONSEGNA per `public_id` sul modello di `PostgreSQLMovimentoCaricoWriter._lock_raccolta`).
Bootstrap e CLI coerenti con lo stile esistente (`tpo assegnazione registra`).
Test: stesso livello di copertura di ogni altro boundary (dominio,
applicazione, CLI, migrazione, integrazione PostgreSQL reale — inclusi i
casi: consegna_id assente, consegna_id valorizzato e coerente, consegna_id
valorizzato ma su un'altra riga ordine → rifiutato, riga_ordine senza
public_id ancora allocato → rifiutato).

Aggiornamento `AUTHORITY_REGISTRY.yaml`: nuovo concetto
`ASSEGNAZIONE_FISICA`, status `FROZEN`, cross-reference da `RACCOLTA` e
`ORDINE`/`RIGA_ORDINE`; nota esplicita di non-relazione con
`PRODUCTION_PLANNING`/`ALL`.
