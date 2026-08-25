# SEMINA COMMISSIONING BOUNDARY V1

**Status:** ARCHITECTURE FROZEN — owner review pending
**Milestone:** 5 — Physical Production Execution
**Sprint:** 5.10 — Physical Production / Semina Commissioning
**Scope:** commissioning of a new, physically observed production cycle

This document is normative. It incrementally freezes only the boundary needed
to commission a new SEMINA. Existing `SEMINE`, Production Planning and Seed Lot
contracts remain authoritative where this document does not explicitly refine
them.

## 1. Frozen scope

V1 commissions only a **new physical start observed exactly when the production
cycle is started**. It creates one permanent production-group authority and,
when applicable, records the Planning execution that caused it.

V1 forbids approximate or guessed start instants, already-progressed historical
production, READY crops predating TPO execution and reconstruction of incomplete
history. Those belong to Sprint 5.12. Commissioning does not advance lifecycle,
record harvest, create stock, modify delivery provenance or create a new
Production Planning revision.

## 2. Frozen SEM identity and constitutive boundary

`SEM-*` is the permanent identity of one homogeneous physical production group.

| Property | Frozen value |
|---|---|
| type | `SeminaId` |
| prefix | `SEM` |
| format | `SEM-[0-9]{6,}` with positive numeric component |
| Identity sequence | `SEMINA_ID` |
| first allocatable value | `SEM-000001` |

`SeminaId.sequence_name` shall be `SEMINA_ID`. Identity is allocated only by the
governed persistent Identity authority and is never supplied by an operator.

The constitutive facts of one SEMINA are its SEM identity, exact physical start,
cultivar, productive use, one LSE, one protocol version and actual seed grams.
Its identity never changes across `GERMINAZIONE`, `LUCE`, `CRESCITA`,
`PRONTA_ALLA_RACCOLTA`, partial harvests or closure. Lifecycle events do not
create another SEM. A harvest receives its own future `RAC-*`.

Shared LSE, protocol, timestamp or quantity do not prove that two physical
starts are the same group. No composite business uniqueness constraint is
introduced. There is no `LOTTO_PRODUZIONE`.

## 3. Frozen command contract

The application command is named `CommissionSemina`:

```text
CommissionSemina(
    seed_lot_public_id: LottoSemeId,
    expected_seed_lot_version: NonNegativeInteger,
    protocol_version_public_id: ProtocolVersionPublicId,
    actual_seed_quantity: ExactQuantity[GRAM],
    physical_started_at: AwareInstant,
    origin: SeminaOrigin,
    planning_start: PlannedSeminaStart | None,
    provenance: SeminaCommissioningProvenance,
    authority: SeminaCommissioningAuthority,
)

PlannedSeminaStart(
    planning_line_public_id: RigaPianoSeminaId,
    expected_planning_line_version: NonNegativeInteger,
    started_quantity: ExactQuantity[SET],
)

SeminaCommissioningAuthority(
    actor: ActorId,
    reason: NormalizedText,
    correlation_id: NormalizedText,
    idempotency_key: NormalizedText,
)
```

| Field | Classification | Authority | Canonical payload? |
|---|---|---|---|
| LSE public ID | REQUIRED | commissioned Seed Lot | YES |
| expected LSE version | REQUIRED | observed CAS epoch | YES |
| PV public ID | REQUIRED | approved Protocol Version | YES |
| actual seed quantity | REQUIRED | physical observation | YES |
| physical start instant | REQUIRED | physical observation | YES |
| origin | REQUIRED | frozen origin vocabulary | YES |
| actor | REQUIRED | execution context | NO |
| reason | REQUIRED | execution context | NO |
| correlation ID | REQUIRED | execution context | NO |
| idempotency key | REQUIRED | request authority | key, not payload |
| structured provenance | REQUIRED | physical fact authority | YES |
| RPS public ID | CONDITIONAL: planned | current Planning line | YES |
| expected RPS version | CONDITIONAL: planned | observed CAS epoch | YES |
| started quantity | CONDITIONAL: planned | operator-observed execution | YES |
| SEM public ID | DERIVED | `SEMINA_ID` | NO |
| initial state | DERIVED | this Freeze | NO; always `AVVIATA` |
| seed UOM | DERIVED | this Freeze | NO; always `GRAM` |
| variety/cultivar/use | DERIVED | PV authority graph | NO |
| historical snapshots | DERIVED | locked authorities | NO |
| Planning-link UOM | DERIVED | Planning contract | NO; always `SET` |
| final outcome | FORBIDDEN | lifecycle | NO |
| state beyond `AVVIATA` | FORBIDDEN | Sprint 5.11 | NO |
| operator-supplied SEM ID | FORBIDDEN | Identity writer | NO |
| approximate timestamp | FORBIDDEN | no authority | NO |
| predictive useful fields | FORBIDDEN at commissioning | separate future authority | NO |
| labels, QR or printer data | FORBIDDEN | Sprint 5.17 | NO |

