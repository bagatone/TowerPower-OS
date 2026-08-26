# SEMINA TRACEABILITY CODE AUTHORITY V1 FREEZE

**Status:** NORMATIVE FREEZE CANDIDATE — OWNER APPROVAL REQUIRED
**Baseline:** `sprint-4.4-production-planning` at `62f691e`
**Governance:** `docs/architecture/ARCHITECTURE_AUTHORITY_GOVERNANCE_FREEZE.md`

## 1. Scope

This Freeze reconciles only the permanent technical identity and the permanent
human-facing traceability reference of one physical SEMINA. It reconciles:

- `SEM-*`;
- `AAA-GGMM-L`;
- `MASTER_VARIETA.CODICE`;
- legacy `ID_LOTTO`;
- `PREDB`;
- legacy article codes such as `SEM-CIL`.

It does not implement a field, command, writer, migration or downstream
provenance model. It does not implement RACCOLTA, STOCK, CONSEGNA or FATTURA.
It does not authorize historical Semina commissioning or operational data
mutation.

## 2. Prior-art result

The repository-wide review classified the material prior art as follows:

| Prior art | Source | Classification before this Freeze | Reconciliation |
|---|---|---|---|
| `SEM-*` | Semina Commissioning Freeze and Core | PRESERVED | remains the constitutive technical identity |
| `AAA-GGMM-L` | `OPERATING_RULES.md`, `AGENTS.md` | MISSING FROM CORE / preserved operational rule | becomes the canonical human-facing Semina traceability code |
| `MASTER_VARIETA.CODICE` | Core Principles, legacy sheet schema | MISSING FROM CORE / predecessor authority | its business meaning moves to canonical VARIETA configuration |
| `ID_LOTTO` | legacy sheets, engines and operating rules | PARTIALLY MIGRATED | replaced in the current model by `SEM-*` plus its traceability code |
| `PREDB` | `OPERATING_RULES.md` | PRESERVED historical exception | confined to approved pre-database history |
| `SEM-CIL` family | legacy article/inventory implementation | CONFLICTING | remains a legacy article reference and is never a Semina or traceability identity |
| sowing or hydration date ambiguity | `AGENTS.md` | CONFLICTING | sowing/physical Semina start date is authoritative |
| `L` discriminator | operating rules and examples | PRESERVED | mandatory single-letter, day-and-variety scoped allocation |

No material predecessor in this scope remains unclassified.

`PRIOR ART REVIEW PASSED`

## 3. Two identities, one physical production group

Every newly commissioned physical SEMINA has two distinct, permanent
references:

1. `SEM-*`: the constitutive, semantic-neutral TPO public identity;
2. `AAA-GGMM-L`: the canonical human-facing operational traceability code.

`SEM-*` remains governed by the existing Semina Commissioning Freeze:

```text
SeminaId
prefix = SEM
format = SEM-[0-9]{6,}
sequence = SEMINA_ID
```

The traceability code does not replace, encode or allocate `SEM-*`. It is not a
second production aggregate and does not create `LOTTO_PRODUZIONE`.

## 4. Cardinality and permanence

For production commissioned under the future implementation of this Freeze:

```text
one SEM-* <-> exactly one AAA-GGMM-L
```

The relationship is mandatory and one-to-one:

- one Semina must have exactly one traceability code;
- one traceability code must identify exactly one Semina;
- two Semine must never share a traceability code;
- a traceability code must never be reassigned after rollback, correction,
  closure or historical retention of its Semina.

The technical identity and traceability code must be allocated and persisted in
the same atomic Semina commissioning transaction. A failure publishes neither.

## 5. Canonical format

The canonical traceability format is:

```text
AAA-GGMM-L
```

The grammar is:

```text
^[A-Z]{3}-[0-9]{4}-[A-Z]$
```

Its components are:

- `AAA`: authoritative three-uppercase-letter VARIETA traceability code;
- `GGMM`: day and month of the exact physical Semina start in the official
  `Atlantic/Canary` business timezone;
- `L`: mandatory discriminator for distinct Semine of the same VARIETA and
  local physical-start date.

