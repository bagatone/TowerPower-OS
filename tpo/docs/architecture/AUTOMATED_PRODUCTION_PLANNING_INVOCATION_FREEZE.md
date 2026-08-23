# AUTOMATED PRODUCTION PLANNING INVOCATION FREEZE

## 1. Status and scope

**Status:** FINAL ARCHITECTURE FREEZE

**Scope:** automated INITIAL Production Planning V1 invocation.

This freeze adds a dedicated automation boundary for Production Planning. It
does not alter the existing Automated Operational Scheduling Freeze, its
LaunchAgent, or its `06:00 Atlantic/Canary` occurrence.

## 2. Topology and invocation boundary

The official automated path is:

```text
dedicated macOS LaunchAgent
→ Production Planning CLI
→ Production Planning runtime
→ ProductionPlanningService.execute(command)
→ PostgreSQL adapters
```

The automation invokes only `tpo production-planning initial`. It does not
import or call Application, Engine, Assembler, Commit Writer, repositories, or
PostgreSQL directly. It does not invoke CLI parsing as shared business logic.

The concrete LaunchAgent and launcher belong to Sprint 5.3B and are not
part of the Application runtime. Their frozen deployment identities are:

| Artifact | Frozen value |
|---|---|
| LaunchAgent label | `com.towerpower.production-planning-scheduler` |
| launcher | `scripts/run_production_planning_schedule.sh` |
| occurrence helper | `scripts/production_planning_occurrence.py` |
| lock | `runtime/production-planning-scheduler.lock` |
| logs | `runtime/logs/production-planning-scheduler-*.log` |
| secrets | `runtime/secrets/production-planning-scheduler.env` |

The secrets file follows the existing seven-key PostgreSQL whitelist and
owner-only `0600` contract. It is provisioned manually and is never generated,
copied, repaired, or logged by the launcher or installer.

## 3. Occurrence and business reference

There is one nominal occurrence per local date at:

```text
06:30 Atlantic/Canary
```

For nominal local date `D`, `business_at` is exactly `D 06:30:00` resolved in
`Atlantic/Canary` and serialized as canonical ISO 8601 with seconds and the
effective UTC offset:

```text
YYYY-MM-DDT06:30:00+00:00
YYYY-MM-DDT06:30:00+01:00
```

The timezone database is authoritative for the offset. If the nominal local
time is ambiguous or nonexistent, invocation fails closed before the CLI and
before any RUN. The adapter does not substitute wall-clock execution time,
UTC, midnight, another offset, or a fallback occurrence.

There is no automatic retry and no catch-up. A missed occurrence is recovered
only by an explicitly authorized manual replay.

## 4. Frozen command

Every occurrence supplies all fields explicitly:

| Field | Value |
|---|---|
| mode | `initial` |
| policy set | `DEFAULT` |
| policy version | `1` |
| actor | `tpo.production-planning-scheduler` |
| reason | `Automated Production Planning V1` |
| correlation ID | `production-planning-auto-v1:<canonical-business-at>` |

Automated REPLAN is unsupported in V1. The automatic boundary must reject it
before runtime invocation and must not synthesize a previous revision, order
line, reason code, or disposition authority.

## 5. Idempotency and manual replay

The nominal occurrence is the logical invocation identity. The same occurrence
always reuses the same `business_at`, `DEFAULT/1`, actor, reason, and correlation
ID. A different occurrence has a different canonical `business_at` and
correlation ID.

The existing `revision_request_key` remains the business idempotency authority.
No scheduler execution table or second idempotency mechanism is introduced.

A manual replay must use the original occurrence's complete canonical fields.
It may open a distinct attempt RUN according to the existing Planning contract,
but a compatible replay does not create a duplicate revision. Automation never
initiates that replay itself.

## 6. Relationship with Operational Scheduling

Operational Scheduling remains independently scheduled at `06:00
Atlantic/Canary`, with its existing RUN lifecycle and automation contract.
Production Planning has an independent RUN lifecycle and no hard dependency
requiring the `06:00` RUN to have completed.

The `06:30` Planning snapshot may include authoritative eligible ORDINI already
committed before that PostgreSQL snapshot begins. ORDINI still uncommitted or
committed after the snapshot boundary are not promised to be visible. Planning
does not poll, wait for, inspect, or classify the Operational Scheduling RUN.

## 7. Outcome policy

| Outcome | Automated behavior |
|---|---|
| `COMMITTED` | occurrence succeeds; record sanitized public CLI output; no further Planning action |
| expected `FAILED` | observable operational failure; no retry or second RUN |
| `RECONCILIATION_REQUIRED` | preserve public reconciliation context; no retry, compensation, or inferred state; immediate escalation |
| `RUN_FINALIZATION_OUTCOME_UNCERTAIN` | high-priority reconciliation; no retry and no invented final RUN state |
| runtime/configuration failure | sanitized operational failure; no business retry |

No outcome triggers Operational Scheduling, compensation, fallback, Google,
Sheets, or a second Production Planning execution.

## 8. Frozen exclusions

V1 introduces no daemon, cron job, LaunchDaemon, schema migration, business
policy seed migration, Google/Sheets dependency, direct runtime automation,
automatic REPLAN, retry, catch-up, recovery, or reconciliation automation.

Changing the occurrence, timezone, policy, actor, reason, correlation grammar,
CLI-only boundary, replay rules, or relationship with Operational Scheduling
requires a new architecture review.