Actor, reason and correlation identify the invocation and its audit context; they
do not change material idempotency. The persistent idempotency key addresses the
request independently.

## 4. Frozen origin contract

`SeminaOrigin` is a closed V1 vocabulary:

```text
PIANO_PRODUZIONE
ORDINE_CLIENTE
RIPRISTINO_STOCK
```

`PIANO_PRODUZIONE` requires `planning_start`. The other two origins forbid it
and represent independent creation. Free text is not accepted as origin.

`TEST` and `SPERIMENTAZIONE` are not V1 origins. Sprint 5.10 does not establish
experimental-production authority or commercial eligibility. Adding either
requires a dedicated Architecture Review and Freeze.

## 5. Frozen protocol, cultivar and use contract

The operator supplies exactly one approved `PV-*`. Variety, cultivar and
productive use are derived through the locked Protocol → cultivar-use → cultivar
→ variety authority graph. They are not redundant command inputs.

The writer verifies that:

1. PV exists, is approved and is valid for the physical start business date;
2. PV resolves exactly one cultivar/use/variety context;
3. the LSE resolves one SEMENTE;
4. that SEMENTE has an authoritative compatible `SEMENTE_IMPIEGO` for the
   derived cultivar/use under the existing recommendation policy;
5. the planned RPS, when present, has the same PV, variety, cultivar and use.

Any missing, ambiguous, inactive or disagreeing authority fails closed. The
writer persists authoritative FKs and normalized historical snapshots for
cultivar, use, LSE and PV from the locked rows. It never trusts duplicated
operator text.

## 6. Frozen LSE consumption contract

Actual seed quantity is a positive exact Decimal using PostgreSQL
`numeric(20,6)` and UOM `GRAM`. Float, scientific notation and implicit
conversion are forbidden.

Under row lock the writer must verify:

- LSE exists and its immutable identity is coherent;
- `expected_seed_lot_version` equals current `lotti_seme.version`;
- residual quantity is at least the requested grams;
- the LSE/SEMENTE is compatible with the derived productive use;
- known expiry has not passed at the official `Atlantic/Canary` business date
  containing `physical_started_at`;
- `anomalia IS NULL`.

On success:

```text
new_residual = old_residual - actual_seed_grams
new_residual >= 0
new_lse_version = old_lse_version + 1
```

The decrement and version advance use optimistic CAS in the same transaction as
SEMINA creation. Insufficient seed never partially consumes, selects another
lot, changes grams or creates a partial SEMINA.

### 6.1 Expiry and anomaly policy V1

The owner-approved anomaly policy is **`ANY ANOMALY BLOCKS`**.

- known expired LSE: **BLOCKED**;
- unknown expiry (`NULL`): **ALLOWED**;
- expiry override: **NONE**;
- any non-NULL anomaly: **BLOCKED**;
- anomaly severity, warning-only behavior and override: **NONE**.

Free-text anomaly content is not interpreted. A future severity/warning/override
model requires a dedicated Architecture Review and Freeze.

## 7. Frozen planned-start contract

For `PIANO_PRODUZIONE`, the writer locks the RPS and validates:

- public ID and expected version;
- current revision/plan authority remains current;
- state is `PRONTA` or `AVVIATA`;
- started quantity is positive `SET`;
- started quantity does not exceed `quantita_residua_da_avviare`;
- PV/variety/cultivar/use match the command-derived context.

It then creates one immutable `righe_piano_semina_semine` link. A Planning line
may have multiple partial SEMINA starts. One SEMINA may belong to at most one
RPS. The following invariants hold:

```text
quantita_avviata = SUM(link.quantita_avviata)
quantita_residua_da_avviare =
    quantita_produttiva_autorizzata - quantita_avviata
0 <= quantita_avviata <= quantita_produttiva_autorizzata
```

The first start changes `PRONTA` to `AVVIATA`. Further valid starts preserve
`AVVIATA`. `AVVIO_COMPLETATO` is derived when residual is zero and is not a new
state. Commissioning never sets `SODDISFATTA`.

`PIANIFICATA`, `SODDISFATTA`, `ANNULLATA`, `SOSTITUITA` and `TARDIVA` are not
eligible for this command. RPS version advances exactly once per successful
command.

## 8. Frozen independent-start contract

`ORDINE_CLIENTE` and `RIPRISTINO_STOCK` create a SEMINA and consume LSE without
an RPS link or Planning mutation. The command must not fabricate an RPS, a
started quantity in SET, a Planning revision or a Planning allocation.

An independently created SEMINA cannot later receive a retrospective Planning
link in V1. Any future association requires a separate explicit authority and
Freeze; it cannot be inferred from matching variety, date or demand.

## 9. Frozen quantity ownership

SEMINA owns only actual seed consumed:

```text
semine.quantita_seme: numeric(20,6), positive, GRAM
```

The planned execution link owns productive start quantity:

```text
righe_piano_semina_semine.quantita_avviata:
numeric(20,6), positive, SET
```

These are distinct authorities. The command may carry SET only inside
`PlannedSeminaStart`; it must not add or persist a generic production quantity
on SEMINA. Independent creation requires no artificial SET value.

## 10. Frozen predictive useful authority

V1 adopts **Option B**.

At initial Semina commissioning these four fields are all `NULL`:

- `expected_useful_quantity`;
- `expected_useful_uom`;
- `harvest_window_start`;
- `harvest_window_end`.

The commissioning writer does not derive them from PV, RPS, seed grams or the
calendar. Initial SEMINA is therefore not yet eligible as an in-progress
Planning resource. A separate governed predictive-resource commissioning
authority must populate all four atomically before such eligibility. Defining
that authority is outside this Sprint.

Prediction is never evidence of `PRONTA_ALLA_RACCOLTA`, harvest or physical
readiness. A future predictive correction is append-audited/versioned and cannot
rewrite the physical start facts.

## 11. Frozen domain/schema parity requirements

Sprint 5.10 implementation shall extend `Semina` only as needed to enforce this
boundary:

- typed `LottoSemeId` reference;
- typed PV public reference;
- authoritative typed cultivar/use references or one immutable context value
  that cannot disagree with derived FKs;
- explicit nullable predictive useful quantity/UOM/window quartet, enforcing
  all-null or all-populated parity even though commissioning constructs all-null;
- optimistic `version` where the application model observes mutable SEMINA.

Existing historical snapshots remain explicit immutable values. No unrelated
domain refactor is authorized.

## 12. Frozen idempotency authority

A dedicated table `semina_commissioning_requests` is required. It must not reuse
`seed_lot_commissioning_requests`.

Minimum persisted authority:

- operation scope fixed to `SEMINA_COMMISSIONING_V1`;
- nonblank idempotency key;
- lowercase SHA-256 canonical payload hash;
- `RESERVED` or `COMMITTED` outcome;
- nullable SEM FK/public ID while reserved and mandatory when committed;
- recorded timestamp and created actor;
- uniqueness on `(operation_scope,idempotency_key)` and on committed SEM result;
- immutable authority except the single `RESERVED → COMMITTED` transition;
- delete prohibited.

The material canonical payload is an ordered framed UTF-8 serialization of:

```text
SEMINA-COMMISSIONING-V1
LSE public ID
expected LSE version
PV public ID
actual seed grams canonical decimal
physical start instant canonical UTC form
origin
planning-present boolean
RPS public ID or NULL
expected RPS version or NULL
started SET quantity or NULL
structured provenance canonical records
```

SEM ID, created timestamps, persistence timestamps, generated versions, audit
IDs, actor, reason and correlation ID are excluded from the material hash.

