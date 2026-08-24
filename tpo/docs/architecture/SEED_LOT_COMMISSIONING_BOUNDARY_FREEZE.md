# SEED LOT COMMISSIONING BOUNDARY V1 FREEZE

## 1. PRE-FLIGHT

**Status:** FINAL ARCHITECTURE FREEZE CANDIDATE — OWNER REVIEW REQUIRED.

This freeze was prepared against the following verified baseline:

| Authority | Frozen baseline |
|---|---|
| repository | `/Users/bagatone/Documents/Codex/2026-06-28/a/work/towerpower-website/tpo` |
| writable | `YES` |
| branch | `sprint-4.4-production-planning` |
| HEAD | `5e5b2f4` |
| working tree before this document | clean |
| Alembic live head | `20260823_0016` |
| operational target | `TPO V1 OPERATIONAL PILOT` |

The live target was inspected read-only. At freeze time it contains zero
`lotti_seme` and no `LOTTO_SEME_ID` Identity registration. This document does
not authorize a migration, Identity registration, commissioning operation,
database write, SEMINA creation, Production Planning execution, commit, or
push.

## 2. FROZEN SCOPE

This freeze governs only the V1 commissioning of an existing physical seed lot
into the existing `LOTTO_SEME` authority.

The governed path is:

```text
authorized caller
→ thin CLI adapter
→ CommissionSeedLot command
→ SeedLotCommissioningService
→ PostgreSQLSeedLotCommissioningWriter
→ one PostgreSQL transaction
   ├── allocate LSE-* from LOTTO_SEME_ID
   ├── create LOTTO_SEME
   ├── persist idempotency authority
   └── append audit/provenance
```

This freeze does not create another seed-lot entity. It does not create or
govern SEMINA. `SEM-*` remains the permanent identity of a physical production
group; `LSE-*` identifies only the physical seed lot used by one or more such
groups.

## 3. FROZEN LOTTO_SEME SEMANTICS

### 3.1 Definition

`LOTTO_SEME` is the permanent authority for one physically distinguishable lot
of seed that Tower Power has received and can hold or consume. It is seed
material, not a production cycle, crop, tray, sowing, harvest, commercial stock,
or delivery.

The constitutive business identity is:

```text
authoritative SEMENTE + normalized manufacturer lot number
```

The existing unique constraint on `(semente_id, numero_lotto_produttore)` is
the definitive business-duplicate guard. `LSE-*` is the permanent public
identity and never replaces that business constraint.

### 3.2 Constitutive facts

The constitutive facts are:

- resolved authoritative `SEMENTE`;
- manufacturer lot number;
- permanent `LSE-*` identity;
- commissioning identity/key and canonical payload hash.

Reception date, expiry date, quantities, UOM, anomaly and provenance are
authoritative facts of the lot but do not create a second lot identity.

### 3.3 Relationship with SEMENTE

Every `LOTTO_SEME` belongs to exactly one existing `SEMENTE`. V1 resolves that
SEMENTE by its existing normalized authoritative business identity:

```text
lower(trim(fornitore)) + lower(trim(referenza_commerciale))
```

The resolved SEMENTE must exist and be active. Internal bigint keys remain
Infrastructure details and are never accepted by the application command or
CLI.

### 3.4 Relationship with SEMENTE_IMPIEGO

Commissioning a lot proves which SEMENTE it contains; it does not authorize
every productive use. `SEMENTE_IMPIEGO` remains the separate compatibility
authority between that SEMENTE and a cultivar/use.

The commissioning boundary does not create or amend `SEMENTE_IMPIEGO`. The
future SEMINA command must verify that the selected lot's SEMENTE has an
eligible `SEMENTE_IMPIEGO` for the requested cultivar/use. Missing,
`SCONSIGLIATA`, or otherwise ineligible authority fails closed.

### 3.5 Relationship with SEM-*

