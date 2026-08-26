# TPO ARCHITECTURE AUTHORITY GOVERNANCE FREEZE V1

**Status:** NORMATIVE FREEZE CANDIDATE — OWNER APPROVAL REQUIRED
**Baseline:** `sprint-4.4-production-planning` at `4e6a127`
**Registry:** `docs/architecture/AUTHORITY_REGISTRY.yaml`

## 1. Purpose

This Freeze governs how TPO discovers, classifies and reconciles architectural
authority. It prevents a current implementation from silently erasing,
duplicating or reinventing business knowledge already present in the
repository. It does not implement or authorize any operational domain command.

`SPRINT 5.13 HARVEST DESIGN SUSPENDED PENDING AUTHORITY RECONCILIATION`

No RACCOLTA implementation, schema change, migration, operational data change,
Production Planning execution or authority commissioning is authorized here.

## 2. Source hierarchy

The following classifications are mandatory. A newer implementation does not,
by itself, erase business knowledge in an older source.

### 2.1 CURRENT RUNTIME AUTHORITY

PostgreSQL Core is the current operational runtime authority. Its approved
application boundaries, PostgreSQL writers and live schema are the only current
operational write path. Google Sheets is not current runtime authority and no
runtime may silently fall back or dual-write to it.

### 2.2 CURRENT ARCHITECTURE FREEZE

An owner-approved document under `docs/architecture/` governs the architecture
within its declared scope. Scope-specific freezes prevail over older general
descriptions for that same architectural responsibility. A freeze does not
silently supersede unrelated domain rules.

### 2.3 CURRENT OPERATIONAL RULE

An operational rule remains binding for its business meaning until it is
explicitly migrated, explicitly superseded, or explicitly rejected through an
owner/architecture decision. Implementation age is not a demotion criterion.

### 2.4 LEGACY IMPLEMENTATION

Legacy Google adapters, engines, scripts and writers are not current runtime
authority. They may remain available for explicitly governed simulation,
compatibility, tests or historical inspection. They must not enter the
PostgreSQL operational write graph.

### 2.5 LEGACY / PREDECESSOR DOMAIN KNOWLEDGE

Legacy documents, schemas and code may preserve valid names, identities,
calculations, distinctions and operational rules. Such knowledge remains a
mandatory prior-art input until it is classified and reconciled. The word
`legacy` describes implementation position, not business invalidity.

### 2.6 TEST-ONLY FIXTURE

A test-only fixture is not runtime or business authority. It may nevertheless
prove that a predecessor concept, field or collision existed. It must be cited
as evidence and corroborated before a rule is treated as authoritative.

### 2.7 SUPERSEDED AUTHORITY

An authority is superseded only when the Registry records both the superseded
rule and a replacement or owner/architecture decision reference. Absence from
the current code, age, naming differences or a new migration are insufficient.

## 3. PostgreSQL and Google reconciliation

The normative reconciliation is:

- PostgreSQL Core is current operational runtime authority.
- Current approved Architecture Freeze documents govern architecture within
  their declared scopes.
- The legacy Google implementation is not current runtime authority.
- Legacy Google documents and code may contain preserved domain knowledge.
- Legacy business rules remain valid prior art until explicitly migrated,
  superseded or rejected by an owner/architecture decision.
- Legacy material is preserved; this Freeze does not delete or rewrite it.

This resolves runtime selection. It does not claim that every historical
business rule has already been migrated into PostgreSQL Core.

## 4. Architecture Authority Registry

`AUTHORITY_REGISTRY.yaml` is the canonical machine-readable index of concepts
and sources. It does not replace the referenced authorities. It records:

- the canonical concept and classification;
- current sources, code and persistence;
- identities and prefixes;
- predecessors and preserved knowledge;
- explicit supersession;
- forbidden duplicates and conflicts;
- unresolved owner decisions;
- correction, audit, idempotency and verification authorities.

Every field defined by the Registry schema is mandatory for every entry. Empty
lists are explicit declarations, not permission to infer missing authority.

## 5. Mandatory repository-wide prior-art gate

Before designing any new entity, aggregate, register, identifier, prefix,
sequence, state, field, product reference, operational code, business rule,
workflow or authority boundary, a repository-wide prior-art review is
mandatory.

The search must include, when present:

- `docs/`, `docs/architecture/`, `docs/registers/`;
- `config/`, `data/`, `scripts/`, `src/`;
- `tests/`, all fixture directories and `migrations/`;
- repository-root material;
- legacy and archived material.

Searches must cover the proposed term, synonyms, translations, historical
names, candidate prefixes, table/field names and business meanings. Every
material match must be classified as exactly one of:

- `PRESERVED`
- `SUPERSEDED EXPLICITLY`
- `PARTIALLY MIGRATED`
- `MISSING FROM CORE`
- `DUPLICATED`
- `CONFLICTING`
- `OBSOLETE WITH EXPLICIT REPLACEMENT`
- `UNKNOWN / OWNER DECISION REQUIRED`

The only gate outcomes are:

`PRIOR ART REVIEW PASSED`

or

`PRIOR ART REVIEW BLOCKED`

The gate is fail-closed. If any material predecessor, collision, conflict,
source status or preserved rule remains unclassified, the result is
`PRIOR ART REVIEW BLOCKED`. Design and implementation must stop until the
authority is reconciled or an owner decision is recorded.

## 6. Forbidden duplicate governance

Registry `forbidden_duplicates` entries are normative collision guards. The
initial guards are:

- `LOTTO_PRODUZIONE` must not reappear beside SEMINA.
- Seed lot identity must not use `SEM-*`; it uses `LSE-*`.
- Legacy `SEM-CIL`-style article references are not `SeminaId` values.
- Planning `ALL-*` must not be treated as physical assignment authority.
- RACCOLTA must not be represented as a Semina state.
- CONSEGNA must not become ORDINE, FATTURA or MOVIMENTO.
- FATTURA must not be represented as CONSEGNA.

New guards require evidence from a prior-art review; speculative duplicates are
forbidden.

## 7. Traceability status

The current evidence is recorded without choosing a new design:

- `SEM-*` is the current permanent technical Semina identity.
- `AAA-GGMM-L` is a preserved legacy operational traceability rule.
- `MASTER_VARIETA.CODICE` is preserved predecessor variety-code authority.
- `ID_LOTTO` is a legacy production-group concept requiring explicit
  reconciliation.
- `RAC-*` is Harvest event identity.
- `LSE-*` is Seed Lot identity.

The normative status is:

`OWNER / ARCHITECTURE DECISION REQUIRED`

No alias, traceability code, generator, mapping or persistence field is
authorized by this Freeze.

## 8. Change governance

A Registry change must cite repository evidence or an owner/architecture
decision. It must preserve predecessor records and cannot turn an unresolved
entry into a resolved status merely because implementation has begun.

An entry may be marked `SUPERSEDED EXPLICITLY` or
`OBSOLETE WITH EXPLICIT REPLACEMENT` only when a replacement or decision
reference is present. Architecture tests must fail when this invariant, source
existence, required fields, unique concepts, unique forbidden aliases, identity
coverage or explicit unresolved status is violated.

## 9. Compliance statement

This Freeze establishes governance only. It invents no business authority,
does not resolve traceability, and does not resume Harvest design. Owner review
is required before it becomes an approved normative architecture Freeze.