Examples:

```text
CIL-2608-A
RAB-2608-B
```

The format is a traceability reference, not a globally meaningful description
from which business facts may be reconstructed without reading the Semina.

## 6. VARIETA code authority

The canonical Core home of `AAA` is VARIETA Configuration. The preserved
business meaning of `MASTER_VARIETA.CODICE` is migrated to that authority;
`MASTER_VARIETA` is not a current PostgreSQL runtime register.

The VARIETA traceability code must be:

- explicitly commissioned or migrated from owner-authorized source data;
- exactly three uppercase ASCII letters;
- unique across VARIETA;
- stable for all Semine already commissioned with it;
- read from authoritative Configuration, never derived algorithmically from a
  denomination, cultivar, product, seed reference or article code.

The physical column name and commissioning/correction command are deferred to
implementation review. This Freeze governs ownership and meaning, not schema.

The following mappings are preserved from the official operational rules:

| Code | Variety denomination recorded by the rule |
|---|---|
| `AFI` | Guisante Afila / Afila |
| `CIL` | Cilantro |
| `RAB` | Rábano Morado |
| `MIZ` | Mizuna Roja |
| `COL` | Col Roja |
| `MOS` | Mostaza |
| `GIR` | Girasole |
| `HIN` | Hinojo |
| `LEN` | Lenticchie |

This list does not authorize fuzzy name matching or new mappings. A current
VARIETA without an owner-authorized traceability code is ineligible for new
Semina commissioning once this authority is implemented. The command fails
closed; it never invents an abbreviation.

## 7. Date authority

`GGMM` is derived only from `semine.data_avvio`, the exact physical start
instant already constitutive under Semina Commissioning.

The instant is converted to the official `Atlantic/Canary` timezone and its
local calendar day and month form `GGMM`, with two digits each.

Hydration date is not a traceability-code authority. This explicitly supersedes
the legacy ambiguity “sowing or hydration” only for construction of
`AAA-GGMM-L`. It does not decide whether hydration is predictive knowledge, a
physical lifecycle fact or another future authority.

The code is not recalculated if an external timezone, display timezone or
downstream event date differs.

## 8. Discriminator authority

`L` is mandatory. It distinguishes Semine having the same authoritative
VARIETA code and the same `Atlantic/Canary` physical-start date.

Allocation scope:

```text
(varieta authority, local physical-start date)
```

Allocation order is the first unused uppercase letter in:

```text
A, B, C, ... Z
```

The authoritative allocation must:

- occur inside the Semina commissioning transaction;
- serialize concurrent allocations for the same scope under a persistent
  database lock/uniqueness authority;
- assign according to successful serialization order;
- release an uncommitted letter on rollback;
- reject collisions rather than select a caller-provided replacement;
- fail closed when `A` through `Z` are exhausted.

Multi-letter, numeric, optional, random and caller-selected discriminators are
outside V1. Exhaustion requires a dedicated Architecture Review and Freeze.

The Semina commissioning idempotency authority covers both `SEM-*` and the
traceability code. Same key plus same canonical payload returns the already
committed pair. Same key plus different payload fails. Replay never allocates a
new letter or a second Semina.

## 9. Immutability and correction

The traceability code is immutable after successful Semina commissioning.

It does not change when:

- Semina changes lifecycle state;
- the VARIETA denomination or traceability Configuration later changes;
- a protocol, LSE, Planning revision, customer or destination changes;
- one or more Raccolte, stock operations, deliveries or invoices refer to the
  production;
- the Semina closes or remains in permanent history.

A wrong constitutive Semina identity, start date or variety is not corrected by
rewriting or reassigning the code. Its future disposition requires a separate
governed correction boundary that preserves the erroneous pair. No code may be
reused.

## 10. Downstream propagation contract

The traceability code accompanies the same physical production through:

```text
SEMINA
-> lifecycle (GERMINAZIONE, LUCE, CRESCITA)
-> RACCOLTA
-> STOCK provenance
-> CONSEGNA provenance
-> FATTURA traceability reference
```

