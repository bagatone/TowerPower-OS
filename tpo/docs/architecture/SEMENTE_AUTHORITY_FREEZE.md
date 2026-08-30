# SEMENTE AUTHORITY V1 FREEZE

## 1. PRE-FLIGHT

**Status:** OWNER-APPROVED ARCHITECTURE FREEZE
**Scope:** Semente commissioning boundary (creation authority only)
**Prior-art gate:** PRIOR ART REVIEW PASSED

This freeze was prepared against the following verified baseline:

| Authority | Frozen baseline |
|---|---|
| repository | `/Users/bagatone/Documents/Codex/2026-06-28/a/work/towerpower-website/tpo` |
| writable | `YES` |
| branch | `sprint-4.4-production-planning` |
| HEAD | `84f7f00` (`Implement Raccolta Authority V1`) |
| working tree before this document | clean |
| repository Alembic head | `20260830_0022` |
| live Alembic head | NOT CHECKED — this is an architecture-only task; no database connection was made |

This document does not authorize a migration, identity registration, commissioning
operation, database write, commit, or push. It governs architecture only.

## 2. Prior-art gate result

Repository-wide search across `docs/`, `docs/architecture/`, `config/`, `data/`,
`scripts/`, `src/`, `tests/`, `migrations/` and legacy fixtures found:

- no `SementeId` domain type and no `SEMENTE_ID` sequence anywhere in the
  repository;
- no `FornitoreId` or `class Fornitore` supplier-master entity;
- no existing `semente_commissioning` application package;
- an existing, unmigrated table pair `tpo.sementi` / `tpo.semente_impieghi`
  (migration `20260810_0003_production_knowledge_prerequisites.py`), with a
  definitive unique index
  `uq_sementi_fornitore_referenza_normalized` on
  `(lower(btrim(fornitore)), lower(btrim(referenza_commerciale)))`;
- one inconsistency in `docs/architecture/AUTHORITY_REGISTRY.yaml`: the
  `SEMENTE` concept entry lists `identities: [{type: ProtocolloVersioneId,
  prefix: PV, sequence: PROTOCOLLO_VERSIONE_ID}]`. Source evidence
  (`src/tpo_core/domain/identifiers.py`,
  `src/tpo_core/application/agronomic_commissioning/models.py`,
  `src/tpo_core/domain/entities/semina.py`) shows `ProtocolloVersioneId` /
  `PV` identifies an agronomic protocol version tied to Cultivar productive
  use, not Semente. This freeze corrects the Registry: `PV` moves to the
  `CULTIVAR` concept entry; `SEMENTE` keeps no public identity (Section 4).

Result: `PRIOR ART REVIEW PASSED`. No competing identity, prefix, sequence or
naming collision exists for Semente V1 creation authority.

## 3. Concept

`SEMENTE` is the commercial seed product/reference authority: a specific
purchasable commercial reference (e.g. supplier `INTERSEMILLAS` + commercial
reference `VERDE MICROGREENS`) that can be evaluated for and used in
production. It is descriptive/commercial knowledge, not physical material and
not a production event.

`SEMENTE` is **not**: a physical manufacturer seed lot (`LOTTO_SEME`), a
production cycle (`SEMINA`), a stock movement, a traceability code, or an
inventory `ARTICOLO`.

Cardinality, as already frozen elsewhere and unchanged by this document:

```text
SEMENTE          -> SEMENTE_IMPIEGO   1:N
SEMENTE_IMPIEGO  -> CULTIVAR_USO      N:1
CULTIVAR_USO     -> CULTIVAR         N:1
CULTIVAR         -> VARIETA          N:1
```

No direct `SEMENTE -> VARIETA` edge and no direct `SEMENTE -> PROTOCOLLO` edge
are authorized.

## 4. Identity — Owner Decision D1

SEMENTE V1 does not introduce a public technical ID.

