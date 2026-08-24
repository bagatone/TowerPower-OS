"""Writer PostgreSQL autorevole del Production Planning V1."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from ...application.production_planning.errors import (
    ProductionPlanningError,
    ProductionPlanningOutcomeUncertain,
)
from ...application.production_planning.models import (
    AllocationDraft,
    AllocationTransitionDraft,
    CanonicalReplanningSnapshot,
    PlanRevisionDraft,
    ProductionPlanningCommit,
    ProductionPlanningResult,
    RevisionCommitResult,
)
from ...domain.time_reference import OFFICIAL_TIMEZONE, OFFICIAL_TIMEZONE_NAME
from .connection import PostgreSQLConnectionFactory


_CHILDREN = {
    "DOMANDA": ("allocazioni_domanda", "riga_ordine_id", "righe_ordine"),
    "STOCK": ("allocazioni_stock", "stock_varieta_id", "stock"),
    "PRODUZIONE_IN_CORSO": (
        "allocazioni_produzione_in_corso", "semina_id", "semine",
    ),
    "RACCOLTA": ("allocazioni_raccolta", "raccolta_id", "raccolte"),
}


class PostgreSQLProductionPlanningCommitWriter:
    """Implementazione di ``ProductionPlanningCommitPort`` su una transazione."""

    def __init__(self, connection_factory: PostgreSQLConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def commit(
        self, write_set: ProductionPlanningCommit, *, completed_at: datetime
    ) -> ProductionPlanningResult:
        if not isinstance(write_set, ProductionPlanningCommit):
            raise ProductionPlanningError(
                "PLANNING_INPUT_INVALID", "INVALID_WRITE_SET",
                "Write set Production Planning non valido.",
            )
        if completed_at.tzinfo is None or completed_at.utcoffset() is None:
            raise ProductionPlanningError(
                "PLANNING_INPUT_INVALID", "INVALID_PERSISTENCE_TIME",
                "Timestamp tecnico del commit non valido.",
            )

        connection = self._connection_factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            result = self._execute(cursor, write_set, completed_at)
            try:
                connection.commit()
            except Exception as exc:
                raise ProductionPlanningOutcomeUncertain(
                    "Esito del commit Production Planning da riconciliare tramite RUN."
                ) from exc
            committed = True
            return result
        except (ProductionPlanningError, ProductionPlanningOutcomeUncertain):
            raise
        except psycopg.errors.UniqueViolation as exc:
            try:
                connection.rollback()
                result = self._read_compatible_replay(write_set)
            except ProductionPlanningError:
                raise
            except Exception as replay_exc:
                raise _failure(
                    "CONCURRENCY_CONFLICT", "IDEMPOTENCY_RACE_CONFLICT",
                    "Uniqueness race incompatibile nel commit Production Planning.",
                    replay_exc,
                ) from exc
            committed = True
            return result
        except (psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected) as exc:
            raise _failure(
                "CONCURRENCY_CONFLICT", "POSTGRESQL_CONCURRENCY_CONFLICT",
                "Conflitto concorrente durante il commit Production Planning.", exc,
            )
        except psycopg.IntegrityError as exc:
            raise _failure(
                "CONCURRENCY_CONFLICT", "POSTGRESQL_CONSTRAINT_CONFLICT",
                "Un vincolo concorrente impedisce il commit Production Planning.", exc,
            )
        except psycopg.Error as exc:
            raise _failure(
                "COMMIT_FAILED_ROLLED_BACK", "POSTGRESQL_COMMIT_FAILED",
                "Commit Production Planning non completato con rollback certo.", exc,
            )
        except Exception as exc:
            raise _failure(
                "INTERNAL_ERROR", "UNEXPECTED_COMMIT_FAILURE",
                "Failure interna del commit Production Planning.", exc,
            )
        finally:
            _cleanup(cursor, connection, rollback=not committed)

    def _read_compatible_replay(
        self, write_set: ProductionPlanningCommit
    ) -> ProductionPlanningResult:
        """Rilegge soltanto un winner già committed dopo una uniqueness race."""

        connection = self._connection_factory.connect()
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT state,completed_at,version
                   FROM tpo.production_planning_runs WHERE public_id=%s""",
                (write_set.run.public_id.value,),
            )
            run = cursor.fetchone()
            if run is None or run[0] != "COMMITTED" or run[1] is None:
                raise _conflict(
                    "IDEMPOTENCY_RACE_NOT_COMMITTED",
                    "La uniqueness race non corrisponde a una RUN committed.",
                )
            results: list[RevisionCommitResult] = []
            line_public_ids: list[Any] = []
            for draft in write_set.revisions:
                cursor.execute(
                    """SELECT r.public_id,p.public_id,r.numero_revisione
                       FROM tpo.piano_produzione_revisioni r
                       JOIN tpo.piani_produzione p ON p.id=r.piano_produzione_id
                       WHERE r.revision_request_key=%s""",
                    (draft.request_key.value,),
                )
                row = cursor.fetchone()
                if row != (
                    draft.revision_public_id.value, draft.plan_public_id.value,
                    draft.revision_number,
                ):
                    raise _conflict(
                        "REVISION_REPLAY_MISMATCH",
                        "Winner concorrente incompatibile con la revisione richiesta.",
                    )
                existing_lines = self._validate_replayed_revision(
                    cursor, draft, row[0], write_set.seed_resources
                )
                line_public_ids.extend(
                    line.public_id for line in draft.lines
                    if line.public_id.value in existing_lines
                )
                results.append(_revision_result(draft, reused=True))
            allocation_public_ids = tuple(
                item.public_id for item in write_set.allocations
            )
            if allocation_public_ids:
                cursor.execute(
                    "SELECT public_id FROM tpo.allocazioni WHERE public_id=ANY(%s) ORDER BY public_id",
                    ([item.value for item in allocation_public_ids],),
                )
                if tuple(row[0] for row in cursor.fetchall()) != tuple(
                    sorted(item.value for item in allocation_public_ids)
                ):
                    raise _conflict(
                        "ALLOCATION_REPLAY_MISMATCH",
                        "Winner concorrente privo delle allocazioni richieste.",
                    )
            connection.rollback()
            return ProductionPlanningResult(
                planning_run_public_id=write_set.run.public_id,
                run_state="COMMITTED",
                plan_public_ids=tuple(item.plan_public_id for item in results),
                current_revision_public_ids=tuple(
                    item.revision_public_id for item in results
                ),
                revision_results=tuple(results),
                planning_line_public_ids=tuple(line_public_ids),
                allocation_public_ids=allocation_public_ids,
                committed_at=run[1],
                warnings=tuple(
                    item for item in write_set.messages
                    if item.message_type == "WARNING"
                ),
            )
        finally:
            _cleanup(cursor, connection, rollback=True)

    def _execute(
        self, cursor: Any, write_set: ProductionPlanningCommit,
        persistence_at: datetime,
    ) -> ProductionPlanningResult:
        run_id = self._lock_run(cursor, write_set)
        policy_id = self._lock_policy(cursor, write_set)
        authority = self._lock_and_revalidate_inputs(cursor, write_set)
        plans = self._lock_plans(cursor, write_set)
        parents, compatible_transition_epochs = self._lock_allocations(
            cursor, write_set
        )
        self._lock_existing_planning_lines(cursor, write_set)
        self._validate_replacements(write_set)
        self._revalidate_allocation_capacity(write_set)

        (
            revision_results,
            line_ids,
            replayed_lines,
            persisted_line_public_ids,
        ) = self._persist_revisions(
            cursor, write_set, run_id, policy_id, authority, plans, persistence_at
        )
        allocation_ids, persisted_allocation_public_ids = self._persist_allocations(
            cursor, write_set.allocations, line_ids, authority, persistence_at,
            write_set.context.actor.value, compatible_transition_epochs,
            write_set.allocation_transitions, replayed_lines,
        )
        self._persist_transitions(
            cursor, write_set, parents, allocation_ids, persistence_at
        )
        self._persist_messages(cursor, run_id, write_set, persistence_at)
        self._persist_audits(cursor, run_id, write_set, persistence_at)
        self._complete_run(cursor, run_id, write_set, persistence_at)
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

        return ProductionPlanningResult(
            planning_run_public_id=write_set.run.public_id,
            run_state="COMMITTED",
            plan_public_ids=tuple(item.plan_public_id for item in revision_results),
            current_revision_public_ids=tuple(
                item.revision_public_id for item in revision_results
            ),
            revision_results=tuple(revision_results),
            planning_line_public_ids=tuple(
                persisted_line_public_ids.get(line.public_id.value, line.public_id)
                for revision in write_set.revisions for line in revision.lines
            ),
            allocation_public_ids=tuple(
                persisted_allocation_public_ids.get(item.public_id.value, item.public_id)
                for item in write_set.allocations
            ),
            committed_at=persistence_at,
            warnings=tuple(
                item for item in write_set.messages if item.message_type == "WARNING"
            ),
        )

    @staticmethod
    def _lock_run(cursor: Any, write_set: ProductionPlanningCommit) -> int:
        cursor.execute(
            """SELECT id,state,version,policy_version_id,business_at
               FROM tpo.production_planning_runs
               WHERE public_id=%s FOR UPDATE""",
            (write_set.run.public_id.value,),
        )
        row = cursor.fetchone()
        if row is None:
            raise _conflict("PLANNING_RUN_MISSING", "Planning RUN assente.")
        if (
            row[1] != "OPEN" or row[2] != write_set.run.expected_version
            or row[4] != write_set.business_at
        ):
            raise _conflict("PLANNING_RUN_CHANGED", "Planning RUN modificata.")
        return row[0]

    @staticmethod
    def _lock_policy(cursor: Any, write_set: ProductionPlanningCommit) -> int:
        cursor.execute(
            """SELECT id,numero_versione,valida_dal,valida_al,
                      buffer_quantitativo_tipo,buffer_quantitativo_valore,
                      priority_policy_code,planning_algorithm_version,
                      harvest_target_strategy
               FROM tpo.production_planning_policy_versions
               WHERE policy_set_code=%s AND numero_versione=%s FOR SHARE""",
            (write_set.policy.policy_set_code, write_set.policy.version),
        )
        row = cursor.fetchone()
        policy = write_set.input_snapshot.policy
        business_date = write_set.business_at.astimezone(OFFICIAL_TIMEZONE).date()
        if row is None or not (row[2] <= business_date and (row[3] is None or business_date < row[3])):
            raise _input("POLICY_NOT_VALID", "Planning policy assente o fuori validità.")
        observed = (row[4], row[5], row[6], row[7], row[8])
        expected = (
            policy.quantitative_buffer_type, policy.quantitative_buffer_value,
            policy.priority_policy_code, policy.algorithm_version,
            policy.harvest_target_strategy,
        )
        if observed != expected:
            raise _conflict("POLICY_CHANGED", "Planning policy modificata.")
        return row[0]

    def _lock_and_revalidate_inputs(
        self, cursor: Any, write_set: ProductionPlanningCommit
    ) -> dict[str, dict[str, tuple[Any, ...]]]:
        demands = {item.order_line_public_id.value: item for item in write_set.input_snapshot.demands}
        order_ids = sorted({item.order_public_id.value for item in demands.values()})
        cursor.execute(
            """SELECT id,public_id,stato,version FROM tpo.ordini
               WHERE public_id=ANY(%s) ORDER BY id FOR UPDATE""", (order_ids,),
        )
        orders = {row[1]: row for row in cursor.fetchall()}
        if set(orders) != set(order_ids):
            raise _input("ORDER_MISSING", "Uno o più ORDINI non esistono.")
        for demand in demands.values():
            row = orders[demand.order_public_id.value]
            if row[2] != demand.order_state.value or row[3] != demand.order_version:
                raise _conflict("ORDER_CHANGED", "ORDINE modificato dopo lo snapshot.")

        line_ids = sorted(demands)
        cursor.execute(
            """SELECT id,public_id,ordine_id,varieta_id,quantita,unita_misura,version
               FROM tpo.righe_ordine WHERE public_id=ANY(%s)
               ORDER BY id FOR UPDATE""", (line_ids,),
        )
        locked_lines = tuple(cursor.fetchall())
        locked_by_id = {row[0]: row for row in locked_lines}
        cursor.execute(
            """SELECT ro.id,
                      COALESCE(SUM(rc.quantita) FILTER (WHERE c.stato='CONSEGNATA'),0)::numeric(20,6)
               FROM tpo.righe_ordine ro
               LEFT JOIN tpo.righe_consegna rc ON rc.riga_ordine_id=ro.id
               LEFT JOIN tpo.consegne c ON c.id=rc.consegna_id
               WHERE ro.id=ANY(%s) GROUP BY ro.id ORDER BY ro.id""",
            (sorted(locked_by_id),),
        )
        delivered = {row[0]: row[1] for row in cursor.fetchall()}
        lines = {
            row[1]: (*row, delivered[row[0]]) for row in locked_lines
        }
        if set(lines) != set(line_ids):
            raise _input("ORDER_LINE_MISSING", "Una o più RIGHE_ORDINE non esistono.")
        for public_id, demand in demands.items():
            row = lines[public_id]
            if (
                row[2] != orders[demand.order_public_id.value][0]
                or row[6] != demand.order_line_version
                or Decimal(row[4]) != demand.ordered.value
                or row[5] != demand.ordered.unit.value
                or Decimal(row[7]) != demand.delivered.value
                or Decimal(row[4]) - Decimal(row[7]) != demand.commercial_residual.value
            ):
                raise _conflict(
                    "ORDER_LINE_FULFILMENT_CHANGED",
                    "Fulfilment o RIGA_ORDINE modificati dopo lo snapshot.",
                )

        varieties = sorted({item.variety_public_id.value for item in demands.values()})
        cursor.execute(
            "SELECT id,public_id FROM tpo.varieta WHERE public_id=ANY(%s) ORDER BY id FOR UPDATE",
            (varieties,),
        )
        variety_rows = {row[1]: row for row in cursor.fetchall()}
        if set(variety_rows) != set(varieties):
            raise _input("VARIETY_MISSING", "VARIETÀ Planning assente.")

        stock_ids = sorted({item.resource_public_id.value for item in write_set.input_snapshot.stock})
        stock_rows: dict[str, tuple[Any, ...]] = {}
        if stock_ids:
            cursor.execute(
                """SELECT v.public_id,s.varieta_id,s.disponibile,s.unita_misura,s.version
                   FROM tpo.stock s JOIN tpo.varieta v ON v.id=s.varieta_id
                   WHERE v.public_id=ANY(%s) ORDER BY s.varieta_id FOR UPDATE OF s""",
                (stock_ids,),
            )
            stock_rows = {row[0]: row for row in cursor.fetchall()}
            if set(stock_rows) != set(stock_ids):
                raise _input("STOCK_MISSING", "STOCK Planning assente.")
            for snapshot in write_set.input_snapshot.stock:
                row = stock_rows[snapshot.resource_public_id.value]
                if row[4] != snapshot.version or Decimal(row[2]) != snapshot.eligible.value or row[3] != snapshot.eligible.unit.value:
                    raise _conflict("STOCK_CHANGED", "STOCK modificato dopo lo snapshot.")

        semina_ids = sorted({item.semina_public_id.value for item in write_set.input_snapshot.in_progress})
        semine: dict[str, tuple[Any, ...]] = {}
        if semina_ids:
            cursor.execute(
                """SELECT s.id,s.public_id,s.stato,s.version,pv.public_id,
                          s.expected_useful_quantity,s.expected_useful_uom,
                          s.harvest_window_start,s.harvest_window_end
                   FROM tpo.semine s JOIN tpo.protocollo_versioni pv ON pv.id=s.protocollo_versione_id
                   WHERE s.public_id=ANY(%s) ORDER BY s.id FOR UPDATE OF s""",
                (semina_ids,),
            )
            semine = {row[1]: row for row in cursor.fetchall()}
            if set(semine) != set(semina_ids):
                raise _input("SEEDING_MISSING", "SEMINA Planning assente.")
            for snapshot in write_set.input_snapshot.in_progress:
                row = semine[snapshot.semina_public_id.value]
                if (
                    row[2] != snapshot.state.value
                    or row[3] != snapshot.version
                    or row[4] != snapshot.protocol_version_public_id.value
                    or row[5] is None
                    or Decimal(row[5]) != snapshot.expected_useful.value
                    or row[6] != snapshot.expected_useful.unit.value
                    or row[7] != snapshot.harvest_window_start
                    or row[8] != snapshot.harvest_window_end
                ):
                    raise _conflict("SEEDING_CHANGED", "SEMINA modificata dopo lo snapshot.")

        harvest_ids = sorted({item.harvest_public_id.value for item in write_set.input_snapshot.harvests})
        harvests: dict[str, tuple[Any, ...]] = {}
        if harvest_ids:
            cursor.execute(
                """SELECT r.id,r.public_id,s.public_id,r.data_raccolta,r.quantita,r.unita_misura
                   FROM tpo.raccolte r JOIN tpo.semine s ON s.id=r.semina_id
                   WHERE r.public_id=ANY(%s) ORDER BY r.id FOR SHARE OF r""", (harvest_ids,),
            )
            harvests = {row[1]: row for row in cursor.fetchall()}
            if set(harvests) != set(harvest_ids):
                raise _input("HARVEST_MISSING", "RACCOLTA Planning assente.")
            for snapshot in write_set.input_snapshot.harvests:
                row = harvests[snapshot.harvest_public_id.value]
                if row[2] != snapshot.semina_public_id.value or row[3] != snapshot.harvested_at or Decimal(row[4]) != snapshot.eligible.value or row[5] != snapshot.eligible.unit.value:
                    raise _conflict("HARVEST_CHANGED", "RACCOLTA incoerente con lo snapshot.")

        protocol_ids = sorted({item.protocol_version_public_id.value for item in write_set.input_snapshot.knowledge})
        protocols: dict[str, tuple[Any, ...]] = {}
        if protocol_ids:
            cursor.execute(
                """SELECT pv.id,pv.public_id,pv.numero_versione,pv.stato_approvazione,
                          pv.valida_dal,pv.valida_al,pv.idratazione_ore,
                          pv.orario_semina_previsto,pv.orario_raccolta_target,
                          pv.germinazione_giorni,pv.crescita_luce_giorni,
                          pv.grammi_seme_per_set,pv.resa_attesa,pv.resa_unita_misura,
                          pv.granularita_produttiva,pv.harvest_min_lead_giorni,
                          pv.harvest_max_lead_giorni,pv.buffer_temporale_minuti,
                          pv.provenance,c.id,c.denominazione,cu.id,up.codice,v.public_id
                   FROM tpo.protocollo_versioni pv
                   JOIN tpo.protocolli p ON p.id=pv.protocollo_id
                   JOIN tpo.cultivar_usi cu ON cu.id=p.cultivar_uso_id
                   JOIN tpo.cultivar c ON c.id=cu.cultivar_id
                   JOIN tpo.usi_produttivi up ON up.id=cu.uso_produttivo_id
                   JOIN tpo.varieta v ON v.id=c.varieta_id
                   WHERE pv.public_id=ANY(%s) ORDER BY pv.id FOR SHARE OF pv""",
                (protocol_ids,),
            )
            protocols = {row[1]: row for row in cursor.fetchall()}
            if set(protocols) != set(protocol_ids):
                raise _input("PROTOCOL_MISSING", "Protocollo Planning assente.")
            for snapshot in write_set.input_snapshot.knowledge:
                row = protocols[snapshot.protocol_version_public_id.value]
                observed = (
                    row[2], row[3], row[4], row[5], Decimal(row[6]), row[7], row[8],
                    row[9], row[10], Decimal(row[11]), Decimal(row[12]), row[13],
                    Decimal(row[14]), row[15], row[16], row[17], row[18], row[20],
                    row[22], row[23],
                )
                expected = (
                    snapshot.protocol_version_number, snapshot.approval_state,
                    snapshot.valid_from, snapshot.valid_to, snapshot.hydration_hours,
                    snapshot.planned_sowing_time, snapshot.target_harvest_time,
                    snapshot.germination_days, snapshot.light_growth_days,
                    snapshot.seed_grams_per_set, snapshot.expected_yield.value,
                    snapshot.expected_yield.unit.value, snapshot.production_granularity,
                    snapshot.harvest_min_lead_days, snapshot.harvest_max_lead_days,
                    snapshot.temporal_buffer_minutes, snapshot.provenance,
                    snapshot.cultivar_reference, snapshot.productive_use_reference,
                    snapshot.variety_public_id.value,
                )
                if observed != expected or row[3] != "APPROVATA":
                    raise _knowledge("PROTOCOL_CHANGED", "Protocollo modificato dopo lo snapshot.")

        return {
            "orders": orders, "lines": lines, "varieties": variety_rows,
            "stock": stock_rows, "semine": semine, "harvests": harvests,
            "protocols": protocols,
        }

    @staticmethod
    def _lock_plans(cursor: Any, write_set: ProductionPlanningCommit) -> dict[str, tuple[Any, ...]]:
        replans = [item for item in write_set.revisions if item.revision_number > 1]
        if not replans:
            return {}
        ids = sorted(item.plan_public_id.value for item in replans)
        cursor.execute(
            """SELECT p.id,p.public_id,p.current_revision_id,p.stato_complessivo,p.version,
                      r.public_id,r.numero_revisione,r.version
               FROM tpo.piani_produzione p
               JOIN tpo.piano_produzione_revisioni r ON r.id=p.current_revision_id
               WHERE p.public_id=ANY(%s) ORDER BY p.id FOR UPDATE OF p,r""", (ids,),
        )
        plans = {row[1]: row for row in cursor.fetchall()}
        if set(plans) != set(ids):
            raise _conflict("CURRENT_PLAN_MISSING", "Piano corrente assente.")
        for draft in replans:
            row = plans[draft.plan_public_id.value]
            if (
                row[4] != draft.expected_plan_version
                or row[5] != draft.previous_revision_public_id.value
                or row[6] != draft.revision_number - 1
                or row[7] != draft.expected_current_revision_version
            ):
                raise _conflict("CURRENT_REVISION_CHANGED", "Revisione corrente modificata.")
        return plans

    @staticmethod
    def _lock_allocations(
        cursor: Any, write_set: ProductionPlanningCommit,
    ) -> tuple[dict[str, tuple[Any, ...]], set[str]]:
        ids = sorted({
            item.allocation_public_id.value
            for item in write_set.allocation_transitions
        } | {
            item.allocation_public_id.value
            for item in write_set.input_snapshot.allocations
        })
        if not ids:
            return {}, set()
        cursor.execute(
            """SELECT id,public_id,allocation_type,riga_piano_semina_id,quantity,
                      unita_misura,state,version
               FROM tpo.allocazioni WHERE public_id=ANY(%s)
               ORDER BY id FOR UPDATE""", (ids,),
        )
        parents = {row[1]: row for row in cursor.fetchall()}
        if set(parents) != set(ids):
            raise _allocation("ALLOCATION_MISSING", "Allocazione parent assente.")
        parent_pks = [parents[item][0] for item in ids]
        for allocation_type in ("DOMANDA", "STOCK", "PRODUZIONE_IN_CORSO", "RACCOLTA"):
            table, _, _ = _CHILDREN[allocation_type]
            cursor.execute(
                f"SELECT allocation_id FROM tpo.{table} WHERE allocation_id=ANY(%s) ORDER BY allocation_id FOR UPDATE",
                (parent_pks,),
            )
            cursor.fetchall()
        compatible_epochs: set[str] = set()
        for draft in write_set.allocation_transitions:
            parent = parents[draft.allocation_public_id.value]
            cursor.execute(
                """SELECT t.transition_type,t.quantity,replacement.public_id,
                          t.reason,t.provenance
                   FROM tpo.transizioni_allocazione t
                   LEFT JOIN tpo.allocazioni replacement
                     ON replacement.id=t.replacement_allocation_id
                   WHERE t.allocation_id=%s
                     AND t.expected_allocation_version=%s
                   ORDER BY t.transition_type,t.id""",
                (parent[0], draft.expected_version),
            )
            existing_epoch = tuple(cursor.fetchall())
            replacement_public_id = (
                draft.replacement_allocation_public_id.value
                if draft.replacement_allocation_public_id is not None else None
            )
            if existing_epoch:
                if existing_epoch != _transition_facts(
                    draft, replacement_public_id
                ):
                    raise _allocation(
                        "ALLOCATION_REPLAY_MISMATCH",
                        "Epoch allocazione già committed con payload incompatibile.",
                    )
                compatible_epochs.add(draft.allocation_public_id.value)
        cursor.execute(
            """SELECT a.public_id,a.allocation_type,
                      CASE a.allocation_type
                        WHEN 'DOMANDA' THEN ro.public_id
                        WHEN 'STOCK' THEN vs.public_id
                        WHEN 'PRODUZIONE_IN_CORSO' THEN s.public_id
                        WHEN 'RACCOLTA' THEN r.public_id END AS source_public_id,
                      destination.public_id,
                      COALESCE(SUM(t.quantity) FILTER (WHERE t.transition_type='CONSUMATA'),0),
                      COALESCE(SUM(t.quantity) FILTER (WHERE t.transition_type='RILASCIATA'),0),
                      COALESCE(SUM(t.quantity) FILTER (WHERE t.transition_type='SOSTITUITA'),0),
                      COALESCE(SUM(t.quantity) FILTER (WHERE t.transition_type='INVALIDA'),0)
               FROM tpo.allocazioni a
               JOIN tpo.righe_piano_semina rps ON rps.id=a.riga_piano_semina_id
               JOIN tpo.righe_ordine destination ON destination.id=rps.riga_ordine_id
               LEFT JOIN tpo.allocazioni_domanda ad ON ad.allocation_id=a.id
               LEFT JOIN tpo.righe_ordine ro ON ro.id=ad.riga_ordine_id
               LEFT JOIN tpo.allocazioni_stock ast ON ast.allocation_id=a.id
               LEFT JOIN tpo.varieta vs ON vs.id=ast.stock_varieta_id
               LEFT JOIN tpo.allocazioni_produzione_in_corso ap ON ap.allocation_id=a.id
               LEFT JOIN tpo.semine s ON s.id=ap.semina_id
               LEFT JOIN tpo.allocazioni_raccolta ar ON ar.allocation_id=a.id
               LEFT JOIN tpo.raccolte r ON r.id=ar.raccolta_id
               LEFT JOIN tpo.transizioni_allocazione t ON t.allocation_id=a.id
               WHERE a.public_id=ANY(%s)
               GROUP BY a.id,ro.public_id,vs.public_id,s.public_id,r.public_id,
                        destination.public_id ORDER BY a.id""", (ids,),
        )
        material = {row[0]: row for row in cursor.fetchall()}
        snapshots = {
            item.allocation_public_id.value: item
            for item in write_set.input_snapshot.allocations
        }
        for public_id, snapshot in snapshots.items():
            if public_id in compatible_epochs:
                continue
            parent = parents[public_id]
            row = material.get(public_id)
            if row is None:
                raise _allocation("ALLOCATION_CHILD_MISSING", "Child allocazione assente.")
            balances = tuple(map(Decimal, row[4:8]))
            remaining = Decimal(parent[4]) - sum(balances)
            if (
                row[1] != snapshot.allocation_type
                or row[2] != snapshot.source_public_id.value
                or row[3] != snapshot.destination_order_line_public_id.value
                or Decimal(parent[4]) != snapshot.allocated_quantity.value
                or parent[5] != snapshot.allocated_quantity.unit.value
                or parent[6] != snapshot.state or parent[7] != snapshot.version
                or balances != (
                    snapshot.consumed_quantity.value,
                    snapshot.released_quantity.value,
                    snapshot.transferred_quantity.value,
                    snapshot.invalidated_quantity.value,
                )
                or remaining != snapshot.remaining_quantity.value
            ):
                raise _allocation(
                    "ALLOCATION_SNAPSHOT_CHANGED",
                    "Allocazione materialmente rilevante modificata.",
                )
        replacement_ids = sorted(
            item.replacement_allocation_public_id.value
            for item in write_set.allocation_transitions
            if item.replacement_allocation_public_id is not None
        )
        if replacement_ids:
            cursor.execute(
                "SELECT id,public_id FROM tpo.allocazioni WHERE public_id=ANY(%s) ORDER BY id FOR UPDATE",
                (replacement_ids,),
            )
            existing = cursor.fetchall()
            replay_replacement_ids = {
                item.replacement_allocation_public_id.value
                for item in write_set.allocation_transitions
                if (
                    item.allocation_public_id.value in compatible_epochs
                    and item.replacement_allocation_public_id is not None
                )
            }
            if any(row[1] not in replay_replacement_ids for row in existing):
                raise _allocation("REPLACEMENT_ALREADY_EXISTS", "Replacement allocation già esistente.")
        return parents, compatible_epochs

    @staticmethod
    def _lock_existing_planning_lines(cursor: Any, write_set: ProductionPlanningCommit) -> None:
        line_ids = sorted(
            item.planning_line_public_id.value
            for item in write_set.input_snapshot.current_planning_lines
        )
        if not line_ids:
            return
        cursor.execute(
            """SELECT public_id,stato,version FROM tpo.righe_piano_semina
               WHERE public_id=ANY(%s) ORDER BY id FOR UPDATE""", (line_ids,),
        )
        observed = {row[0]: row for row in cursor.fetchall()}
        if set(observed) != set(line_ids):
            raise _conflict("PLANNING_LINE_MISSING", "Riga Planning corrente assente.")
        for snapshot in write_set.input_snapshot.current_planning_lines:
            row = observed[snapshot.planning_line_public_id.value]
            if row[1] != snapshot.state or row[2] != snapshot.version:
                raise _conflict("PLANNING_LINE_CHANGED", "Riga Planning corrente modificata.")

    @staticmethod
    def _revalidate_allocation_capacity(write_set: ProductionPlanningCommit) -> None:
        lines = {
            line.public_id.value: line
            for revision in write_set.revisions for line in revision.lines
        }
        demands = {
            item.order_line_public_id.value: item
            for item in write_set.input_snapshot.demands
        }
        resources: dict[tuple[str, str], tuple[Decimal, str]] = {}
        for item in write_set.input_snapshot.stock:
            resources[("STOCK", item.resource_public_id.value)] = (
                item.allocable_residual.value, item.allocable_residual.unit.value,
            )
        for item in write_set.input_snapshot.in_progress:
            resources[("PRODUZIONE_IN_CORSO", item.semina_public_id.value)] = (
                item.allocable_residual.value, item.allocable_residual.unit.value,
            )
        for item in write_set.input_snapshot.harvests:
            resources[("RACCOLTA", item.harvest_public_id.value)] = (
                item.allocable_residual.value, item.allocable_residual.unit.value,
            )
        for item in demands.values():
            resources[("DOMANDA", item.order_line_public_id.value)] = (
                item.commercial_residual.value, item.commercial_residual.unit.value,
            )
        replacements = {
            item.replacement_allocation_public_id.value
            for item in write_set.allocation_transitions
            if item.replacement_allocation_public_id is not None
        }
        totals: dict[tuple[str, str], Decimal] = {}
        for draft in write_set.allocations:
            line = lines.get(draft.planning_line_public_id.value)
            if line is None or (
                line.candidate.demand.order_line_public_id
                != draft.destination_order_line_public_id
            ):
                raise _allocation(
                    "ALLOCATION_DESTINATION_MISMATCH",
                    "Destinazione della nuova allocazione incoerente.",
                )
            key = (draft.allocation_type, draft.source_public_id.value)
            limit = resources.get(key)
            if limit is None or limit[1] != draft.quantity.unit.value:
                raise _allocation(
                    "ALLOCATION_SOURCE_MISMATCH",
                    "Sorgente o UOM della nuova allocazione incoerente.",
                )
            if draft.public_id.value in replacements:
                continue
            totals[key] = totals.get(key, Decimal(0)) + draft.quantity.value
            if totals[key] > limit[0]:
                raise _allocation(
                    "ALLOCATION_CAPACITY_EXCEEDED",
                    "Nuove allocazioni superano il residuo autorevole.",
                )

    @staticmethod
    def _validate_replacements(write_set: ProductionPlanningCommit) -> None:
        allocations = {item.public_id.value: item for item in write_set.allocations}
        snapshots = {
            item.allocation_public_id.value: item
            for item in write_set.input_snapshot.allocations
        }
        used: set[str] = set()
        for transition in write_set.allocation_transitions:
            replacement_id = transition.replacement_allocation_public_id
            if replacement_id is None:
                continue
            replacement = allocations.get(replacement_id.value)
            parent = snapshots.get(transition.allocation_public_id.value)
            if replacement is None or parent is None:
                raise _allocation(
                    "REPLACEMENT_WRITE_SET_INCOMPLETE",
                    "Replacement allocation o parent snapshot mancanti.",
                )
            if replacement_id.value in used:
                raise _allocation(
                    "REPLACEMENT_REUSED", "Replacement allocation condivisa."
                )
            used.add(replacement_id.value)
            if (
                replacement.quantity.value != transition.transferred_quantity_delta
                or replacement.quantity.unit != parent.allocated_quantity.unit
                or replacement.allocation_type != parent.allocation_type
                or replacement.source_public_id != parent.source_public_id
            ):
                raise _allocation(
                    "REPLACEMENT_MISMATCH",
                    "Replacement allocation incoerente con il transfer.",
                )

    def _persist_revisions(
        self, cursor: Any, write_set: ProductionPlanningCommit, run_id: int,
        policy_id: int, authority: dict[str, dict[str, tuple[Any, ...]]],
        plans: dict[str, tuple[Any, ...]], persistence_at: datetime,
    ) -> tuple[
        list[RevisionCommitResult], dict[str, int], set[str], dict[str, Any]
    ]:
        results: list[RevisionCommitResult] = []
        line_ids: dict[str, int] = {}
        replayed_lines: set[str] = set()
        persisted_line_public_ids: dict[str, Any] = {}
        actor = write_set.context.actor.value
        for draft in write_set.revisions:
            cursor.execute(
                """SELECT r.public_id,p.public_id,r.revision_request_key,r.numero_revisione
                   FROM tpo.piano_produzione_revisioni r
                   JOIN tpo.piani_produzione p ON p.id=r.piano_produzione_id
                   WHERE r.revision_request_key=%s""", (draft.request_key.value,),
            )
            replay = cursor.fetchone()
            if replay is not None:
                if replay[2:] != (draft.request_key.value, draft.revision_number):
                    raise _conflict(
                        "REVISION_REPLAY_MISMATCH",
                        "Revision request key già associata a un payload incompatibile.",
                    )
                replayed = self._validate_replayed_revision(
                    cursor, draft, replay[0], write_set.seed_resources
                )
                for draft_id, (line_pk, persisted_id) in replayed.items():
                    line_ids[draft_id] = line_pk
                    replayed_lines.add(draft_id)
                    persisted_line_public_ids[draft_id] = type(draft.plan_public_id)(
                        persisted_id
                    )
                results.append(_revision_result(
                    draft,
                    reused=True,
                    plan_public_id=type(draft.plan_public_id)(replay[1]),
                    revision_public_id=type(draft.revision_public_id)(replay[0]),
                ))
                continue

            if draft.revision_number == 1:
                cursor.execute(
                    """INSERT INTO tpo.piani_produzione
                       (public_id,current_revision_id,stato_complessivo,created_at,
                        created_by,updated_at,updated_by,version)
                       VALUES (%s,NULL,%s,%s,%s,%s,%s,0) RETURNING id""",
                    (draft.plan_public_id.value, draft.plan_state, persistence_at,
                     actor, persistence_at, actor),
                )
                plan_id = cursor.fetchone()[0]
                previous_id = None
                snapshot_id = None
            else:
                plan_id = plans[draft.plan_public_id.value][0]
                previous_id = plans[draft.plan_public_id.value][2]
                assert draft.canonical_replanning_snapshot is not None
                snapshot_id = self._persist_replanning_snapshot(
                    cursor, draft.canonical_replanning_snapshot, authority,
                    persistence_at, actor,
                )

            cursor.execute(
                """INSERT INTO tpo.piano_produzione_revisioni
                   (public_id,piano_produzione_id,planning_run_id,numero_revisione,
                    revisione_precedente_id,policy_version_id,business_at,
                    replanning_reason_code,revision_request_key,replanning_snapshot_id,
                    created_at,created_by,version)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
                   RETURNING id""",
                (draft.revision_public_id.value, plan_id, run_id,
                 draft.revision_number, previous_id, policy_id, write_set.business_at,
                 draft.replanning_reason_code, draft.request_key.value, snapshot_id,
                 persistence_at, actor),
            )
            revision_id = cursor.fetchone()[0]
            for line in draft.lines:
                demand = line.candidate.demand
                protocol = authority["protocols"][
                    line.candidate.knowledge.protocol_version_public_id.value
                ]
                cursor.execute(
                    """INSERT INTO tpo.righe_piano_semina
                       (public_id,piano_revisione_id,riga_ordine_id,varieta_id,
                        cultivar_id,cultivar_uso_id,protocollo_versione_id,
                        ordine_version_attesa,riga_ordine_version_attesa,
                        varieta_public_id_snapshot,cultivar_snapshot,
                        uso_produttivo_snapshot,domanda_originaria,
                        quantita_consegnata_snapshot,domanda_residua_commerciale,
                        copertura_stock,copertura_produzione_in_corso,
                        copertura_raccolta_allocata,deficit_produttivo,
                        buffer_quantitativo_tipo,buffer_quantitativo_valore,
                        buffer_quantitativo_calcolato,quantita_pre_granularita,
                        granularita_produttiva,quantita_produttiva_autorizzata,
                        quantita_avviata,quantita_residua_da_avviare,resa_attesa,
                        resa_unita_misura,grammi_seme_richiesti,unita_domanda,
                        data_consegna,harvest_window_start,harvest_window_end,
                        harvest_target_at,sowing_at,light_at,hydration_at,timezone,
                        orario_semina_snapshot,orario_raccolta_snapshot,
                        buffer_temporale_minuti,stato,planning_key,provenance,
                        created_at,created_by,updated_at,updated_by,version)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                               %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,
                               %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                               %s,%s,%s,%s,0) RETURNING id""",
                    (
                        line.public_id.value, revision_id,
                        authority["lines"][demand.order_line_public_id.value][0],
                        authority["varieties"][demand.variety_public_id.value][0],
                        protocol[19], protocol[21], protocol[0],
                        line.expected_order_version, line.expected_order_line_version,
                        demand.variety_public_id.value,
                        line.candidate.knowledge.cultivar_reference,
                        line.candidate.knowledge.productive_use_reference,
                        demand.ordered.value, demand.delivered.value,
                        demand.commercial_residual.value, line.stock_coverage.value,
                        line.in_progress_coverage.value,
                        line.allocated_harvest_coverage.value,
                        line.production_deficit.value, line.quantitative_buffer_type,
                        line.quantitative_buffer_value,
                        line.calculated_quantitative_buffer,
                        line.pre_granularity_quantity,
                        line.candidate.knowledge.production_granularity,
                        line.authorized_productive_quantity.value,
                        line.remaining_to_start.value,
                        line.candidate.knowledge.expected_yield.value,
                        line.candidate.knowledge.expected_yield.unit.value,
                        (
                            line.authorized_productive_quantity.value
                            * line.candidate.knowledge.seed_grams_per_set
                            if line.authorized_productive_quantity.value > 0
                            else None
                        ),
                        demand.ordered.unit.value, demand.delivery_date,
                        line.harvest_window_start, line.harvest_window_end,
                        line.candidate.harvest_target_at, line.candidate.sowing_at,
                        line.candidate.light_at, line.candidate.hydration_at,
                        OFFICIAL_TIMEZONE_NAME,
                        line.candidate.knowledge.planned_sowing_time,
                        line.candidate.knowledge.target_harvest_time,
                        line.candidate.knowledge.temporal_buffer_minutes, line.state,
                        line.planning_key.value, line.candidate.provenance,
                        persistence_at, actor, persistence_at, actor,
                    ),
                )
                line_ids[line.public_id.value] = cursor.fetchone()[0]

            resources = {
                item.planning_line_public_id.value: item
                for item in write_set.seed_resources
                if item.planning_line_public_id.value in line_ids
            }
            for line in draft.lines:
                resource = resources.get(line.public_id.value)
                productive = line.authorized_productive_quantity.value
                if productive == 0:
                    if resource is not None:
                        raise _input(
                            "SEED_RESOURCE_UNEXPECTED",
                            "Risorsa seme vietata per una riga a produzione zero.",
                        )
                    continue
                if resource is None:
                    raise _input(
                        "SEED_RESOURCE_MISSING", "Risorsa seme pianificata mancante."
                    )
                protocol = authority["protocols"][
                    line.candidate.knowledge.protocol_version_public_id.value
                ]
                cursor.execute(
                    """INSERT INTO tpo.risorse_seme_pianificate
                       (riga_piano_semina_id,cultivar_uso_id,protocollo_versione_id,
                        grammi_richiesti,grammi_seme_per_set,unita_misura,
                        created_at,created_by)
                       VALUES (%s,%s,%s,%s,%s,'GRAM',%s,%s)""",
                    (line_ids[line.public_id.value], protocol[21], protocol[0],
                     resource.required_grams, resource.grams_per_set,
                     persistence_at, actor),
                )

            cursor.execute(
                """UPDATE tpo.piani_produzione
                   SET current_revision_id=%s,stato_complessivo=%s,updated_at=%s,
                       updated_by=%s,version=version+1
                   WHERE id=%s AND version=%s RETURNING version""",
                (revision_id, draft.plan_state, persistence_at, actor, plan_id,
                 0 if draft.revision_number == 1 else draft.expected_plan_version),
            )
            if cursor.fetchone() is None:
                raise _conflict("PLAN_CAS_FAILED", "CAS del piano fallita.")
            if previous_id is not None:
                cursor.execute(
                    """UPDATE tpo.piano_produzione_revisioni
                       SET sostituita_at=%s,sostituita_by=%s,version=version+1
                       WHERE id=%s AND version=%s AND sostituita_at IS NULL""",
                    (persistence_at, actor, previous_id,
                     draft.expected_current_revision_version),
                )
                if cursor.rowcount != 1:
                    raise _conflict(
                        "REVISION_CAS_FAILED", "CAS della revisione corrente fallita."
                    )
            results.append(_revision_result(draft, reused=False))
        return results, line_ids, replayed_lines, persisted_line_public_ids

    @staticmethod
    def _validate_replayed_revision(
        cursor: Any, draft: PlanRevisionDraft, public_id: str,
        seed_resources: tuple[Any, ...],
    ) -> dict[str, tuple[int, str]]:
        cursor.execute(
            """SELECT rps.public_id,rps.planning_key,rps.id,
                      rps.quantita_produttiva_autorizzata,
                      rps.grammi_seme_richiesti
               FROM tpo.piano_produzione_revisioni r
               JOIN tpo.righe_piano_semina rps ON rps.piano_revisione_id=r.id
               WHERE r.public_id=%s ORDER BY rps.planning_key""", (public_id,),
        )
        observed = tuple(cursor.fetchall())
        expected = tuple(sorted(
            (
                line.planning_key.value,
                line.authorized_productive_quantity.value,
                (
                    line.authorized_productive_quantity.value
                    * line.candidate.knowledge.seed_grams_per_set
                    if line.authorized_productive_quantity.value > 0
                    else None
                ),
            )
            for line in draft.lines
        ))
        if tuple((row[1], row[3], row[4]) for row in observed) != expected:
            raise _conflict(
                "REVISION_REPLAY_MISMATCH",
                "Revisione committed incompatibile con il replay.",
            )
        resources = {item.planning_line_public_id.value: item for item in seed_resources}
        lines = {line.planning_key.value: line for line in draft.lines}
        for line_public_id, planning_key, line_id, _, _ in observed:
            cursor.execute(
                """SELECT grammi_richiesti,grammi_seme_per_set,unita_misura
                   FROM tpo.risorse_seme_pianificate
                   WHERE riga_piano_semina_id=%s""",
                (line_id,),
            )
            children = tuple(cursor.fetchall())
            line = lines[planning_key]
            resource = resources.get(line.public_id.value)
            if line.authorized_productive_quantity.value == 0:
                if children or resource is not None:
                    raise _conflict(
                        "REVISION_REPLAY_MISMATCH",
                        "Replay a produzione zero con risorsa seme incompatibile.",
                    )
                continue
            if resource is None or children != ((
                resource.required_grams, resource.grams_per_set, "GRAM",
            ),):
                raise _conflict(
                    "REVISION_REPLAY_MISMATCH",
                    "Replay produttivo privo della risorsa seme compatibile.",
                )
        return {
            lines[row[1]].public_id.value: (row[2], row[0])
            for row in observed
        }

    @staticmethod
    def _persist_replanning_snapshot(
        cursor: Any, snapshot: CanonicalReplanningSnapshot,
        authority: dict[str, dict[str, tuple[Any, ...]]], persistence_at: datetime,
        actor: str,
    ) -> int:
        cursor.execute(
            """INSERT INTO tpo.replanning_snapshots
               (order_line_public_id,order_public_id,order_state,order_version,
                order_line_version,ordered_quantity,delivered_quantity,
                commercial_residual_quantity,delivery_date,variety_public_id,
                protocol_version_public_id,protocol_version_number,
                protocol_valid_from,protocol_valid_to,policy_set_code,
                planning_policy_version,quantitative_buffer_policy_type,
                quantitative_buffer_policy_value,temporal_buffer_minutes,
                production_granularity,previous_plan_revision_public_id,
                previous_plan_revision_version,replanning_reason_code,
                disposition_set_key,canonical_text,canonical_hash,created_at,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                       %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (
                snapshot.order_line_public_id.value, snapshot.order_public_id.value,
                snapshot.order_state.value, snapshot.order_version,
                snapshot.order_line_version, snapshot.ordered_quantity.value,
                snapshot.delivered_quantity.value,
                snapshot.commercial_residual_quantity.value, snapshot.delivery_date,
                snapshot.variety_public_id.value,
                snapshot.protocol_version_public_id.value,
                snapshot.protocol_version_number, snapshot.protocol_valid_from,
                snapshot.protocol_valid_to, snapshot.policy.policy_set_code,
                snapshot.policy.version, snapshot.quantitative_buffer_type,
                snapshot.quantitative_buffer_value, snapshot.temporal_buffer_minutes,
                snapshot.production_granularity,
                snapshot.previous_revision_public_id.value,
                snapshot.previous_plan_revision_version, snapshot.reason_code,
                snapshot.decision_set_key.value,
                snapshot.canonical_text, snapshot.canonical_snapshot_hash.value,
                persistence_at, actor,
            ),
        )
        snapshot_id = cursor.fetchone()[0]
        for position, item in enumerate(snapshot.stock, 1):
            cursor.execute(
                """INSERT INTO tpo.replanning_snapshot_stock
                   (snapshot_id,posizione,stock_resource_public_id,variety_public_id,
                    eligible_quantity,allocated_quantity,allocable_residual,
                    resource_version)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (snapshot_id, position, item.resource_public_id.value,
                 item.variety_public_id.value, item.eligible.value,
                 item.allocated.value, item.allocable_residual.value,
                 item.version),
            )
        for position, item in enumerate(snapshot.in_progress, 1):
            cursor.execute(
                """INSERT INTO tpo.replanning_snapshot_semine
                   (snapshot_id,posizione,semina_public_id,variety_public_id,
                    protocol_version_public_id,expected_useful_quantity,
                    allocated_quantity,allocable_residual,harvest_window_start,
                    harvest_window_end,semina_state,semina_version)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (snapshot_id, position, item.semina_public_id.value,
                 item.variety_public_id.value,
                 item.protocol_version_public_id.value,
                 item.expected_useful.value, item.allocated.value,
                 item.allocable_residual.value, item.harvest_window_start,
                 item.harvest_window_end, item.state.value, item.version),
            )
        for position, item in enumerate(snapshot.allocations, 1):
            cursor.execute(
                """INSERT INTO tpo.replanning_snapshot_allocazioni
                   (snapshot_id,posizione,allocation_public_id,allocation_type,
                    source_public_id,destination_order_line_public_id,
                    allocated_quantity,consumed_quantity,released_quantity,
                    transferred_quantity,invalidated_quantity,remaining_quantity,
                    unita_misura,allocation_state,allocation_version)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (snapshot_id, position, item.allocation_public_id.value,
                 item.allocation_type, item.source_public_id.value,
                 item.destination_order_line_public_id.value,
                 item.allocated_quantity.value, item.consumed_quantity.value,
                 item.released_quantity.value, item.transferred_quantity.value,
                 item.invalidated_quantity.value, item.remaining_quantity.value,
                 item.allocated_quantity.unit.value, item.state, item.version),
            )
        return snapshot_id

    @staticmethod
    def _persist_allocations(
        cursor: Any, drafts: tuple[AllocationDraft, ...], line_ids: dict[str, int],
        authority: dict[str, dict[str, tuple[Any, ...]]], persistence_at: datetime,
        actor: str, compatible_transition_epochs: set[str],
        transitions: tuple[AllocationTransitionDraft, ...], replayed_lines: set[str],
    ) -> tuple[dict[str, int], dict[str, Any]]:
        result: dict[str, int] = {}
        persisted_public_ids: dict[str, Any] = {}
        replay_transitions = {
            item.allocation_public_id.value: item
            for item in transitions
            if item.allocation_public_id.value in compatible_transition_epochs
        }
        new_replacement_ids = {
            item.replacement_allocation_public_id.value
            for item in transitions
            if (
                item.replacement_allocation_public_id is not None
                and item.allocation_public_id.value not in compatible_transition_epochs
            )
        }
        for draft in drafts:
            line_id = line_ids.get(draft.planning_line_public_id.value)
            if line_id is None:
                raise _input(
                    "ALLOCATION_LINE_MISSING",
                    "Nuova allocazione riferita a una riga non persistita.",
                )
            cursor.execute(
                """SELECT id,allocation_type,riga_piano_semina_id,quantity,
                          unita_misura,state,version
                   FROM tpo.allocazioni WHERE public_id=%s""",
                (draft.public_id.value,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                expected_material = (
                    draft.allocation_type, line_id, draft.quantity.value,
                    draft.quantity.unit.value,
                )
                replay_transition = replay_transitions.get(draft.public_id.value)
                if replay_transition is None:
                    expected_state = draft.state
                    version_compatible = True
                else:
                    expected_state = replay_transition.target_state
                    version_compatible = (
                        existing[6] == replay_transition.expected_version + 1
                    )
                if (
                    tuple(existing[1:5]) != expected_material
                    or existing[5] != expected_state
                    or not version_compatible
                ):
                    raise _allocation(
                        "ALLOCATION_REPLAY_MISMATCH",
                        "Allocazione committed incompatibile con il replay.",
                    )
                table, column, _ = _CHILDREN[draft.allocation_type]
                source_id = _allocation_source_id(cursor, draft, authority)
                cursor.execute(
                    f"SELECT {column} FROM tpo.{table} WHERE allocation_id=%s",
                    (existing[0],),
                )
                child = cursor.fetchone()
                if child != (source_id,):
                    raise _allocation(
                        "ALLOCATION_REPLAY_MISMATCH",
                        "Child allocazione committed incompatibile con il replay.",
                    )
                result[draft.public_id.value] = existing[0]
                continue
            if (
                draft.planning_line_public_id.value in replayed_lines
                and draft.public_id.value not in new_replacement_ids
            ):
                source_id = _allocation_source_id(cursor, draft, authority)
                table, column, _ = _CHILDREN[draft.allocation_type]
                cursor.execute(
                    f"""SELECT a.id,a.public_id
                         FROM tpo.allocazioni a
                         JOIN tpo.{table} child ON child.allocation_id=a.id
                         WHERE a.riga_piano_semina_id=%s
                           AND a.allocation_type=%s AND a.quantity=%s
                           AND a.unita_misura=%s AND a.state=%s
                           AND child.{column}=%s
                         ORDER BY a.public_id""",
                    (line_id, draft.allocation_type, draft.quantity.value,
                     draft.quantity.unit.value, draft.state, source_id),
                )
                matches = tuple(cursor.fetchall())
                if len(matches) != 1:
                    raise _allocation(
                        "ALLOCATION_REPLAY_MISMATCH",
                        "Allocazione committed incompatibile con il replay.",
                    )
                result[draft.public_id.value] = matches[0][0]
                persisted_public_ids[draft.public_id.value] = type(draft.public_id)(
                    matches[0][1]
                )
                continue
            cursor.execute(
                """INSERT INTO tpo.allocazioni
                   (public_id,allocation_type,riga_piano_semina_id,quantity,
                    unita_misura,state,created_at,created_by,updated_at,updated_by,version)
                   VALUES (%s,%s,%s,%s,%s,'ATTIVA',%s,%s,%s,%s,0) RETURNING id""",
                (draft.public_id.value, draft.allocation_type, line_id,
                 draft.quantity.value, draft.quantity.unit.value, persistence_at,
                 actor, persistence_at, actor),
            )
            allocation_id = cursor.fetchone()[0]
            result[draft.public_id.value] = allocation_id
            table, column, _ = _CHILDREN[draft.allocation_type]
            source_id = _allocation_source_id(cursor, draft, authority)
            cursor.execute(
                f"INSERT INTO tpo.{table} (allocation_id,{column}) VALUES (%s,%s)",
                (allocation_id, source_id),
            )
        return result, persisted_public_ids

    @staticmethod
    def _persist_transitions(
        cursor: Any, write_set: ProductionPlanningCommit,
        parents: dict[str, tuple[Any, ...]], new_allocations: dict[str, int],
        persistence_at: datetime,
    ) -> None:
        actor = write_set.context.actor.value
        for draft in write_set.allocation_transitions:
            parent = parents[draft.allocation_public_id.value]
            cursor.execute(
                """SELECT transition_type,quantity,replacement_allocation_id,
                          reason,provenance
                   FROM tpo.transizioni_allocazione
                   WHERE allocation_id=%s AND expected_allocation_version=%s
                   ORDER BY transition_type,id""",
                (parent[0], draft.expected_version),
            )
            existing = tuple(cursor.fetchall())
            replacement_id = (
                new_allocations[draft.replacement_allocation_public_id.value]
                if draft.replacement_allocation_public_id is not None else None
            )
            expected_facts = _transition_facts(draft, replacement_id)
            if existing:
                if existing != expected_facts:
                    raise _allocation(
                        "ALLOCATION_REPLAY_MISMATCH",
                        "Epoch allocazione già committed con payload incompatibile.",
                    )
                continue
            if parent[6] != draft.current_state or parent[7] != draft.expected_version:
                raise _allocation(
                    "ALLOCATION_VERSION_CHANGED",
                    "Stato o versione allocazione modificati.",
                )
            cursor.execute(
                """SELECT
                     COALESCE(SUM(quantity) FILTER (WHERE transition_type='CONSUMATA'),0),
                     COALESCE(SUM(quantity) FILTER (WHERE transition_type='RILASCIATA'),0),
                     COALESCE(SUM(quantity) FILTER (WHERE transition_type='SOSTITUITA'),0),
                     COALESCE(SUM(quantity) FILTER (WHERE transition_type='INVALIDA'),0)
                   FROM tpo.transizioni_allocazione WHERE allocation_id=%s""",
                (parent[0],),
            )
            consumed, released, transferred, invalidated = map(
                Decimal, cursor.fetchone()
            )
            observed = (
                Decimal(parent[4]), consumed, released, transferred, invalidated,
                Decimal(parent[4]) - consumed - released - transferred - invalidated,
            )
            expected = (
                draft.observed_allocated_quantity,
                draft.observed_consumed_quantity,
                draft.observed_released_quantity,
                draft.observed_transferred_quantity,
                draft.observed_invalidated_quantity,
                draft.observed_remaining_quantity,
            )
            if observed != expected:
                raise _allocation(
                    "ALLOCATION_BALANCE_CHANGED",
                    "Saldi allocazione modificati dopo lo snapshot.",
                )
            for transition_type, quantity, replacement, reason, provenance in expected_facts:
                cursor.execute(
                    """INSERT INTO tpo.transizioni_allocazione
                       (allocation_id,transition_type,quantity,replacement_allocation_id,
                        expected_allocation_version,created_at,created_by,reason,provenance)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (parent[0], transition_type, quantity, replacement,
                     draft.expected_version, persistence_at, actor, reason, provenance),
                )
            cursor.execute(
                """UPDATE tpo.allocazioni
                   SET state=%s,version=version+1,updated_at=%s,updated_by=%s
                   WHERE id=%s AND state='ATTIVA' AND version=%s RETURNING version""",
                (draft.target_state, persistence_at, actor, parent[0],
                 draft.expected_version),
            )
            updated = cursor.fetchone()
            if updated != (draft.expected_version + 1,):
                raise _allocation("ALLOCATION_CAS_FAILED", "CAS allocazione fallita.")

    @staticmethod
    def _persist_messages(
        cursor: Any, run_id: int, write_set: ProductionPlanningCommit,
        persistence_at: datetime,
    ) -> None:
        for message in write_set.messages:
            cursor.execute(
                """INSERT INTO tpo.production_planning_run_messaggi
                   (planning_run_id,posizione,tipo,failure_category,codice,
                    messaggio,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (run_id, message.position, message.message_type,
                 message.failure_category, message.code, message.message,
                 persistence_at),
            )

    @staticmethod
    def _persist_audits(
        cursor: Any, run_id: int, write_set: ProductionPlanningCommit,
        persistence_at: datetime,
    ) -> None:
        context = write_set.context
        for audit in write_set.audits:
            before = dict(audit.before_payload) if audit.before_payload else None
            after = dict(audit.after_payload) if audit.after_payload else None
            cursor.execute(
                """INSERT INTO tpo.audit_eventi
                   (occurred_at,actor,planning_run_id,entity_type,entity_public_id,
                    operation,reason,before_data,after_data,correlation_id,provenance)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (persistence_at, context.actor.value, run_id, audit.entity_type,
                 audit.entity_public_id.value, audit.operation, context.reason,
                 Jsonb(before) if before is not None else None,
                 Jsonb(after) if after is not None else None,
                 context.correlation_id, audit.provenance),
            )

    @staticmethod
    def _complete_run(
        cursor: Any, run_id: int, write_set: ProductionPlanningCommit,
        persistence_at: datetime,
    ) -> None:
        counters = write_set.counters
        cursor.execute(
            """UPDATE tpo.production_planning_runs
               SET state='COMMITTED',completed_at=%s,ordini_letti=%s,
                   righe_ordine_valutate=%s,righe_coperte_integralmente=%s,
                   righe_coperte_parzialmente=%s,righe_piano_generate=%s,
                   allocazioni_generate=%s,righe_tardive=%s,
                   righe_non_producibili=%s,elementi_saltati=%s,version=version+1
               WHERE id=%s AND state='OPEN' AND version=%s
               RETURNING public_id,state,version""",
            (persistence_at, counters.orders_read, counters.order_lines_evaluated,
             counters.lines_fully_covered, counters.lines_partially_covered,
             counters.planning_lines_generated, counters.allocations_generated,
             counters.late_lines, counters.non_producible_lines,
             counters.skipped_items, run_id, write_set.run.expected_version),
        )
        expected = (
            write_set.run.public_id.value, "COMMITTED",
            write_set.run.expected_version + 1,
        )
        if cursor.fetchone() != expected:
            raise _conflict("PLANNING_RUN_CAS_FAILED", "CAS Planning RUN fallita.")


def _allocation_source_id(
    cursor: Any, draft: AllocationDraft,
    authority: dict[str, dict[str, tuple[Any, ...]]],
) -> int:
    public_id = draft.source_public_id.value
    mapping = {
        "DOMANDA": authority["lines"], "STOCK": authority["stock"],
        "PRODUZIONE_IN_CORSO": authority["semine"],
        "RACCOLTA": authority["harvests"],
    }[draft.allocation_type]
    row = mapping.get(public_id)
    if row is None:
        raise _allocation(
            "ALLOCATION_SOURCE_MISSING", "Sorgente allocazione non revalidata."
        )
    if draft.allocation_type == "STOCK":
        return row[1]
    return row[0]


def _transition_facts(
    draft: AllocationTransitionDraft, replacement_id: int | str | None,
) -> tuple[tuple[Any, ...], ...]:
    facts = []
    for transition_type, quantity in (
        ("CONSUMATA", draft.consumed_quantity_delta),
        ("RILASCIATA", draft.released_quantity_delta),
        ("SOSTITUITA", draft.transferred_quantity_delta),
        ("INVALIDA", draft.invalidated_quantity_delta),
    ):
        if quantity > 0:
            facts.append((
                transition_type, quantity,
                replacement_id if transition_type == "SOSTITUITA" else None,
                draft.reason, draft.provenance,
            ))
    return tuple(sorted(facts, key=lambda item: item[0]))


def _revision_result(
    draft: PlanRevisionDraft, *, reused: bool, plan_public_id=None,
    revision_public_id=None,
) -> RevisionCommitResult:
    replanning = draft.canonical_replanning_snapshot
    return RevisionCommitResult(
        plan_public_id=plan_public_id or draft.plan_public_id,
        revision_public_id=revision_public_id or draft.revision_public_id,
        revision_request_key=draft.request_key,
        planning_key_v1=draft.request_key if replanning is None else None,
        replanning_key_v1=(
            replanning.replanning_key_v1 if replanning is not None else None
        ),
        reused_existing_revision=reused,
    )


def _input(code: str, message: str) -> ProductionPlanningError:
    return ProductionPlanningError("PLANNING_INPUT_INVALID", code, message)


def _knowledge(code: str, message: str) -> ProductionPlanningError:
    return ProductionPlanningError("PRODUCTION_KNOWLEDGE_INVALID", code, message)


def _allocation(code: str, message: str) -> ProductionPlanningError:
    return ProductionPlanningError("ALLOCATION_CONFLICT", code, message)


def _conflict(code: str, message: str) -> ProductionPlanningError:
    return ProductionPlanningError("CONCURRENCY_CONFLICT", code, message)


def _failure(
    category: str, code: str, message: str, cause: BaseException,
) -> ProductionPlanningError:
    error = ProductionPlanningError(category, code, message)
    error.__cause__ = cause
    return error


def _cleanup(cursor: Any, connection: Any, *, rollback: bool) -> None:
    if rollback:
        try:
            connection.rollback()
        except Exception:
            pass
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            pass
    try:
        connection.close()
    except Exception:
        pass
