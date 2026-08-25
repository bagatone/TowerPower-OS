# SEMINA LIFECYCLE EVENT AUTHORITY V1

**Status:** ARCHITECTURE FROZEN — owner review pending
**Milestone:** 5 — Physical Production Execution
**Sprint:** 5.11 — Production Lifecycle
**Scope:** governed physical lifecycle transitions after SEMINA commissioning

This document is normative. It incrementally freezes the V1 authority required
to transition an existing `SEM-*` after commissioning. Existing SEMINA, Seed
Lot, Production Planning, audit and Identity contracts remain authoritative
where this document does not explicitly refine them.

## 1. Frozen scope

V1 records an exact, owner-authorized physical transition of one existing
SEMINA. Physical observation is authoritative. Protocol timing is predictive
only and cannot execute, synthesize or backfill a transition.

The governed path is:

```text
authorized caller
→ thin `tpo semina transition` CLI
→ TransitionSemina command
→ SeminaLifecycleService
→ PostgreSQLSeminaLifecycleWriter
→ one PostgreSQL transaction
   ├── reserve lifecycle idempotency authority
   ├── lock and validate SEMINA
   ├── append immutable lifecycle event
   ├── advance current SEMINA state/version
   ├── append correlated audit
   └── commit once
```

V1 does not commission a new SEMINA, import historical production, create a
RACCOLTA, mutate STOCK, satisfy a delivery, create a Production Planning
revision or commission predictive useful authority.

## 2. Frozen identity boundary

`SEM-*` remains the permanent externally traceable identity of the physical
production group throughout its lifecycle and after closure. A lifecycle
transition does not create another SEMINA or a `LOTTO_PRODUZIONE`.

Lifecycle events use an immutable internal database identity. V1 introduces no
public event ID, prefix, PermanentId type or Identity sequence. A public event
identity requires a later external-referencing Architecture Review and Freeze.

## 3. Frozen state vocabulary

The complete V1 `SeminaState` vocabulary remains:

```text
AVVIATA
GERMINAZIONE
LUCE
CRESCITA
PRONTA_ALLA_RACCOLTA
CHIUSA
```

There are no aliases, warning states, discarded states or additional terminal
states. `CHIUSA` is the only terminal state. Discard and interruption are final
outcomes, not states.

## 4. Frozen transition graph

Only these ordinary active-state transitions are valid:

```text
AVVIATA → GERMINAZIONE
GERMINAZIONE → LUCE
LUCE → CRESCITA
CRESCITA → PRONTA_ALLA_RACCOLTA
```

Every active state may also transition directly to `CHIUSA`:

```text
AVVIATA → CHIUSA
GERMINAZIONE → CHIUSA
LUCE → CHIUSA
CRESCITA → CHIUSA
PRONTA_ALLA_RACCOLTA → CHIUSA
```

V1 forbids every skipped active phase, backward transition, transition out of
`CHIUSA`, same-state transition and state outside the frozen vocabulary.
Protocol duration, including zero duration, does not authorize a skipped state.
A future physically omitted phase requires a dedicated protocol/lifecycle
Architecture Review and Freeze. Missing intermediate events are never
synthesized.

## 5. Frozen READY semantics

`PRONTA_ALLA_RACCOLTA` means only that the living physical production group has
been owner-authorized as physically ready for harvest.

It does not mean or create a RACCOLTA, harvested quantity, commercial
allocation or guarantee, STOCK availability, delivery readiness, delivery
fulfilment, commissioned useful quantity or Production Planning revision. READY
creates no downstream authority. Harvest and commercial availability remain
separate future governed boundaries.

## 6. Frozen closure and final outcome

Target `CHIUSA` requires exactly one `esito_finale` from the existing closed
vocabulary:

```text
RACCOLTA_COMPLETA
RACCOLTA_PARZIALE_CON_SCARTO
SCARTO_TOTALE
INTERRUZIONE
```

Every active target forbids `esito_finale`. The application/domain mapping must
preserve parity with the existing semantic labels `raccolta completa`,
`raccolta parziale con scarto`, `scarto totale` and `interruzione`.

Closure means no active productive quantity remains attributable to the cycle.
It may occur from any active state and does not require a RACCOLTA. Sprint 5.11
does not invent a harvest balance or modify Harvest authority.

