# FATTURA AUTHORITY V1 FREEZE

## 1. PRE-FLIGHT

**Status:** OWNER-APPROVED ARCHITECTURE FREEZE
**Scope:** Fattura (invoice) emission and correction — creation authority only. Payment/collection (`PAGAMENTO`/`INCASSO`) is explicitly out of scope (Section 17).
**Prior-art gate:** PRIOR ART REVIEW PASSED

| Authority | Frozen baseline |
|---|---|
| repository | `/Users/bagatone/Documents/Codex/2026-06-28/a/work/towerpower-website/tpo` |
| writable | `YES` |
| branch | `sprint-4.4-production-planning` |
| HEAD | `aadbb2c` (`Wire delivery fulfilment CLI and backfill MOV/ORD/CON/RUN id_sequences`) |
| working tree before this document | clean |
| repository Alembic head | `20260903_0025` |
| live Alembic head | NOT CHECKED — this is an architecture-only task; no database connection was made |

This document does not authorize a migration, commissioning operation, database
write, commit, or push.

## 2. Prior-art gate result

Repository-wide search found:

- `docs/registers/AMMINISTRAZIONE.md`: a full, pre-existing domain-governance
  document defining `FATTURA` (§5.3, "il documento fiscale"), `RIGA FATTURA`
  (§5.6), `PAGAMENTO`/`INCASSO` (§5.7-5.8), `ALLOCAZIONE DEL PAGAMENTO`
  (§5.9), `RETTIFICA` (§5.10), `SCADENZA DOCUMENTATA` (§5.12) and the
  permanent separations in §7 (`Fattura non è Pagamento`, `Le Fatture
  definitive sono immutabili`, `Le rettifiche producono nuovi Facts`, ...).
  This freeze adopts that vocabulary verbatim and does not redefine it;
- `docs/registers/DOCUMENTO_DI_VENDITA.md`: a distinct, separately-frozen
  concept (delivery note issued when no `FATTURA` is required). Explicitly
  forbids IVA/IGIC/prices/amounts/payment terms in its own content (§12).
  Out of scope here — not built by this freeze;
- `AUTHORITY_REGISTRY.yaml` `FATTURA` entry: `status: UNKNOWN / OWNER
  DECISION REQUIRED`, `core_implementations: []`, `persistence_authorities:
  []`, `identities: []`, `open_owner_decisions: ["Freeze invoice identity,
  lifecycle and commissioning boundary in a future administration
  sprint."]` — this is that sprint;
- `CONSEGNE.md`: "La CONSEGNA costituisce il riferimento operativo della
  futura fatturazione. La FATTURA fa riferimento ad una o più CONSEGNE. La
  CONSEGNA non genera direttamente la FATTURA." — `FATTURA` references
  `CONSEGNA`, never the reverse, and never `ORDINE`/`RIGA_ORDINE` directly;
- no `prezzo`/`price`/`listino` column, table or Configuration concept
  anywhere in the repository (checked across migrations, data dictionary and
  architecture docs). No pricing authority of any kind exists today;
- `tpo.clienti` (migration `20260806_0002`) has no invoicing-mode or
  payment-terms columns — only `public_id`, `denominazione` and provenance
  columns;
- `PRODOTTO` concept (`AUTHORITY_REGISTRY.yaml`): `status: UNKNOWN / OWNER
  DECISION REQUIRED`, with an already-registered, already-accepted conflict
  — `"Core commercial lines currently reference Varieta directly."` This
  freeze inherits that same conflict rather than resolving it: `FATTURA`
  lines reference `VARIETA`, exactly like `RIGA_ORDINE` and `RIGA_CONSEGNA`
  already do;