| Property | Frozen value |
|---|---|
| technical persistence identity | existing internal PostgreSQL `sementi.id` (bigint) |
| public identity | `NONE` |
| public sequence | `NONE` |
| canonical business identity | normalized `fornitore` + `referenza_commerciale` (Section 5) |

No `SementeId` domain type and no `SEMENTE_ID` sequence are authorized unless a
future architecture review explicitly reopens this decision. The internal
bigint is Infrastructure-only and is never accepted as caller input by a
future application command or CLI.

The prior Registry association of `ProtocolloVersioneId` (`PV`) with
`SEMENTE` is corrected by this freeze: `PV` is agronomic protocol-version
identity and is registered under the `CULTIVAR` concept (Section 3 evidence
above; Registry change in Section 20).

## 5. Business identity and normalization — Owner Decision D2

Constitutive identity fields:

```text
fornitore
referenza_commerciale
```

Normalization reuses the existing PostgreSQL semantics exactly, with no new
transformation:

```text
lower(btrim(fornitore))
lower(btrim(referenza_commerciale))
```

The definitive uniqueness backstop is the existing database constraint
`uq_sementi_fornitore_referenza_normalized`. Concurrent commissioning of the
same normalized `fornitore + referenza_commerciale` must converge to one
canonical `SEMENTE`; the application layer must not rely on a pre-check alone.

No accent folding, punctuation stripping or other canonical transformation is
authorized without a future owner decision.

After successful creation, `fornitore` and `referenza_commerciale` are
immutable. A genuinely different or corrected commercial reference becomes a
distinct `SEMENTE` authority; no in-place rewrite of the constitutive key is
authorized. Historical authority may later be deactivated using a separately
governed state command (Section 8).

## 6. Field classification

| Field | Classification |
|---|---|
| `fornitore` | CONSTITUTIVE_IDENTITY |
| `referenza_commerciale` | CONSTITUTIVE_IDENTITY |
| `marca` | OPTIONAL_METADATA |
| `formato` | OPTIONAL_METADATA |
| `trattamento` | OPTIONAL_METADATA |
| `certificazioni` | OPTIONAL_METADATA |
| `attiva` | STATE_AUTHORITY |
| `created_at` / `created_by` | PERSISTENCE_PROVENANCE |
| `updated_at` / `updated_by` | PERSISTENCE_PROVENANCE |
| `version` | OPTIMISTIC_CONCURRENCY |

## 7. Treatment — Owner Decision D3

`trattamento` is descriptive metadata in SEMENTE V1. It is not part of
business identity. Example: supplier `INTERSEMILLAS`, commercial reference
`VERDE MICROGREENS`, treatment `Sin tratamiento` — business identity remains
`INTERSEMILLAS + VERDE MICROGREENS`. Treatment metadata must never
independently create a second `SEMENTE` for the same normalized business key.

## 8. State model

The current state model is exactly:

```text
attiva = true
attiva = false
```

No new state enum and no lifecycle are authorized. Commissioning results in an
active `SEMENTE` under current authority (`attiva = true`). An
activation/deactivation command is separate and deferred (Section 17) unless
existing architecture already governs one.

## 9. Supplier authority — Owner Decision D4

No `FORNITORE` master/entity is authorized in SEMENTE V1. `fornitore` remains
normalized governed text inside `SEMENTE`. No duplicate supplier authority may
be introduced.

## 10. Creation authority

Conceptual command:

```text
CommissionSemente(
    fornitore: NormalizedText,
    referenza_commerciale: NormalizedText,
    marca: NormalizedText | None,
    formato: NormalizedText | None,
    trattamento: NormalizedText | None,
    certificazioni: NormalizedText | None,
    authority: SementeCommissioningAuthority(
        actor: ActorId,
        reason: NormalizedText,
        correlation_id: NormalizedText,
        idempotency_key: NormalizedText,
    ),
) -> CommissionSementeResult
```

`CommissionSementeResult` carries the internal identity, the normalized
business identity, metadata, `outcome: INSERTED | COMPATIBLE_REPLAY`, and
`recorded_at`. The public_id, `attiva`, timestamps and `version` are
writer-owned and are never caller input.