One `LOTTO_SEME` may be referenced by zero, one, or many `SEM-*`. Every future
SEMINA references exactly one `LOTTO_SEME`. Consumption by a SEMINA changes
only the seed lot's residual quantity; it never changes the lot's identity or
constitutive facts.

### 3.6 Historical permanence

An exhausted, expired, anomalous, superseded, or unused lot remains readable
forever. Exhaustion means `quantita_residua = 0`; it does not mean deletion or
closure of historical references.

`LOTTO_SEME` is never hard-deleted after commissioning. All FK references use
`ON DELETE RESTRICT`. Direct physical deletion and identity reuse are forbidden.

### 3.7 Correction policy summary

No commissioned row is corrected by manual SQL or an ungoverned repository
update. Constitutive identity facts are immutable. Corrections to non-
constitutive facts require a future explicit correction command and append-only
audit. Quantity changes use quantity operations only.

## 4. FROZEN IDENTITY AUTHORITY

The repository currently has no `LottoSemeId` Permanent ID type and no
`LOTTO_SEME_ID` sequence. V1 freezes the required additions as follows:

| Component | Frozen value |
|---|---|
| domain type | `LottoSemeId(PermanentId)` |
| prefix | `LSE` |
| public format | `LSE-[0-9]{6,}` |
| first valid value | `LSE-000001` |
| sequence name | `LOTTO_SEME_ID` |
| identifier type registration | `LottoSemeId` |
| authority table | existing `tpo.id_sequences` |
| public ID column | future `lotti_seme.public_id`, NOT NULL, UNIQUE, immutable |

`LSE` is frozen to distinguish seed lots from `SEM` production groups and from
any generic or future lot concept. `LOT`, `LS`, `SEM`, technical bigint IDs and
manufacturer lot numbers are not public TPO identities.

The Identity registration must be commissioned before the first lot, using the
existing incremental Identity commissioning boundary. This freeze does not
commission it.

Allocation occurs inside the same transaction as lot creation. The writer locks
the `LOTTO_SEME_ID` row, validates type/prefix/current version, reserves exactly
one value and advances `next_value` and `version`. An absent or incompatible
registration, a CAS mismatch, or any generated-ID collision fails the entire
transaction. IDs from rolled-back transactions may be retried; no committed ID
may ever be reused.

## 5. FROZEN MINIMUM INPUT CONTRACT

`public_id`, internal PK, `quantita_residua`, timestamps and optimistic version
are writer-owned and are not caller input.

| Field | Authority | Required? | Unknown allowed? | Immutable? |
|---|---|---:|---:|---:|
| `seed_supplier` | existing `sementi.fornitore` business identity | REQUIRED | NO | YES after resolution |
| `seed_commercial_reference` | existing `sementi.referenza_commerciale` business identity | REQUIRED | NO | YES after resolution |
| `manufacturer_lot_number` | label/owner-authorized physical lot fact | REQUIRED | NO | YES |
| `received_date` | owner-authorized physical business date | REQUIRED | NO under current schema | NO direct rewrite; correction command only |
| `expiry_date` | label/owner-authorized date | OPTIONAL | YES (`NULL`) | NO direct rewrite; correction command only |
| `initial_quantity` | owner-authorized measured/label quantity | REQUIRED | NO | NO direct rewrite; correction command only |
| `unit` | seed quantity UOM | REQUIRED and exactly `GRAM` | NO | YES |
| `anomaly` | owner observation | OPTIONAL | YES (`NULL`) | correction command only |
| `provenance` | source classification for supplied facts | REQUIRED | NO | append-only audit |
| `actor` | application authority | REQUIRED | NO | audit fact |
| `reason` | application authority | REQUIRED | NO | audit fact |
| `correlation_id` | tracing authority | REQUIRED | NO | audit fact |
| `idempotency_key` | commissioning request authority | REQUIRED | NO | YES |

`received_date` remains required because the existing schema makes
`data_ricezione` NOT NULL. It is a local `Atlantic/Canary` calendar date, not a
fabricated timestamp. If the date is unknown, V1 commissioning fails closed; a
placeholder date is forbidden.