Same key and same material payload returns the persisted SEM without new SEM
identity, seed consumption, RPS mutation, link or success audit. Same key with a
different payload is a typed idempotency conflict. Different keys with shared
physical facts are distinct commands; no unsafe duplicate inference is made.

## 13. Frozen transaction and lock ordering

One writer owns the full transaction. Its normative order is:

1. reserve or lock Semina idempotency authority;
2. resolve and lock LSE by internal PK/public ID;
3. verify LSE version, eligibility and residual;
4. resolve and lock PV/cultivar/use/variety and SEMENTE compatibility;
5. resolve and lock RPS when planned;
6. verify RPS version, state, context and residual;
7. lock `SEMINA_ID` authority;
8. allocate the next SEM identity in memory;
9. insert SEMINA with authoritative FKs and snapshots;
10. decrement LSE residual and advance LSE version by CAS;
11. insert RPS→SEMINA link when planned;
12. update RPS quantities/state/version by CAS when planned;
13. append correlated audit events;
14. complete the idempotency authority with the SEM result;
15. advance `SEMINA_ID` counter/version by CAS;
16. force deferred constraints and commit once.

Any certain failure rolls back every action, including idempotency reservation
and identity consumption. An uncertain commit outcome returns reconciliation
required and must never be blindly retried as a new command.

### 13.1 Concurrency

- same key: uniqueness serializes; compatible committed result is reused;
- same LSE, different commands: both may commit only through successive expected
  versions and sufficient residual;
- stale LSE version: fail closed;
- same RPS, different partial starts: serialize under lock/CAS and remain within
  residual;
- stale RPS version: fail closed;
- last-seed race: at most a consumption supported by the locked residual commits;
- no balance, started counter or identity may become negative or duplicated.

Lock acquisition is deterministic by aggregate class and ascending internal PK
within a class. No retry loop hides an application concurrency conflict.

## 14. Frozen audit and provenance contract

The shared `audit_eventi` authority is reused. No parallel audit system is
introduced. A successful command appends correlated events for:

1. `SEMINA` / `INSERT`, containing the new SEM and constitutive snapshots;
2. `LOTTO_SEME` / `UPDATE`, containing before/after residual and version;
3. `RIGA_PIANO_SEMINA` / `UPDATE` for planned starts, containing before/after
   quantities, state and version; the immutable link identity is represented in
   the after payload.

All events share actor, reason, correlation ID and one persistence timestamp.
Audit is evidence, not the quantitative source of truth. Compatible replay
creates no duplicate success audit.

`SeminaCommissioningProvenance` is a closed, structured field-to-source map for:

- physical start instant;
- actual seed grams;
- selected LSE;
- selected PV;
- origin;
- planned started quantity when present.

Each source uses exactly the existing authority vocabulary
`OWNER_AUTHORIZED`, `LABEL_OR_PACKAGE` or `IMPORTED`. `UNKNOWN` is forbidden
because every commissioned physical-start fact is required and known. Absence,
extra fields, free-text notes as authority, or inconsistent optional Planning
provenance fail validation. The canonical map is sorted and included in the
payload hash.

## 15. Frozen error contract

The application exposes typed, sanitized failures at minimum for:

- `SEMINA_IDENTITY_UNAVAILABLE`;
- `SEMINA_IDEMPOTENCY_CONFLICT`;
- `SEMINA_RECONCILIATION_REQUIRED`;
- `LSE_NOT_FOUND`;
- `LSE_VERSION_CONFLICT`;
- `LSE_INSUFFICIENT_SEED`;
- `LSE_INCOMPATIBLE`;
- `LSE_EXPIRED`;
- `LSE_ANOMALY_BLOCKED`;
- `PROTOCOL_NOT_FOUND_OR_UNAVAILABLE`;
- `PROTOCOL_CONTEXT_INCOMPATIBLE`;
- `PHYSICAL_START_INVALID`;
- `RPS_NOT_FOUND`;
- `RPS_VERSION_CONFLICT`;
- `RPS_STATE_INCOMPATIBLE`;
- `RPS_QUANTITY_EXCEEDED`;
- `SEMINA_COMMIT_ROLLED_BACK`;
- `SEMINA_COMMIT_OUTCOME_UNCERTAIN`.