- `tpo.id_sequences` / `PersistentIdAllocator`
  (`docs/architecture/APPLICATION_ATOMIC_COMMIT_FREEZE.md` §14, "Identity:
  compare-and-set PostgreSQL su sequenza tipizzata e versionata"): the
  existing identity mechanism assumes one fixed prefix and a sequence that
  never resets. It cannot produce a numbering series that resets every
  calendar year, which the legal invoice number requires (Section 6). No
  existing mechanism is reused unmodified for `FATTURA` numbering;
- no `FatturaId`, `RigaFatturaId`, pricing type or invoice-related domain
  type exists anywhere in `src/tpo_core/domain/identifiers.py` or
  `domain/states.py`.

Result: `PRIOR ART REVIEW PASSED`. No competing identity, numbering,
pricing or commissioning boundary exists for Fattura V1.

## 3. Owner-provided fiscal context (this session)

Recorded verbatim because it overrides any assumption this project would
otherwise default to (the codebase's working language is Italian, but the
business itself is not):

- Tower Power operates from the **Canary Islands**. The applicable indirect
  tax is **IGIC** (Impuesto General Indirecto Canario), **not** Italian IVA.
- Electronic transmission to a tax authority (SII, Verifactu, SDI or any
  equivalent) is explicitly **out of scope** for V1 (Section 17).
- Currency is **EUR only** (Owner Decision, Section 7).

## 4. Concept

`FATTURA` is the fiscal document that records an economic and fiscal
obligation. It is distinct from `ORDINE`, `CONSEGNA`, `DOCUMENTO_DI_VENDITA`,
`PAGAMENTO` and any `RAPPRESENTAZIONE` (e.g. a PDF) of itself
(`AMMINISTRAZIONE.md` §5.3, §7). A definitive `FATTURA` is immutable
(`AMMINISTRAZIONE.md` §6.2); corrections are new, separately-numbered
documents (Section 16).

```text
CLIENTE   -> FATTURA        1:N
CONSEGNA  -> FATTURA        N:1  (one CONSEGNA belongs to exactly one FATTURA once invoiced)
FATTURA   -> RIGA_FATTURA   1:N
RIGA_CONSEGNA -> RIGA_FATTURA  1:1 (a delivery line is invoiced at most once)
VARIETA   -> RIGA_FATTURA   N:1  (price/rate source, via LISTINO_VARIETA, Section 9)
```

`FATTURA` is **not**: `ORDINE`, `CONSEGNA`, `DOCUMENTO_DI_VENDITA`,
`PAGAMENTO`, `INCASSO`, a `RAPPRESENTAZIONE` (PDF/print), or an accounting
ledger. It does not compute or store `STATE ECONOMICO` (that remains
`Derived`, `AMMINISTRAZIONE.md` §5.14, and is out of scope here).

## 5. Identity — Owner Decision D1

The public identity of a `FATTURA` **is** its legal invoice number, not a
separate semantically-neutral technical code. This is a deliberate,
explicit deviation from every other entity frozen so far in this system
(`SEMENTE`, `SEMENTE_IMPIEGO`, `LOTTO_SEME`, `SEMINA`, `RACCOLTA`,
`CONSEGNA`, ... all use a neutral internal prefix precisely so the public
code carries no meaning). A legal invoice number is different in kind: the
law itself requires it to be permanent, sequential and gap-free — it already
has exactly the properties an internal identity exists to provide, and
introducing a second, competing "real" identity alongside it would violate
`REGISTER_GOVERNANCE`'s single-identity discipline instead of upholding it.

| Property | Frozen value |
|---|---|
| technical persistence identity | new internal PostgreSQL `fatture.id` (bigint), never exposed |
| public identity (`numero_fattura`) | the legal sequential number itself |
| format | `AAAA/NNNN` — 4-digit year, `/`, 4-digit sequence, e.g. `2026/0001` (Owner-confirmed) |
| identity shape | a dedicated value object, **not** a `PermanentId` subclass — `PermanentId`'s frozen regex (`PREFIX-[0-9]{6,}`, Owner Decision baked into every other identity) cannot express a year-scoped, 4-digit, `/`-separated series without redefining that shared base class, which this freeze does not authorize |
| mutability | immutable once assigned; never reassigned, reused or reissued to a different `FATTURA` |

## 6. Numbering authority — Owner Decision D2

A dedicated, year-scoped numbering authority is introduced:
`tpo.fattura_numerazione` — `(anno: int PRIMARY KEY, next_value: bigint,
version: bigint)`, following the exact compare-and-set discipline already
frozen for `tpo.id_sequences`
(`APPLICATION_ATOMIC_COMMIT_FREEZE.md` §14) but keyed per calendar year
instead of once globally. A new year with no row yet is initialized
lazily (`next_value = 1`) on first use within the same transaction — no
migration seed is required per year.

**Gap-free allocation.** Unlike `MovimentoId`/`ConsegnaId`
(`docs/architecture/AUTHORITY_REGISTRY.yaml`, backfilled by migration
`20260903_0025`), where the number is allocated in its own transaction
*before* the fact that consumes it — an accepted source of harmless gaps for
purely internal identities — `numero_fattura` allocation **must** happen
**inside the same single PostgreSQL transaction**
(`APPLICATION_ATOMIC_COMMIT_FREEZE.md` §14, "write path: una sola
transazione PostgreSQL") that inserts the `FATTURA` row itself. If that
transaction rolls back for any reason, the compare-and-set on
`fattura_numerazione` rolls back with it, and no number is consumed. This is
the mechanism by which "senza buchi" (Owner-confirmed, Section 3) is
actually satisfied — not a promise layered on top of a two-step allocate-then-use
pattern that cannot make that guarantee.

## 7. Fiscal model — Owner Decision D3

- Tax: **IGIC**, never Italian IVA, never a generic "VAT" field name in the
  domain model.
- Rate: **not** a fixed system constant. `aliquota_igic` is a per-line
  (`RIGA_FATTURA`) `Decimal` value, sourced from `LISTINO_VARIETA` (Section
  9) at emission time and snapshotted onto the line (Owner-confirmed: "può
  variare per prodotto").
- Currency: **EUR only**. No multi-currency field, conversion or storage in
  V1 (Owner-confirmed).
- Electronic transmission (SII/Verifactu/SDI or equivalent): **out of
  scope** (Section 17). `FATTURA` V1 is an internal fiscal record only.

## 8. Prerequisite Configuration: CLIENTE extension — Owner Decision D4

`FATTURA` emission cannot resolve its own constitutive shape (Section 11)
without two facts that belong to `CLIENTE` as `CONFIGURATION`
(`AMMINISTRAZIONE.md` §4.3: "CONFIGURATION governa ... Clienti ... termini").
`tpo.clienti` gains two additive columns (existing rows/columns/constraints
untouched, per this project's standing forward-only, non-breaking-migration
discipline):

| Field | Meaning |
|---|---|
| `modalita_fatturazione` | `A_CONSEGNA \| PERIODICA_MENSILE` — Owner-confirmed: "dipende dal cliente" |
| `termini_pagamento_giorni` | integer, days from emission to due date — Owner-confirmed: "variano per cliente" |

Both are `CONFIGURATION` (current values, not an append-only Fact history).
`FATTURA` snapshots what it needs from them at emission time (`scadenza`,
Section 11) — it never re-reads `CLIENTE` later to reinterpret an already
emitted invoice, consistent with `AMMINISTRAZIONE.md` §5.12 ("Scadenza
documentata" must be attested by the document itself, not recomputed).

## 9. Prerequisite Configuration: LISTINO_VARIETA — Owner Decision D5

A new, minimal `CONFIGURATION` concept: `tpo.listino_varieta` —
`(varieta_id UNIQUE, prezzo_unitario NUMERIC, aliquota_igic NUMERIC, ...)`.
One **current** row per `VARIETA` (Owner-confirmed: "prezzo unico di listino
per varietà" — not per-client, not an order-time negotiation). It is
mutable Configuration, **not** an append-only Fact register — there is no
requirement to keep price history as its own authority, because
`RIGA_FATTURA` snapshots `prezzo_unitario` and `aliquota_igic` into its own
immutable fields at emission time (Section 11), exactly as `SEMENTE_IMPIEGO`
already snapshots `cultivar`/`uso_produttivo` descriptive facts rather than
re-deriving them later. A `VARIETA` with no `LISTINO_VARIETA` row cannot be
invoiced (typed failure, no fallback price).

`LISTINO_VARIETA` commissioning/maintenance (who may change a price, and
how) is not frozen by this document — Section 17.

## 10. Granularity and period — Owner Decision D6

- Per `CLIENTE.modalita_fatturazione` (Section 8):
  - `A_CONSEGNA`: one `FATTURA` may cover exactly one `CONSEGNA`.
  - `PERIODICA_MENSILE`: one `FATTURA` covers every `CONSEGNA` in state
    `CONSEGNATA` for that `CLIENTE` within one calendar month, not yet
    attached to another `FATTURA`.
- Lines are **never** aggregated across `CONSEGNA`/`VARIETA` boundaries
  (Owner-confirmed: "una riga per riga di consegna"). Every `RIGA_FATTURA`
  corresponds to exactly one `RIGA_CONSEGNA` (Section 4). A `PERIODICA_MENSILE`
  `FATTURA` with five delivered order lines across three deliveries has five
  `RIGA_FATTURA` rows, not three and not one per `VARIETA`.
- Late-arriving corrections to a `CONSEGNA` after its calendar month has
  already been invoiced are **deferred** — Section 17.

## 11. Field classification and creation authority

Conceptual command:

```text
EmitFattura(
    cliente_public_id: ClienteId,
    consegna_public_ids: tuple[ConsegnaId, ...],   # exactly 1 for A_CONSEGNA, 1..N for PERIODICA_MENSILE
    authority: FatturaEmissionAuthority(
        actor: ActorId,
        reason: NormalizedText,
        correlation_id: NormalizedText,
        idempotency_key: NormalizedText,
    ),
) -> EmitFatturaResult
```

| Field | Classification |
|---|---|
| `numero_fattura` (`AAAA/NNNN`) | CONSTITUTIVE_IDENTITY — writer-owned (Section 6), never caller input |
| `cliente_id` (resolved) | CONSTITUTIVE_IDENTITY |
| `consegna_id` (per referenced `CONSEGNA`) | CONSTITUTIVE_IDENTITY (join table, one row per covered `CONSEGNA`) |
| `data_emissione` | PERSISTENCE_PROVENANCE — writer-owned `CURRENT_DATE`, never caller input (same forward-only discipline as `SEMENTE_IMPIEGO.ultima_revisione`) |
| `scadenza` | ECONOMIC_FACT — writer-computed as `data_emissione + cliente.termini_pagamento_giorni`, snapshotted at emission (Section 8) |
| `RIGA_FATTURA.riga_consegna_id` (resolved) | CONSTITUTIVE_IDENTITY |
| `RIGA_FATTURA.varieta_id` (mirrored from `RIGA_CONSEGNA`, never re-declared) | ECONOMIC_FACT provenance |
| `RIGA_FATTURA.quantita`/`unita_misura` (mirrored from `RIGA_CONSEGNA`) | ECONOMIC_FACT provenance |
| `RIGA_FATTURA.prezzo_unitario` | ECONOMIC_FACT — snapshotted from `LISTINO_VARIETA` at emission (Section 9) |
| `RIGA_FATTURA.aliquota_igic` | ECONOMIC_FACT — snapshotted from `LISTINO_VARIETA` at emission (Section 9) |
| `RIGA_FATTURA.importo_netto` / `importo_igic` | ECONOMIC_FACT — writer-computed, never caller input |
| `created_at` / `created_by` | PERSISTENCE_PROVENANCE |

`EmitFatturaResult` carries `numero_fattura`, `cliente_id`, the resolved
line facts (for operator confirmation), `totale_netto`, `totale_igic`,
`totale`, `scadenza`, `outcome: EMESSA | COMPATIBLE_REPLAY`, and
`recorded_at`. Internal bigints, `numero_fattura` (Section 6), `data_emissione`,
computed amounts and `version` are all writer-owned.

## 12. Idempotency

Follows the identical pattern frozen and implemented for `SEMENTE`,
`SEMENTE_IMPIEGO`, `RACCOLTA` and `CONSEGNA`: a dedicated immutable
commissioning-request authority `tpo.fattura_emissione_requests`, scope
`FATTURA_EMISSIONE_V1`, opaque `idempotency_key`, canonical payload hash
over every authoritative input (`cliente_public_id`, the exact set of
`consegna_public_ids`). Same key + same payload -> `COMPATIBLE_REPLAY`
(returns the already-assigned `numero_fattura`, never allocates a second
one). Same key + different payload -> typed idempotency conflict.
Reservation, numbering (Section 6), `FATTURA`/`RIGA_FATTURA` insertion and
audit are one PostgreSQL transaction.

## 13. Audit

Canonical audit authority: `tpo.audit_eventi`, `entity_type = 'FATTURA'`,
`entity_public_id = numero_fattura` (unlike `SEMENTE`/`SEMENTE_IMPIEGO`,
`FATTURA` has a real public identity to use here, Section 5). One audit row
per emitted `FATTURA`; correction (Section 16) audits under the same rule
with the new document's own `numero_fattura`.

## 14. Concurrency and duplicates

- A `RIGA_CONSEGNA` may be covered by at most one *active* `RIGA_FATTURA` —
  a definitive unique constraint (`uq_riga_fattura_riga_consegna`), the same
  single-authoritative-consumer discipline already used for
  `raccolta_recording_raccolta` and `semente_impieghi`'s constitutive pair.
  A second `EmitFattura` attempt that would re-invoice an already-invoiced
  `RIGA_CONSEGNA` fails closed — no silent skip, no silent merge.
- `numero_fattura` allocation (Section 6) is the concurrency backstop for
  the numbering series itself: two concurrent emissions in the same year
  serialize on the `fattura_numerazione` row's compare-and-set exactly like
  `tpo.id_sequences` does today.
- A `CONSEGNA` not in state `CONSEGNATA` (Section 4, `CONSEGNE.md`) cannot
  be referenced by `EmitFattura` — typed failure, no fallback.

## 15. Prerequisite ordering

`FATTURA` emission requires, at emission time: an existing `CLIENTE` with
`modalita_fatturazione` and `termini_pagamento_giorni` set (Section 8); one
or more `CONSEGNA` in state `CONSEGNATA` belonging to that `CLIENTE`,
matching the requested `modalita_fatturazione` shape (Section 10); and a
`LISTINO_VARIETA` row for every `VARIETA` appearing in the covered
`RIGA_CONSEGNA` (Section 9). It does not require, and never touches,
`PAGAMENTO`/`INCASSO` (Section 17).

## 16. Correction semantics and immutability — Owner Decision D7

A definitive `FATTURA` is immutable end to end
(`AMMINISTRAZIONE.md` §6.2): no field, once emitted, may ever be updated —
not `numero_fattura`, not amounts, not the covered `CONSEGNA` set. A
correction (Owner-confirmed: "nota di credito / fattura rettificativa") is
modeled as a **new** `FATTURA`:

- it receives its **own** `numero_fattura` from the same year-scoped series
  (Section 6) — Spanish/Canary correlativity applies to rectificative
  invoices exactly as it does to ordinary ones, they are not a separate,
  unnumbered artifact;
- it carries an explicit `rettifica_di: numero_fattura` reference to the
  original, which is never mutated (`AMMINISTRAZIONE.md` §5.10);
- its `RIGA_FATTURA` rows are **not** required to trace back 1:1 to a
  `RIGA_CONSEGNA` (Section 14's uniqueness constraint applies only to
  ordinary emission) — a rectificative line corrects a previously invoiced
  amount and is a distinct, smaller commissioning shape deferred to its own
  future command (`RectifyFattura`), out of this freeze's implementation
  boundary (Section 17) but reserved here so the numbering/identity model
  (Sections 5-6) does not need to change when it is built.

## 17. Forbidden duplicates and deferred scope

Forbidden under V1:

- a second, neutral internal `FatturaId` alongside `numero_fattura`
  (Section 5) — one identity, not two competing ones;
- allocating `numero_fattura` outside the single commit transaction
  (Section 6) — this is the one guarantee this freeze cannot compromise on;
- a fixed IVA-style tax rate constant, or the name "IVA"/"VAT" anywhere in
  the domain model (Section 7 — this is IGIC);
- per-client negotiated pricing, order-time pricing, or manual per-invoice
  price entry (Section 9 — Owner-confirmed single price list per `VARIETA`);
- aggregating `RIGA_FATTURA` across `CONSEGNA` or `VARIETA` boundaries
  (Section 10);
- re-invoicing an already-invoiced `RIGA_CONSEGNA` (Section 14);
- editing or deleting a definitive `FATTURA` (Section 16).

Deferred, outside this boundary:

- `PAGAMENTO`/`INCASSO` and `ALLOCAZIONE DEL PAGAMENTO` (Owner-confirmed:
  "solo FATTURA per ora") — a distinct future freeze;
- `DOCUMENTO_DI_VENDITA` (delivery note without invoice) — a distinct,
  already-scoped-elsewhere future concept, not built here;
- electronic transmission (SII/Verifactu/SDI or equivalent) — Owner-confirmed
  out of scope;
- multi-currency — Owner-confirmed out of scope;
- `LISTINO_VARIETA` commissioning/versioning/history (who may change a
  price, when, with what authorization) — V1 treats it as directly-editable
  Configuration with no governance boundary of its own yet;
- `RectifyFattura` implementation (Section 16 reserves the shape only);
- handling `CONSEGNA` delivered after its calendar month was already
  invoiced (`PERIODICA_MENSILE`, Section 10);
- any PDF/print `RAPPRESENTAZIONE` of a `FATTURA`;
- any UI or reporting surface.

## 18. Implementation boundary

| Layer | Component |
|---|---|
| application | `EmitFattura` command, service, ports (`src/tpo_core/application/fattura_emissione/`) |
| infrastructure | PostgreSQL writer (`src/tpo_core/infrastructure/postgresql/fattura_emissione.py`) |
| bootstrap | builder exported from `src/tpo_core/bootstrap/` |
| CLI | thin `tpo fattura emetti` adapter |
| schema | migration(s) for `tpo.clienti` additive columns (Section 8), `tpo.listino_varieta` (Section 9), `tpo.fattura_numerazione` (Section 6), `tpo.fatture`, `tpo.righe_fattura`, `tpo.fattura_emissione_requests` (Section 12) |
| audit | `tpo.audit_eventi` INSERT inside the same transaction |
| tests | domain/application/CLI tests plus real PostgreSQL atomicity, concurrency, gap-free-numbering and replay tests |

## 19. Next mission

```text
IMPLEMENT FATTURA EMISSION BOUNDARY V1
```

It is not executed by this freeze.