Supplier procurement data, price, invoice, accounting values, storage
location, packaging workflow and intended SEMINA are not part of V1 input.

## 6. FROZEN QUANTITY MODEL

### 6.1 Unambiguous decision

V1 uses model **A: `quantita_residua` is the authoritative mutable balance**.

This reuses the model already present in `lotti_seme` and mirrors TPO's
authoritative-current-balance plus audited mutation pattern. A separate seed
movement aggregate is not introduced in V1. Commercial
`MOVIMENTI_MAGAZZINO` is not reused because it governs sellable product, not
seed material.

### 6.2 Invariants

All values use exact `numeric(20,6)` decimal arithmetic. Float and scientific
notation are forbidden.

```text
UOM = GRAM
quantita_iniziale > 0
0 <= quantita_residua <= quantita_iniziale
quantita_consumata = quantita_iniziale - quantita_residua
```

At commissioning:

```text
quantita_residua = quantita_iniziale
quantita_consumata = 0
version = 0
```

`quantita_consumata` is derived and is not a stored mutable balance in V1.

### 6.3 Future SEMINA consumption

The future SEMINA command must:

1. resolve and lock the seed lot row;
2. verify immutable identity and SEMENTE compatibility through
   `SEMENTE_IMPIEGO`;
3. verify the lot is not expired for the authorized business date unless a
   later explicit exception authority is frozen;
4. reject a blocking anomaly under the future Semina contract;
5. require exact positive seed grams;
6. require `quantita_residua >= requested_grams`;
7. create SEMINA and decrement the balance in one transaction;
8. update `version` by optimistic CAS;
9. append audit for the balance transition.

Insufficient or exhausted quantity fails closed. It does not partially consume,
select another lot, create a partial SEMINA, make the balance negative, or
silently adjust requested grams.

Concurrent consumers serialize on the seed lot row and additionally validate
the expected `version` and residual balance. A concurrency loser rolls back and
may retry the complete command using the same idempotency authority. A retry
never performs a second consumption for an already committed SEMINA.

## 7. FROZEN COMMISSIONING COMMAND

Conceptual signature:

```text
CommissionSeedLot(
    seed_supplier: NormalizedText,
    seed_commercial_reference: NormalizedText,
    manufacturer_lot_number: NormalizedText,
    received_date: LocalBusinessDate,
    expiry_date: LocalBusinessDate | None,
    initial_quantity: ExactDecimal,
    unit: GRAM,
    anomaly: NormalizedText | None,
    provenance: SeedLotProvenance,
    authority: SeedLotCommissioningAuthority(
        actor: ActorId,
        reason: NormalizedText,
        correlation_id: NormalizedText,
        idempotency_key: NormalizedText,
    ),
) -> CommissionSeedLotResult
```

`SeedLotProvenance` classifies every supplied fact as one of:

- `OWNER_AUTHORIZED`;
- `LABEL_OR_PACKAGE`;
- `IMPORTED`;
- `UNKNOWN` only for fields whose contract permits NULL.

Mixed sources are represented as a canonical per-field provenance map inside
the audit payload; they are not flattened into a false single source.

Result:

```text
CommissionSeedLotResult(
    seed_lot_id: LottoSemeId,
    outcome: INSERTED | COMPATIBLE_REPLAY,
    seed_authority: supplier + commercial reference,
    manufacturer_lot_number,
    initial_quantity,
    residual_quantity,
    unit,
    received_date,
    expiry_date,
    recorded_at,
)
```

Frozen failures:

| Code | Meaning |
|---|---|
| `SEED_LOT_INPUT_INVALID` | malformed/missing input or false precision |
| `SEED_AUTHORITY_NOT_FOUND` | SEMENTE does not exist |
| `SEED_AUTHORITY_INACTIVE` | SEMENTE is not active |
| `SEED_AUTHORITY_AMBIGUOUS` | authoritative lookup is not singular |
| `SEED_LOT_INCOMPATIBLE` | references/facts violate existing authority |
| `SEED_LOT_QUANTITY_INVALID` | nonpositive, non-GRAM or inexact quantity |
| `SEED_LOT_DUPLICATE` | same business lot under another request authority |
| `SEED_LOT_IDEMPOTENCY_CONFLICT` | same token, different canonical payload |
| `SEED_LOT_CONCURRENCY_CONFLICT` | lock/version/uniqueness race lost |
| `SEED_LOT_IDENTITY_UNAVAILABLE` | missing/incompatible Identity registration |
| `SEED_LOT_COMMIT_ROLLED_BACK` | persistence failed with certain rollback |
| `SEED_LOT_RECONCILIATION_REQUIRED` | commit outcome is uncertain |
| `SEED_LOT_INTERNAL_ERROR` | unexpected internal failure, no details leaked |

Infrastructure constraint errors are translated into these application errors;
raw PostgreSQL errors never define the public contract.

## 8. FROZEN IDEMPOTENCY

The required caller-supplied `idempotency_key` is opaque normalized non-empty
text. Its scope is globally unique within operation
`SEED_LOT_COMMISSIONING_V1`.

The canonical payload includes every authoritative domain input and its
per-field provenance. It excludes `actor`, `reason`, `correlation_id`,
`recorded_at`, allocated `LSE-*`, internal PK and database version. Encoding
uses the repository's framed canonical-record convention and SHA-256 lowercase
hexadecimal.

The future physical schema must persist, under a definitive unique constraint:

- operation scope;
- idempotency key;
- canonical payload hash;
- resulting `LSE-*`;
- committed outcome;
- system `recorded_at`.

Frozen behavior:

- same key + same canonical payload → `COMPATIBLE_REPLAY`, same `LSE-*`, no
  second insert, sequence allocation, quantity change, or audit INSERT;
- same key + different payload → `SEED_LOT_IDEMPOTENCY_CONFLICT`;
- same business identity under a different key → `SEED_LOT_DUPLICATE`;
- retry after a lost response reconciles the persisted request and returns the
  committed result;
- an uncertain commit returns `SEED_LOT_RECONCILIATION_REQUIRED`; blind retry
  without reconciliation is forbidden;
- no idempotency record survives a rolled-back command.

`correlation_id`, audit search, a pre-check, `ON CONFLICT DO NOTHING`, or the
manufacturer lot number alone is not the idempotency authority.

## 9. FROZEN AUDIT / PROVENANCE

The existing `tpo.audit_eventi` authority is reused. No parallel audit system is
introduced.

The successful transaction appends exactly one commissioning audit event:

| Audit field | Frozen value |
|---|---|
| `entity_type` | `LOTTO_SEME` |
| `entity_public_id` | allocated `LSE-*` |
| `operation` | `INSERT` |
| `actor` | command actor |
| `reason` | command reason |
| `correlation_id` | command correlation ID |
| `occurred_at` | database/system recorded timestamp |
| `before_data` | NULL |
| `after_data` | canonical authoritative created values |
| `provenance` | `seed-lot-commissioning-v1` plus canonical source map |

`after_data` includes public seed lot ID, authoritative SEMENTE business
identity, manufacturer lot, dates, initial/residual quantity, UOM, anomaly,
idempotency key and payload hash. It does not expose internal PKs or secrets.

Owner-authorized facts, label/package facts, imported facts and unknown optional
facts remain distinguishable. `created_by`/`updated_by` on `lotti_seme` mirror
the actor but do not replace `audit_eventi`.

## 10. FROZEN TRANSACTION / CONCURRENCY

One PostgreSQL transaction contains all of:

1. idempotency reconciliation/lock;
2. authoritative SEMENTE lookup and active-state check;
3. business-duplicate check;
4. `LOTTO_SEME_ID` row lock and identity allocation;
5. `lotti_seme` insert with `public_id`;
6. idempotency result persistence;
7. audit INSERT;
8. Identity counter advance;
9. commit.

```text
SUCCESS = all facts committed and visible.
FAILURE = no new lot, counter advance, request record or audit is visible.
```