## 7. Frozen command contract

The canonical application command is:

```text
TransitionSemina(
    semina_public_id: SeminaId,
    expected_semina_version: NonNegativeInteger,
    target_state: SeminaState,
    effective_at: AwareInstant,
    final_outcome: SeminaFinalOutcome | None,
    provenance: SeminaLifecycleProvenance,
    authority: SeminaLifecycleAuthority,
)

SeminaLifecycleAuthority(
    actor: ActorId,
    reason: NormalizedText,
    correlation_id: NormalizedText,
    idempotency_key: NormalizedText,
)
```

Current/from state is derived from the locked SEMINA and is never caller input.

| Field | Classification | Authority | Canonical payload? |
|---|---|---|---|
| SEM public ID | REQUIRED | existing SEMINA | YES |
| expected SEM version | REQUIRED | observed CAS epoch | YES |
| target state | REQUIRED | physical observation | YES |
| `effective_at` | REQUIRED | owner-authorized physical fact | YES |
| final outcome | CONDITIONAL: `CHIUSA` | frozen vocabulary | YES |
| structured provenance | REQUIRED | physical fact authority | YES |
| actor | REQUIRED | execution context | NO |
| reason | REQUIRED | execution context | NO |
| correlation ID | REQUIRED | execution context | NO |
| idempotency key | REQUIRED | request authority | key, not payload |
| current/from state | DERIVED | locked SEMINA | NO |
| `recorded_at` | DERIVED | persistence clock | NO |
| resulting SEM version | DERIVED | CAS update | NO |
| event internal ID | DERIVED | persistence | NO |

V1 does not require quantity, quality grade, physical location, notes, harvest
quantity or commercial availability. Optional notes cannot replace structured
authority or affect transition validity.

## 8. Frozen physical evidence and provenance

Every command carries a closed structured provenance map covering exactly:

```text
target_state
effective_at
final_outcome  # present exactly when target_state is CHIUSA
```

The implementation reuses an authoritative provenance-source vocabulary where
semantically compatible. Unknown, missing, duplicate, extra or free-text-as-
authority provenance fails closed. Canonically sorted provenance records enter
the material payload. Actor, reason and correlation identify execution/audit
context; they do not replace physical provenance or material idempotency.

## 9. Frozen timestamp semantics

V1 stores exactly two authoritative instants:

- `effective_at`: exact owner-authorized physical instant when the transition
  became true;
- `recorded_at`: current system persistence timestamp.

Both are timezone-aware. Operational interpretation/display remains
`Atlantic/Canary`; canonical UTC storage must preserve the supplied instant.
V1 does not introduce mandatory `observed_at`.

A transition may be recorded after physical occurrence only with an exact,
owner-authorized `effective_at`. Every transition requires:

```text
effective_at >= semina.data_avvio
```

When a previous lifecycle event exists, it also requires:

```text
effective_at > latest_lifecycle_effective_at
```

Chronology is strictly monotonic. Equal timestamps and regressions fail closed.
Neither protocol timing nor `recorded_at` substitutes an unknown physical time.

## 10. Frozen append-only event authority

A dedicated table, conventionally `semina_lifecycle_eventi`, is required. Each
successful non-replay transition appends exactly one immutable row containing:

- internal event identity;
- SEM internal FK and public-ID reference/snapshot;
- previous and resulting states;
- conditional final outcome;
- `effective_at` and `recorded_at`;
- actor, reason and correlation ID;
- canonical structured provenance;
- Semina version before and after;
- authoritative lifecycle-request reference.

Event update and delete are prohibited. Constraints enforce state/outcome
pairing, version adjacency and nonblank context. The writer, under SEMINA lock,
enforces graph and strict chronology.

Current state remains in `semine.stato`; append-only events prove how it was
reached. Both advance atomically and must never diverge.

## 11. Frozen idempotency authority

A dedicated persistent authority, conventionally
`semina_lifecycle_transition_requests`, is required and must not reuse
`semina_commissioning_requests`.