## 11. Idempotency — Owner Decision D5

SEMENTE creation uses a dedicated immutable commissioning request authority,
following the existing TPO request/idempotency pattern (`tpo.raccolta_recording_requests`,
`tpo.seed_lot_commissioning_requests`, `tpo.semina_commissioning_requests`).
The future physical persistence is `tpo.semente_commissioning_requests`.

Required semantics:

- opaque caller `idempotency_key`, scope `SEMENTE_COMMISSIONING_V1`;
- canonical payload hash over every authoritative domain input;
- same key + same canonical payload -> `COMPATIBLE_REPLAY`, same internal
  identity, no second insert and no duplicate mutation audit;
- same key + different canonical payload -> typed idempotency conflict, no
  mutation;
- concurrent identical requests converge to one `SEMENTE`;
- request reservation, creation/reconciliation, audit and request completion
  are one PostgreSQL transaction;
- committed request history is immutable; no repository-level retry beyond
  the caller re-issuing the same key.

This authority is DEFERRED_IMPLEMENTATION as of this freeze: it is frozen
architecture, not yet built (Section 17).

## 12. Audit

Canonical audit authority: `tpo.audit_eventi`. No parallel audit system is
introduced.

Successful first SEMENTE creation produces exactly one mutation audit event.
Compatible replay produces no duplicate mutation audit. The audit event
carries: internal SEMENTE identity, normalized `fornitore`, normalized
`referenza_commerciale`, metadata, actor, reason, correlation ID, idempotency
request reference, `before = NULL`, and the created after-state. Audit is
evidence of the mutation; it is not a second SEMENTE authority.

## 13. Concurrency

Concurrent commissioning of the same normalized `fornitore +
referenza_commerciale` must converge to one canonical `SEMENTE`. The existing
database unique normalized business-key constraint
(`uq_sementi_fornitore_referenza_normalized`) remains the final uniqueness
backstop; the application layer relies on it and does not rely only on an
application-level pre-check.

## 14. Correction semantics and immutability

After creation:

```text
fornitore              = FORBIDDEN to mutate
referenza_commerciale  = FORBIDDEN to mutate
```

No generic update path may mutate the constitutive key. A corrected commercial
identity becomes a distinct `SEMENTE` authority. No physical deletion of a
referenced historical `SEMENTE` is authorized.

Metadata correction (`marca`, `formato`, `trattamento`, `certificazioni`) is
DEFERRED unless separately frozen. Activation/deactivation is DEFERRED unless
separately frozen.

## 15. SEMENTE_IMPIEGO separation — Owner Decision D6

`SEMENTE_IMPIEGO` remains a separate authority. It is:

- NOT automatically created by SEMENTE commissioning;
- NOT required for SEMENTE creation;
- NOT required for LOTTO_SEME creation (a Seed Lot may be created from an
  active SEMENTE without SEMENTE_IMPIEGO, per
  `docs/architecture/SEED_LOT_COMMISSIONING_BOUNDARY_FREEZE.md` Section 3.4);
- REQUIRED before Semina commissioning where current Semina authority
  requires compatible `SEMENTE_IMPIEGO` classification `RACCOMANDATA` or
  `UTILIZZABILE`.

## 16. CULTIVAR / VARIETA and LOTTO_SEME / ARTICOLO separation — Owner Decision D7

`SEMENTE` is distinct from `CULTIVAR` and `VARIETA` (Section 3 cardinality);
it is never a Cultivar or Varieta identity.

`SEMENTE` is distinct from `LOTTO_SEME`. `LOTTO_SEME` is the physical
manufacturer-lot authority (`LSE-*`); manufacturer lot number, received date,
initial/residual quantity, lot-specific expiry, lot-specific analysis and
physical anomaly belong to `LOTTO_SEME`, never to `SEMENTE`.