Validation/domain failures, business conflicts, concurrency conflicts,
rollback-certain persistence failures and reconciliation-required outcomes stay
distinct. Raw SQL, credentials, internal PKs and driver details are never
exposed by CLI output.

## 16. Frozen CLI contract

The thin command is:

```text
tpo semina commission \
  --seed-lot LSE-000001 \
  --expected-seed-lot-version <n> \
  --protocol-version PV-000001 \
  --actual-seed-grams <decimal> \
  --physical-started-at <timezone-aware ISO-8601> \
  --origin <PIANO_PRODUZIONE|ORDINE_CLIENTE|RIPRISTINO_STOCK> \
  [--planning-line RPS-000001 \
   --expected-planning-line-version <n> \
   --started-quantity-set <decimal>] \
  --provenance <canonical JSON object> \
  --actor <actor> --reason <reason> \
  --correlation-id <id> --idempotency-key <key> \
  --confirm
```

The three Planning arguments are all present exactly for
`PIANO_PRODUZIONE` and all absent otherwise. CLI only parses, constructs the
command, invokes the service and renders typed outcome. It performs no SQL,
identity allocation, derivation or business decision.

## 17. Required implementation components

Only these components are authorized by this Freeze:

1. `SeminaId.sequence_name = "SEMINA_ID"`;
2. minimal `Semina` domain parity described in §11;
3. Semina commissioning commands, results, errors, service and ports;
4. dedicated PostgreSQL Semina commissioning writer;
5. migration for `semina_commissioning_requests` and only required structural
   constraints/protection;
6. bootstrap builder;
7. `tpo semina commission` CLI;
8. domain, application, CLI, architecture, migration and PostgreSQL integration
   tests;
9. explicit later operational commissioning of `SEMINA_ID` through the existing
   Identity boundary, outside implementation and only after owner approval.

The Seed Lot commissioning writer remains separate and is not extended into a
consumption writer.

## 18. Acceptance criteria

V1 is accepted only if tests prove all of the following:

1. SEM identity grammar, non-reuse and governed sequence allocation;
2. initial state always `AVVIATA`, final outcome NULL;
3. exact aware physical timestamp and positive GRAM validation;
4. PV-derived context and LSE/SEMENTE compatibility fail closed;
5. known expiry blocks, NULL expiry succeeds, any anomaly blocks;
6. insufficient seed and stale LSE version roll back completely;
7. SEM insert and exact LSE decrement/version advance are atomic;
8. planned start requires eligible `PRONTA`/`AVVIATA` RPS and matching context;
9. partial starts update exact SET counters and never exceed residual;
10. multiple SEMINE per RPS work; one SEMINA cannot link to two RPS;
11. independent start creates no link and no Planning mutation;
12. predictive quartet is all NULL after commissioning;
13. same idempotency key/payload returns the same SEM without duplicate effects;
14. same key/different payload conflicts;
15. different keys/shared physical facts are not rejected as false duplicates;
16. same-LSE and same-RPS races serialize correctly;
17. last-seed race never creates negative residual;
18. audit events are complete, correlated and absent after rollback/replay;
19. uncertain commit is reconciliation-required, not reported as rollback;
20. CLI is thin, sanitized and has no provider/business logic;
21. migration graph remains single-head and downgrade is safe or explicitly
    blocked when commissioned SEMINE make reversal unsafe;
22. full regression remains green and no Seed Lot/Planning semantics regress.

## 19. Deferred boundaries

### Sprint 5.11

- transitions after `AVVIATA`;
- `GERMINAZIONE`, `LUCE`, `CRESCITA`, `PRONTA_ALLA_RACCOLTA`, closure;
- lifecycle audit and transition concurrency.

### Sprint 5.12

- existing physical production commissioning;
- approximate or incomplete historical facts;
- already-progressed or READY production predating TPO execution.

### Future predictive-resource authority

- commissioning/correction of expected useful quantity/UOM and harvest window;
- eligibility as an in-progress Planning resource.

### Sprint 5.17

- labels, QR, rendering and printer integration.

Also excluded: Harvest/RACCOLTA implementation, STOCK, Delivery provenance,
experimental commercial eligibility, new Production Planning revisions and real
operational commissioning.

## 20. Next mission

`IMPLEMENT SPRINT 5.10 — SEMINA COMMISSIONING BOUNDARY V1`