The minimum concurrency controls are:

- definitive unique public ID;
- definitive unique `(semente_id, numero_lotto_produttore)`;
- definitive unique `(operation_scope, idempotency_key)`;
- row lock/CAS on `LOTTO_SEME_ID`;
- expected `version` plus row lock/CAS for future consumption;
- uniqueness-race reconciliation against committed authoritative data.

No distributed lock, advisory lock, external queue or automatic unbounded retry
is introduced. Serialization/deadlock failures are bounded infrastructure
failures; the caller receives a concurrency result and may perform an explicit
retry with the same idempotency key.

## 11. FROZEN CORRECTION POLICY

Direct SQL correction and generic repository mutation are forbidden.

| Field | Policy |
|---|---|
| `LSE-*` / internal identity | permanently immutable |
| SEMENTE reference | constitutive, immutable; wrong reference requires a new correctly commissioned lot and explicit disposition of the erroneous one |
| manufacturer lot number | constitutive, immutable under V1; same disposition rule |
| commissioning/idempotency key and payload hash | immutable |
| UOM | immutable and always GRAM |
| initial quantity | no direct rewrite; future quantity-correction command only |
| residual quantity | quantity operations only |
| received date | future audited correction command only |
| expiry date | future audited correction command only |
| anomaly | future audited correction/state command only |
| created/audit facts | append-only |

The correction boundary is **DEFERRED**. Until it is frozen and implemented,
incorrect non-replay data fails closed and must not be patched. A future
quantity correction must preserve consumed quantity, prevent residual quantity
from becoming negative or exceeding corrected initial quantity, use optimistic
concurrency, and append before/after audit.

## 12. FROZEN CLI CONTRACT

The future thin adapter is:

```text
tpo seed-lot commission
  --seed-supplier <text>
  --seed-commercial-reference <text>
  --manufacturer-lot-number <text>
  --received-date <YYYY-MM-DD>
  [--expiry-date <YYYY-MM-DD>]
  --initial-quantity <decimal>
  --unit GRAM
  [--anomaly <text>]
  --provenance <canonical-source-map>
  --actor <ActorId>
  --reason <text>
  --correlation-id <text>
  --idempotency-key <text>
  --confirm
```

The CLI parses syntax, constructs typed values, builds the command, invokes one
application service method and renders the result. It performs no lookup,
normalization policy, quantity calculation, identity allocation, idempotency
decision, transaction, or business validation.

Success output:

```text
STATUS: INSERTED | COMPATIBLE_REPLAY
ENTITY: LOTTO_SEME
PUBLIC_ID: LSE-000001
SEED: <supplier> / <commercial reference>
MANUFACTURER_LOT: <value>
INITIAL_QUANTITY: <decimal> GRAM
RESIDUAL_QUANTITY: <decimal> GRAM
```

Known failure output begins with:

```text
SEED_LOT_COMMISSIONING_FAILED: <stable-code>: <safe-message>
```

Exit codes reuse `OperationalExitCode`:

| Exit | Meaning |
|---:|---|
| 0 | committed or compatible replay |
| 1 | known operation/domain/conflict failure |
| 2 | CLI input invalid |
| 3 | runtime/database unavailable before outcome uncertainty |
| 4 | reconciliation required |
| 5 | unexpected internal error |

No credentials, SQL, internal PK, traceback or raw database error is printed.

## 13. FROZEN TRACEABILITY GUARANTEE

`LOTTO_SEME` keeps one permanent `LSE-*` and can be referenced stably by one or
more `SEM-*`. It never acquires SEMINA lifecycle or production-group semantics.

The future complete chain is:

```text
RIGA_CONSEGNA
→ provenance RAC-*
→ RACCOLTA.semina_id
→ SEMINA SEM-*
→ SEMINA.protocollo_versione_id / PV-*
→ SEMINA.lotto_seme_id / LSE-*
→ LOTTO_SEME.semente_id
```