It persists operation scope `SEMINA_LIFECYCLE_TRANSITION_V1`, nonblank key,
lowercase SHA-256 canonical payload hash, `RESERVED`/`COMMITTED` outcome,
nullable result while reserved and mandatory result when committed, recorded
timestamp and created actor. `(operation_scope, idempotency_key)` is unique.
The authority is immutable except for `RESERVED → COMMITTED`; delete is
prohibited.

The ordered framed UTF-8 material payload contains:

```text
SEMINA-LIFECYCLE-TRANSITION-V1
SEM public ID
expected SEM version
target state
effective_at canonical UTC form
final outcome or NULL
structured provenance canonical records
```

Event ID, derived from state, resulting version, generated timestamps, actor,
reason and correlation ID are excluded.

Semantics:

- same key + same payload: compatible replay, without duplicate event, audit or
  version bump;
- same key + different payload: typed idempotency conflict;
- different key + already physically applied transition: evaluate locked
  current state and fail closed as invalid/already applied, without event and
  without silently replaying another request.

## 12. Frozen optimistic concurrency

The writer locks SEMINA and requires exact equality with
`expected_semina_version`. Success increments the version exactly once:

```text
version_after = version_before + 1
```

Two commands from the same version cannot both commit. Different targets,
closure-versus-forward races and already-applied transitions are resolved from
the locked state. There is no silent last-write-wins or retry loop hiding an
application conflict.

## 13. Frozen transaction and lock order

One writer owns the transaction in this normative order:

1. reserve or lock lifecycle idempotency authority;
2. resolve and lock SEMINA by internal PK/public ID;
3. verify expected version;
4. derive current state and latest lifecycle event;
5. validate terminal state, edge and final outcome;
6. validate aware timestamp, start bound and strict chronology;
7. validate provenance and material payload;
8. append immutable lifecycle event with version before/after;
9. update SEMINA state, conditional outcome, audit metadata and version by CAS;
10. append one correlated `audit_eventi` record;
11. complete idempotency authority with authoritative result;
12. force deferred constraints and commit once.

Every certain failure rolls back reservation, event, SEMINA update and audit.
Uncertain commit requires reconciliation and must not be blindly retried under
another key.

## 14. Frozen audit contract

Reuse shared `audit_eventi`; do not introduce parallel audit. Each successful
non-replay transition appends one `SEMINA / STATE_TRANSITION` record. Before and
after payloads include states, conditional final outcome, effective instant and
versions. Audit and lifecycle event share actor, reason, correlation,
provenance and one `recorded_at`.

Audit is evidence, not lifecycle/current-state authority. Compatible replay
creates no duplicate audit; rollback leaves no orphan audit.

## 15. Frozen protocol interaction

Protocol hydration, germination, light/growth, nominal-cycle and harvest timing
may suggest, validate or warn. They cannot execute a transition, authorize a
skip, invent `effective_at`, synthesize an event, prove READY or close a SEMINA.

A future scheduler or briefing may expose due/overdue transitions read-only.
Automatic physical-state mutation requires another Architecture Review and
Freeze.

## 16. Planning and predictive-authority isolation

Lifecycle does not invoke, create, replace or revise Production Planning. It
does not populate or modify:

- `expected_useful_quantity`;
- `expected_useful_uom`;
- `harvest_window_start`;
- `harvest_window_end`.

Predictive useful authority remains separate. Active-state change does not
manufacture resource eligibility. `CHIUSA` may be observed by a later Planning
read, but transition itself does not run or mutate Planning.

## 17. Frozen result contract

A committed or compatible-replay result exposes:

```text
semina_public_id
previous_state
resulting_state
final_outcome or NULL
effective_at
recorded_at
version_before
version_after
outcome = INSERTED | COMPATIBLE_REPLAY
```

Internal event/request identities are not public business identities.

## 18. Frozen typed errors

The boundary exposes sanitized typed failures at minimum for:

- `SEMINA_NOT_FOUND`;
- `SEMINA_VERSION_CONFLICT`;
- `SEMINA_TRANSITION_INVALID`;
- `SEMINA_ALREADY_CLOSED`;
- `SEMINA_LIFECYCLE_IDEMPOTENCY_CONFLICT`;
- `SEMINA_LIFECYCLE_TIMESTAMP_INVALID`;
- `SEMINA_LIFECYCLE_TIMESTAMP_REGRESSION`;
- `SEMINA_LIFECYCLE_PROVENANCE_INVALID`;
- `SEMINA_FINAL_OUTCOME_REQUIRED`;
- `SEMINA_FINAL_OUTCOME_FORBIDDEN`;
- `SEMINA_LIFECYCLE_COMMIT_ROLLED_BACK`;
- `SEMINA_LIFECYCLE_COMMIT_OUTCOME_UNCERTAIN`;
- `SEMINA_LIFECYCLE_RECONCILIATION_REQUIRED`.

A different-key already-applied request uses the canonical invalid/already-
closed error appropriate to locked current state and is never compatible
replay. Provider/SQL details do not cross the boundary.

## 19. Frozen CLI boundary

The sole V1 command is:

```text
tpo semina transition \
  --semina SEM-000001 \
  --expected-semina-version 0 \
  --target-state GERMINAZIONE \
  --effective-at 2026-08-25T09:00:00+01:00 \
  --provenance '<canonical JSON object>' \
  --actor <actor> \
  --reason <reason> \
  --correlation-id <correlation> \
  --idempotency-key <key> \
  --confirm
```

`--final-outcome` is required exactly for `CHIUSA` and forbidden otherwise.
CLI only parses, constructs, invokes and renders sanitized outcomes. It performs
no SQL, inference, retry or business decision. Convenience commands such as
`to-light`, `ready` or `close` are not introduced.

## 20. Required implementation components

Only a later owner-authorized implementation may add:

1. lifecycle command, result, provenance, errors, service and writer port;
2. domain transition validation consistent with this graph;
3. dedicated PostgreSQL lifecycle writer;
4. migration for append-only events and persistent lifecycle requests;
5. minimal SEMINA mutable audit columns only if existing schema conventions
   require them;
6. bootstrap builder and thin CLI;
7. domain, application, CLI, architecture, migration and PostgreSQL integration
   tests.

No Identity commissioning is required for lifecycle events.

## 21. Acceptance criteria

Implementation is accepted only if tests prove:

1. exact state vocabulary and no aliases;
2. all four ordinary edges succeed;
3. closure succeeds from every active state;
4. skips, backward, same-state and post-closure transitions fail;
5. zero protocol duration cannot authorize a skip;
6. `CHIUSA` requires one frozen outcome and active targets forbid it;
7. READY creates no downstream authority;
8. exact aware `effective_at` is required;
9. time before `data_avvio`, equal time and regression fail;
10. valid backdated recording preserves distinct effective/recorded times;
11. from state is derived under lock;
12. stale version fails without partial writes;
13. success appends one immutable event and increments version once;
14. event update/delete protection is enforced;
15. same key/same payload replays without duplicate effects;
16. same key/different payload conflicts;
17. different key/already-applied transition fails without duplication;
18. concurrent same-version and close/forward races remain consistent;
19. audit is complete, correlated and absent after rollback/replay;
20. uncertain commit returns reconciliation required;
21. lifecycle does not mutate predictive quartet or Planning;
22. lifecycle creates no RACCOLTA, STOCK, delivery or Identity records;
23. CLI is thin and sanitized;
24. migration remains single-head and downgrade is safe or blocked when history
    makes reversal unsafe;
25. full regression remains green.

## 22. Deferred boundaries

Explicitly deferred:

- Experimental Production Authority. Sprint 5.11 does not classify a SEMINA as
  experimental or commercial, introduce experimental eligibility, promote
  experimental production to commercial production, or change the Sprint 5.10
  exclusion of experimental authority. Experimental Production Authority
  remains assigned to its dedicated future boundary and Sprint;
- existing physical production commissioning and incomplete historical
  reconstruction (Sprint 5.12);
- predictive useful authority and correction;
- Harvest/RACCOLTA, STOCK and commercial availability;
- delivery provenance;
- measurements, quality, location, notes and problem registers;
- protocol-specific omitted phases;
- public lifecycle-event identity;
- automatic protocol-driven mutation;
- labels/QR;
- Production Planning invocation or revision.

## 23. Next mission

`IMPLEMENT SPRINT 5.11 — SEMINA LIFECYCLE EVENT AUTHORITY V1`
