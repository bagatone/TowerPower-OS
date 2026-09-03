# SEMENTE_IMPIEGO AUTHORITY V1 FREEZE

## 1. PRE-FLIGHT

**Status:** OWNER-APPROVED ARCHITECTURE FREEZE
**Scope:** Semente Impiego commissioning boundary (first eligibility evaluation only)
**Prior-art gate:** PRIOR ART REVIEW PASSED

| Authority | Frozen baseline |
|---|---|
| repository | `/Users/bagatone/Documents/Codex/2026-06-28/a/work/towerpower-website/tpo` |
| writable | `YES` |
| branch | `sprint-4.4-production-planning` |
| HEAD | `017e41c` (`Fix normalization test to send pre-trimmed input`) |
| working tree before this document | clean |
| repository Alembic head | `20260903_0023` |
| live Alembic head | NOT CHECKED — this is an architecture-only task; no database connection was made |

This document does not authorize a migration, commissioning operation, database
write, commit, or push.

## 2. Prior-art gate result

Repository-wide search found:

- an existing, unmigrated table `tpo.semente_impieghi` (migration
  `20260810_0003_production_knowledge_prerequisites.py`) with columns
  `semente_id`, `cultivar_uso_id`, `raccomandazione`
  (`semente_raccomandazione` enum: `RACCOMANDATA | UTILIZZABILE |
  SCONSIGLIATA`), `rating`, `motivazione`, `ultima_revisione`, and a
  definitive unique constraint `uq_semente_impieghi_semente_cultivar_uso` on
  `(semente_id, cultivar_uso_id)`;
- an existing consumer:
  `src/tpo_core/infrastructure/postgresql/semina_commissioning.py` reads
  `tpo.semente_impieghi` and fails closed
  (`IncompatibleSeedLotError`) unless exactly one row exists for the
  resolved `(semente_id, cultivar_uso_id)` with `raccomandazione` in
  `(RACCOMANDATA, UTILIZZABILE)`. This is the live blocker: no code path
  exists to create that row, so no real SEMINA can ever be commissioned
  today, for any SEMENTE;
- no `SementeImpiegoId` domain type, no dedicated public sequence, and no
  `semente_impiego_commissioning` application package anywhere;
- `tpo.cultivar_usi` (created and upserted by the existing
  `agronomic_commissioning` boundary) has no dedicated public identity
  either; it is resolved everywhere else (see
  `src/tpo_core/infrastructure/postgresql/semina_commissioning.py`,
  method `_context`) by joining from an already-approved, currently-valid
  `PROTOCOLLO_VERSIONE` (`PV-*`) through `protocolli` to `cultivar_usi`.
  This freeze reuses that exact resolution join rather than inventing a
  second lookup path.

Result: `PRIOR ART REVIEW PASSED`. No competing identity, prefix, sequence
or naming collision exists for Semente Impiego V1 creation authority.

## 3. Concept