No `LOTTO_PRODUZIONE` or other production identity is required. `SEM-*` remains
the permanent physical production-group identity; `RAC-*` remains a harvest
event; `LSE-*` remains seed-material identity.

The Seed Lot boundary guarantees only the last authority in this chain. It does
not claim that the currently absent delivery-provenance boundary is already
implemented.

## 14. REQUIRED IMPLEMENTATION COMPONENTS

Probable components, following current repository layout:

| Layer | Required component |
|---|---|
| domain | add `LottoSemeId` to `src/tpo_core/domain/identifiers.py` |
| domain | seed-lot value/entity model under `src/tpo_core/domain/entities/` |
| application | `src/tpo_core/application/seed_lot_commissioning/models.py` |
| application | `src/tpo_core/application/seed_lot_commissioning/errors.py` |
| application | service and ports under the same package |
| infrastructure | `src/tpo_core/infrastructure/postgresql/seed_lot_commissioning.py` |
| bootstrap | builder exported from `src/tpo_core/bootstrap/` |
| CLI | thin `src/tpo_core/cli/seed_lot.py` and parser wiring in `cli/main.py` |
| schema | future Alembic revision for public ID, idempotency authority and constraints |
| Identity | future commissioning of `LOTTO_SEME_ID` through the existing boundary |
| tests | domain/application/CLI tests plus real PostgreSQL atomicity, race, replay and rollback tests |
| docs | update physical schema documentation only with the implementation migration |

This list is not implementation authorization.

## 15. ACCEPTANCE CRITERIA

The future implementation is accepted only if every statement is true:

1. `LottoSemeId` accepts only `LSE-` plus at least six positive digits.
2. `LOTTO_SEME_ID` is commissioned through the existing Identity boundary.
3. No command or CLI accepts an internal bigint identifier.
4. SEMENTE resolution is unique, authoritative and active.
5. Manufacturer lot number is normalized non-empty text.
6. Unknown reception date is rejected; no placeholder timestamp/date is used.
7. Unknown expiry and anomaly remain NULL.
8. Quantity is exact positive `numeric(20,6)` GRAM.
9. Initial and residual quantities are equal on insert.
10. Public ID, business identity and idempotency scope have definitive unique constraints.
11. Same key and payload returns the original `LSE-*` without writes.
12. Same key with a different payload fails closed.
13. Same business lot under a different key fails as duplicate.
14. Identity allocation, lot, request result and audit commit atomically.
15. Any pre-commit failure leaves no partial state and no counter advance.
16. Uncertain commit returns reconciliation-required, not a guessed outcome.
17. Concurrent commissioning creates at most one authoritative lot.
18. Future concurrent consumption cannot make residual quantity negative.
19. Audit contains actor, reason, correlation, recorded timestamp, canonical values and per-field provenance.
20. No commercial `MOVIMENTO_MAGAZZINO` is created.
21. No SEMINA, RACCOLTA, STOCK, order, plan or Planning revision is created or changed.
22. CLI contains no business or persistence rule.
23. Unit, application, CLI and real PostgreSQL integration tests pass.
24. Repository formatting/tests and `git diff --check` pass.

## 16. DEFERRED ITEMS

The following remain outside this boundary:

- SEMINA creation implementation;
- SEMINA lifecycle and transition events;
- existing physical production commissioning;
- useful-production authority revision;
- experimental-production authority;
- READY state and physical readiness commissioning;
- harvest and RACCOLTA writer;
- STOCK and commercial `MOVIMENTI_MAGAZZINO`;
- delivery-to-harvest provenance;
- post-readiness useful life;
- Production Planning execution or revision;
- seed procurement and supplier workflow;
- accounting, invoices and prices;
- seed-lot correction command;
- seed-consumption event aggregate beyond the V1 authoritative residual balance.

## 17. NEXT MISSION

Exactly one next mission is authorized for future owner initiation:

```text
IMPLEMENT SEED LOT COMMISSIONING BOUNDARY V1
```

It is not executed by this freeze.