Downstream domains must reference the originating Semina authority and expose
or preserve its immutable traceability code as required by their own future
boundaries. They must not:

- generate a new production traceability identity;
- change or reallocate the code;
- infer the code from names or dates;
- replace `SEM-*` with the human code;
- treat `RAC-*`, a stock movement, delivery or invoice identity as the
  production-group identity.

One Semina may produce multiple Raccolte. Product from one traceability code may
serve multiple customers, Orders, Deliveries or Invoices. Conversely, a
downstream aggregate may need to preserve multiple originating traceability
codes. These facts do not change the one-to-one relationship between a Semina
and its code.

This section freezes propagation responsibility only. It does not decide
Harvest creation, stock publication, delivery provenance schema or invoice
implementation.

## 11. Legacy ID_LOTTO reconciliation

Legacy `ID_LOTTO` combined two responsibilities: it identified the physical
production group operationally and carried its human-readable traceability
reference.

In the current model those responsibilities are explicitly separated:

```text
legacy ID_LOTTO production-group meaning -> SEM-*
legacy ID_LOTTO displayed code           -> AAA-GGMM-L
```

Therefore legacy `ID_LOTTO` is
`OBSOLETE WITH EXPLICIT REPLACEMENT` for new PostgreSQL runtime production. Its
replacement is the mandatory pair `SEM-*` plus the Semina traceability code.

This is a semantic reconciliation, not authorization to import or
retroactively commission legacy production. Forward-only production cut-over
remains unchanged.

## 12. PREDB reconciliation

`PREDB` is confined to already approved traceability references for physical
production that predates the official coding/database cut-over.

- Existing approved PREDB references remain preserved and immutable.
- PREDB is never generated for new production.
- PREDB is not a `SeminaId`, `LottoSemeId`, `RaccoltaId` or current canonical
  `AAA-GGMM-L` code.
- PREDB does not authorize retrospective Semina commissioning or automatic
  mapping to a new `SEM-*`.
- Any future historical import or mapping requires a dedicated Freeze.

## 13. Legacy article-code collision

`SEM-CIL`, `SEM-RAB`, `SEM-AFI` and similar values are legacy article/inventory
references for seed resources. They are not:

- `SeminaId` values;
- `AAA-GGMM-L` traceability codes;
- `LSE-*` seed-lot identities;
- evidence that a physical Semina exists.

They must never be parsed, normalized, padded or migrated into `SEM-*`.
`SEM-CIL` does not satisfy `SEM-[0-9]{6,}`. A future ARTICOLO authority must
choose a namespace that cannot be confused with current TPO public identities;
this Freeze does not design that authority.

## 14. Forbidden duplicates

- No `LOTTO_PRODUZIONE` aggregate or identity may be introduced beside SEMINA.
- No second Semina traceability code may be introduced beside `AAA-GGMM-L`.
- `RAC-*`, `LSE-*`, article codes, manufacturer seed-lot numbers, customer,
  Order, Delivery and Invoice references must not substitute either member of
  the `SEM-*` / `AAA-GGMM-L` pair.
- No downstream domain may allocate another production-group traceability code.

## 15. Future implementation constraints

Any future implementation must be separately authorized and must include:

- canonical VARIETA code persistence and governed commissioning/migration;
- immutable Semina traceability persistence;
- atomic `SEM-*` and discriminator allocation;
- uniqueness and concurrency enforcement;
- Semina commissioning idempotency parity;
- audit/provenance for the resolved VARIETA code, date and discriminator;
- fail-closed behavior for missing code, invalid code, exhaustion and conflict;
- architecture, domain, migration and PostgreSQL integration tests.

This Freeze authorizes none of those changes by itself.

## 16. Final authority decision

The unresolved traceability placeholder recorded at governance baseline
`62f691e` is resolved for this scope:

```text
SEM-* = permanent technical Semina identity
AAA-GGMM-L = permanent human-facing traceability code of that same Semina
VARIETA Configuration = canonical AAA authority
GGMM = Atlantic/Canary date of exact physical Semina start
L = mandatory atomic A..Z discriminator per VARIETA/date
```

No material owner decision remains inside this Freeze scope.