`SEMENTE_IMPIEGO` records whether, and how well, one specific `SEMENTE`
(commercial seed reference) is eligible for one specific `CULTIVAR_USO`
(a cultivar's productive use). It is an evaluation/compatibility fact, not a
physical event and not a production authorization by itself — it is the gate
that a future `SEMINA` commissioning must find satisfied.

```text
SEMENTE          -> SEMENTE_IMPIEGO   1:N
SEMENTE_IMPIEGO  -> CULTIVAR_USO      N:1
```

`SEMENTE_IMPIEGO` is **not**: `SEMENTE` itself, `CULTIVAR_USO` itself, a
`LOTTO_SEME`, a `SEMINA`, or a `PROTOCOLLO_VERSIONE`. A `PROTOCOLLO_VERSIONE`
(`PV-*`) is used only as the caller-facing resolution path to an existing,
approved `CULTIVAR_USO` (Section 5); it is never stored as part of
`SEMENTE_IMPIEGO` identity.

## 4. Identity — Owner Decision D1

No public technical ID is introduced, consistent with `SEMENTE` (Owner
Decision D1, `docs/architecture/SEMENTE_AUTHORITY_FREEZE.md` Section 4) and
with `CULTIVAR_USO` itself (no public identity exists today).

| Property | Frozen value |
|---|---|
| technical persistence identity | existing internal PostgreSQL `semente_impieghi.id` (bigint) |
| public identity | `NONE` |
| public sequence | `NONE` |
| canonical business identity | `(semente_id, cultivar_uso_id)` pair (Section 5) |

## 5. Business identity and resolution — Owner Decision D2

Constitutive identity is the existing database pair:

```text
semente_id, cultivar_uso_id
```

backed by the existing unique constraint
`uq_semente_impieghi_semente_cultivar_uso`.

Callers never supply either internal bigint. `semente_id` is resolved exactly
as in `SEED_LOT_COMMISSIONING_BOUNDARY_FREEZE.md` Section 3.3: normalized
`fornitore` + `referenza_commerciale`, active `SEMENTE` required.
`cultivar_uso_id` is resolved by reusing the existing, already-proven join in
`semina_commissioning.py` (`_context`): an owner-supplied
`protocol_version_public_id` (`PV-*`) must reference a
`PROTOCOLLO_VERSIONE` that is `stato_approvazione = APPROVATA`, currently
valid (`valida_dal <= today < valida_al`), belongs to an active `PROTOCOLLO`,
whose `CULTIVAR_USO` has `stato_validazione = APPROVATA`, whose `CULTIVAR`
and `VARIETA` are `stato = ATTIVA`, and whose `USO_PRODUTTIVO` is `attivo`.
Any other state resolves to a typed failure; no fallback resolution path is
authorized.

The same `CULTIVAR_USO` may be reachable from more than one `PV-*` over time
(new protocol versions). Resolution always targets the underlying
`CULTIVAR_USO`; two commissioning attempts that resolve to the same
`(semente_id, cultivar_uso_id)` — even via different `PV-*` — are the same
business duplicate (Section 12).

## 6. Field classification

| Field | Classification |
|---|---|
| `semente_id` (resolved) | CONSTITUTIVE_IDENTITY |
| `cultivar_uso_id` (resolved) | CONSTITUTIVE_IDENTITY |
| `raccomandazione` | EVALUATION_FACT |
| `rating` | EVALUATION_FACT (optional) |
| `motivazione` | EVALUATION_FACT (optional) |
| `ultima_revisione` | PERSISTENCE_PROVENANCE — writer-owned `CURRENT_DATE`, never caller input (Owner Decision D3) |
| `created_at` / `created_by` | PERSISTENCE_PROVENANCE |
| `updated_at` / `updated_by` | PERSISTENCE_PROVENANCE |
| `version` | OPTIMISTIC_CONCURRENCY |

## 7. Evaluation-date authority — Owner Decision D3

`ultima_revisione` is writer-owned (`CURRENT_DATE` at commissioning time),
never caller-supplied. This preserves the forward-only discipline already
adopted for this cutover (no synthetic historical evaluation dates), matching
the Owner's explicit "ignoriamo il passato, ripartiamo da oggi" decision
recorded for the live Semente cutover.

## 8. Raccomandazione domain — Owner Decision D4

All three existing enum values are eligible caller input:
`RACCOMANDATA`, `UTILIZZABILE`, `SCONSIGLIATA`. Recording an explicit
`SCONSIGLIATA` evaluation is in scope — it is valuable negative knowledge and
already representable by the frozen schema. No new enum value is authorized.

## 9. Creation authority

Conceptual command:

```text
CommissionSementeImpiego(
    fornitore: NormalizedText,
    referenza_commerciale: NormalizedText,
    protocol_version_public_id: ProtocolloVersioneId,
    raccomandazione: RACCOMANDATA | UTILIZZABILE | SCONSIGLIATA,
    rating: Decimal(0..100) | None,
    motivazione: NormalizedText | None,
    authority: SementeImpiegoCommissioningAuthority(
        actor: ActorId,
        reason: NormalizedText,
        correlation_id: NormalizedText,
        idempotency_key: NormalizedText,
    ),
) -> CommissionSementeImpiegoResult
```

`CommissionSementeImpiegoResult` carries the internal identity, the resolved
`fornitore`/`referenza_commerciale`, the resolved `cultivar_uso` descriptive
facts (variety public id, cultivar name, use name — read-only, for operator
confirmation), the evaluation facts, `outcome: INSERTED |
COMPATIBLE_REPLAY`, and `recorded_at`. Internal bigints, `ultima_revisione`,
timestamps and `version` are writer-owned and never caller input.

## 10. Idempotency — Owner Decision D5

Follows the identical pattern already frozen and implemented for `SEMENTE`
(`docs/architecture/SEMENTE_AUTHORITY_FREEZE.md` Section 11) and for
`LOTTO_SEME`/`SEMINA`: dedicated immutable commissioning request authority
`tpo.semente_impiego_commissioning_requests`, scope
`SEMENTE_IMPIEGO_COMMISSIONING_V1`, opaque `idempotency_key`, canonical
payload hash over every authoritative domain input (including
`protocol_version_public_id`, since it selects which `CULTIVAR_USO` is
targeted). Same key + same payload -> `COMPATIBLE_REPLAY`. Same key +
different payload -> typed idempotency conflict. Request reservation,
creation, audit and completion are one PostgreSQL transaction.

## 11. Audit

Canonical audit authority: `tpo.audit_eventi`, entity_type `SEMENTE_IMPIEGO`,
`entity_public_id = NULL` (no public identity, Section 4), internal identity
and resolved business facts carried in `after_data`, matching the `SEMENTE`
audit shape exactly.

## 12. Concurrency and duplicates

The existing unique constraint `uq_semente_impieghi_semente_cultivar_uso`
remains the definitive backstop. A second commissioning attempt that resolves
to an already-existing `(semente_id, cultivar_uso_id)` under a different
idempotency key is a typed duplicate, not a silent update and not a silent
convergence to the existing row — identical precedent to `SEMENTE` Owner
Decision D2/Section 13. Revising an existing evaluation is explicitly out of
scope for V1 (Section 15).

## 13. Correction semantics and immutability

After creation, `semente_id` and `cultivar_uso_id` (the constitutive pair)
are `FORBIDDEN` to mutate — a different pair is a distinct
`SEMENTE_IMPIEGO` authority. `raccomandazione`, `rating`, `motivazione` and
`ultima_revisione` are `DEFERRED` for correction/revision in V1 (Section 15).

## 14. Prerequisite ordering

`SEMENTE_IMPIEGO` commissioning requires, at commissioning time: an active
`SEMENTE` (Section 5) and an approved, currently-valid `PROTOCOLLO_VERSIONE`
resolving to an eligible `CULTIVAR_USO` (Section 5). It does not require any
`LOTTO_SEME` to exist. It remains, per existing frozen architecture
(`docs/architecture/SEED_LOT_COMMISSIONING_BOUNDARY_FREEZE.md` Section 3.4
and `docs/architecture/SEMENTE_AUTHORITY_FREEZE.md` Section 15), a
prerequisite for `SEMINA` commissioning but never for `SEMENTE` or
`LOTTO_SEME` creation.

## 15. Forbidden duplicates and deferred scope

Forbidden under V1:

- a public `SementeImpiegoId` type or dedicated public sequence (Section 4);
- a second resolution path to `CULTIVAR_USO` other than an approved,
  currently-valid `PROTOCOLLO_VERSIONE` (Section 5);
- silent convergence/update of an existing `(semente_id, cultivar_uso_id)`
  evaluation from a differently-keyed request (Section 12);
- caller-supplied `ultima_revisione` or any other synthetic historical
  evaluation date (Section 7).

Deferred, outside this boundary: revising/re-evaluating an existing
`SEMENTE_IMPIEGO` (a distinct future command, e.g.
`ReviseSementeImpiego`); bulk/batch evaluation; any UI or reporting surface
listing eligible seeds per cultivar use.

## 16. Implementation boundary

| Layer | Component |
|---|---|
| application | `CommissionSementeImpiego` command, service, ports (`src/tpo_core/application/semente_impiego_commissioning/`) |
| infrastructure | PostgreSQL writer (`src/tpo_core/infrastructure/postgresql/semente_impiego_commissioning.py`) |
| bootstrap | builder exported from `src/tpo_core/bootstrap/` |
| CLI | thin `tpo semente-impiego commission` adapter |
| schema | migration for `tpo.semente_impiego_commissioning_requests`; `tpo.semente_impieghi` is modified only if the current schema proves insufficient — no public ID column is added |
| audit | `tpo.audit_eventi` INSERT inside the same transaction |
| tests | domain/application/CLI tests plus real PostgreSQL atomicity, concurrency and replay tests |

## 17. Next mission

```text
IMPLEMENT SEMENTE_IMPIEGO COMMISSIONING BOUNDARY V1
```

It is not executed by this freeze.