`SEMENTE` / `ARTICOLO` coupling is DEFERRED. SEMENTE creation does not create
an `ARTICOLO`. `ARTICOLO` is not a prerequisite for SEMENTE commissioning.
Legacy `SEM-*` article references (e.g. `SEM-CIL`) remain legacy-only and are
never migrated or reinterpreted as SEMENTE, LOTTO_SEME or SEMINA identity.

## 17. Forbidden duplicates

The following are forbidden under SEMENTE V1:

- a public `SementeId` type or `SEMENTE_ID` sequence (Section 4);
- a dedicated `FORNITORE` master/entity (Section 9);
- treating `ProtocolloVersioneId` / `PV` as a Semente identity (Section 4);
- automatic `SEMENTE_IMPIEGO` creation from SEMENTE commissioning (Section 15);
- automatic `ARTICOLO` creation from SEMENTE commissioning (Section 16);
- migrating or reinterpreting legacy `SEM-*` article references as SEMENTE,
  LOTTO_SEME or SEMINA identity (Section 16);
- moving `LOTTO_SEME` physical-lot facts into SEMENTE identity (Section 16).

## 18. Live forward cutover

Once SEMENTE V1 implementation is reviewed, tested, migrated live and
certified, the exceptional one-time commissioning validation targets exactly:

```text
SUPPLIER               = INTERSEMILLAS
COMMERCIAL_REFERENCE   = VERDE MICROGREENS
TREATMENT              = Sin tratamiento
```

Expected business identity: normalized `INTERSEMILLAS` + normalized
`VERDE MICROGREENS`. No public SEMENTE ID is expected; the internal bigint
returned by commissioning is used by downstream persistence (`LOTTO_SEME`
commissioning) as required. This freeze does not authorize that
commissioning; it only defines the target.

## 19. Implementation boundary

After this freeze passes owner review, implement only the minimal governed
SEMENTE creation boundary:

| Layer | Component |
|---|---|
| application | `CommissionSemente` command, service, ports (`src/tpo_core/application/semente_commissioning/`) |
| infrastructure | PostgreSQL writer (`src/tpo_core/infrastructure/postgresql/semente_commissioning.py`) |
| bootstrap | builder exported from `src/tpo_core/bootstrap/` |
| CLI | thin `tpo semente commission` adapter |
| schema | migration for `tpo.semente_commissioning_requests` and any required constraints; `tpo.sementi` is modified only if the current schema proves insufficient — no public ID column is added |
| audit | `tpo.audit_eventi` INSERT inside the same transaction |
| tests | domain/application/CLI tests plus real PostgreSQL atomicity, concurrency and replay tests |

Do not implement, inside the SEMENTE creation task: `SEMENTE_IMPIEGO`,
`LOTTO_SEME`, `SEMINA`, Stock, `ARTICOLO`, a supplier master, metadata
correction, or activation/deactivation.

## 20. Registry change

`docs/architecture/AUTHORITY_REGISTRY.yaml` is updated by this freeze to:

- add a `semente_authority_v1` structured authority block (Owner Decisions
  D1-D7);
- update the `SEMENTE` concept entry: `identities: []`, add this document to
  `current_authorities`, `conflicts: []`, `open_owner_decisions: []`;
- correct the `CULTIVAR` concept entry: `identities:
  [{type: ProtocolloVersioneId, prefix: PV, sequence: PROTOCOLLO_VERSIONE_ID}]`.

The Registry ends with `conflicts=[]` and `open_owner_decisions=[]` for
SEMENTE V1 creation authority.

## 21. Deferred scope

Outside this boundary: SEMENTE_IMPIEGO creation/evaluation boundary; LOTTO_SEME
commissioning execution; SEMINA commissioning; Stock and Movimento Magazzino;
ARTICOLO and generic inventory authority; supplier master authority; metadata
correction command; activation/deactivation command; SEMENTE/ARTICOLO
coupling decision.

## 22. Next mission

Exactly one next mission is authorized for future owner initiation:

```text
IMPLEMENT SEMENTE COMMISSIONING BOUNDARY V1
```

It is not executed by this freeze.
