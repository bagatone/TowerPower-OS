"""Coherent PostgreSQL loader for the frozen Production Planning input."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import psycopg

from ...application.production_planning.errors import ProductionPlanningError
from ...application.production_planning.models import (
    ActiveAllocationSnapshot, AllocationDispositionDecision,
    AllocationReplacementSpecification, CurrentPlanningLineSnapshot,
    CurrentPlanSnapshot, DemandSnapshot, ExactQuantity,
    HarvestResourceSnapshot, InProgressResourceSnapshot,
    InitialProductionPlanningCommand, PlanningInputSnapshot,
    PlanningPolicySnapshot, ProductionKnowledgeSnapshot,
    ProductionPlanningLoadedInput, PublicId, ReplanProductionPlanningCommand,
    StockResourceSnapshot, disposition_set_key_v1,
    planning_line_slot_key_v1, replacement_allocation_slot_key_v1,
)
from ...domain.quantities import UnitOfMeasure
from ...domain.states import OrdineState, SeminaState
from .connection import PostgreSQLConnectionFactory


class PostgreSQLProductionPlanningInputAdapter:
    """Builds all loaded input in one read-only repeatable-read transaction."""

    def __init__(self, connection_factory: PostgreSQLConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def load(self, command) -> ProductionPlanningLoadedInput:
        if not isinstance(command, (InitialProductionPlanningCommand, ReplanProductionPlanningCommand)):
            raise _input("INVALID_COMMAND", "Command Production Planning non valido.")
        connection = self._connection_factory.connect()
        cursor = None
        committed = False
        try:
            cursor = connection.cursor()
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            policy = self._policy(cursor, command)
            allocations, balances = self._allocations(cursor)
            stock = self._stock(cursor, balances)
            in_progress = self._in_progress(cursor, balances)
            harvests = self._harvests(cursor, balances)
            represented_sources = {
                *(('STOCK', item.resource_public_id.value) for item in stock),
                *(('PRODUZIONE_IN_CORSO', item.semina_public_id.value) for item in in_progress),
                *(('RACCOLTA', item.harvest_public_id.value) for item in harvests),
            }
            if not set(balances).issubset(represented_sources):
                raise _allocation(
                    "ALLOCATION_SOURCE_NOT_ELIGIBLE",
                    "Allocazione attiva riferita a una risorsa assente o non eleggibile.",
                )
            snapshot = PlanningInputSnapshot(
                business_at=command.business_at,
                policy=policy,
                demands=self._demands(cursor),
                knowledge=self._knowledge(cursor),
                stock=stock, in_progress=in_progress, harvests=harvests,
                allocations=allocations,
                current_plans=self._current_plans(cursor),
                current_planning_lines=self._current_lines(cursor),
            )
            decisions = (
                () if isinstance(command, InitialProductionPlanningCommand)
                and not isinstance(command, ReplanProductionPlanningCommand)
                else self._dispositions(cursor, command)
            )
            result = ProductionPlanningLoadedInput(snapshot, decisions)
            connection.commit()
            committed = True
            return result
        except ProductionPlanningError:
            raise
        except (ValueError, TypeError) as exc:
            raise _input("AUTHORITATIVE_INPUT_INCONSISTENT", "Input Planning autorevole incoerente.") from exc
        except psycopg.Error as exc:
            raise ProductionPlanningError(
                "INTERNAL_ERROR", "INPUT_LOAD_FAILED",
                "Lettura PostgreSQL del Planning non completata.",
            ) from exc
        finally:
            _cleanup(cursor, connection, rollback=not committed)

    @staticmethod
    def _policy(cursor: Any, command) -> PlanningPolicySnapshot:
        cursor.execute(
            """SELECT valida_dal,valida_al,buffer_quantitativo_tipo,
                      buffer_quantitativo_valore,priority_policy_code,
                      planning_algorithm_version,harvest_target_strategy
               FROM tpo.production_planning_policy_versions
               WHERE policy_set_code=%s AND numero_versione=%s
                 AND valida_dal<=%s::date AND (valida_al IS NULL OR %s::date<valida_al)
               ORDER BY id""",
            (command.policy.policy_set_code, command.policy.version,
             command.business_at, command.business_at),
        )
        rows = cursor.fetchall()
        if len(rows) != 1:
            raise _input("POLICY_NOT_EXACT", "Planning Policy richiesta assente, non valida o ambigua.")
        row = rows[0]
        return PlanningPolicySnapshot(
            command.policy, row[0], row[1], row[2],
            _decimal_or_none(row[3]), row[4], row[5], row[6],
        )

    @staticmethod
    def _demands(cursor: Any) -> tuple[DemandSnapshot, ...]:
        cursor.execute(
            """SELECT o.public_id,ro.public_id,o.version,ro.version,o.stato,
                      v.public_id,ro.quantita,ro.unita_misura,
                      COALESCE(SUM(rc.quantita) FILTER (WHERE c.stato='CONSEGNATA'),0)::numeric(20,6),
                      o.data_ordine,o.data_consegna_prevista
               FROM tpo.ordini o JOIN tpo.righe_ordine ro ON ro.ordine_id=o.id
               JOIN tpo.varieta v ON v.id=ro.varieta_id
               LEFT JOIN tpo.righe_consegna rc ON rc.riga_ordine_id=ro.id
               LEFT JOIN tpo.consegne c ON c.id=rc.consegna_id
               WHERE o.stato IN ('APERTO','PARZIALMENTE_EVASO')
                 AND o.data_consegna_prevista IS NOT NULL
               GROUP BY o.id,o.public_id,ro.id,ro.public_id,v.public_id
               HAVING ro.quantita-COALESCE(SUM(rc.quantita) FILTER
                         (WHERE c.stato='CONSEGNATA'),0)>0
               ORDER BY ro.public_id"""
        )
        result = []
        for row in cursor.fetchall():
            ordered, delivered = Decimal(row[6]), Decimal(row[8])
            if delivered < 0 or delivered > ordered:
                raise _input("DEMAND_BALANCE_INVALID", "Saldo domanda commerciale impossibile.")
            unit = UnitOfMeasure(row[7])
            result.append(DemandSnapshot(
                PublicId(row[0]), PublicId(row[1]), row[2], row[3],
                OrdineState(row[4]), PublicId(row[5]),
                ExactQuantity(ordered, unit), ExactQuantity(delivered, unit),
                ExactQuantity(ordered-delivered, unit), row[9], row[10], None,
                "tpo.righe_ordine+tpo.righe_consegna:CONSEGNATA",
            ))
        return tuple(result)

    @staticmethod
    def _knowledge(cursor: Any) -> tuple[ProductionKnowledgeSnapshot, ...]:
        cursor.execute(
            """SELECT pv.public_id,pv.numero_versione,pv.stato_approvazione,
                      v.public_id,c.denominazione,u.codice,pv.valida_dal,pv.valida_al,
                      pv.idratazione_ore,pv.orario_semina_previsto,
                      pv.orario_raccolta_target,pv.germinazione_giorni,
                      pv.crescita_luce_giorni,pv.grammi_seme_per_set,
                      pv.resa_attesa,pv.resa_unita_misura,pv.granularita_produttiva,
                      pv.harvest_min_lead_giorni,pv.harvest_max_lead_giorni,
                      pv.buffer_temporale_minuti,pv.provenance
               FROM tpo.protocollo_versioni pv
               JOIN tpo.protocolli p ON p.id=pv.protocollo_id
               JOIN tpo.cultivar_usi cu ON cu.id=p.cultivar_uso_id
               JOIN tpo.cultivar c ON c.id=cu.cultivar_id
               JOIN tpo.varieta v ON v.id=c.varieta_id
               JOIN tpo.usi_produttivi u ON u.id=cu.uso_produttivo_id
               WHERE pv.public_id IS NOT NULL AND pv.stato_approvazione IS NOT NULL
               ORDER BY pv.public_id"""
        )
        return tuple(ProductionKnowledgeSnapshot(
            PublicId(r[0]), r[1], r[2], PublicId(r[3]), r[4], r[5], r[6], r[7],
            Decimal(r[8]), r[9], r[10], r[11], r[12], Decimal(r[13]),
            ExactQuantity(Decimal(r[14]), UnitOfMeasure(r[15])), Decimal(r[16]),
            r[17], r[18], r[19], r[20],
        ) for r in cursor.fetchall())

    @staticmethod
    def _allocations(cursor: Any):
        cursor.execute(
            """SELECT a.public_id,a.allocation_type,
                      COALESCE(vs.public_id,sem.public_id,rac.public_id,rod.public_id),
                      ro.public_id,a.quantity,a.unita_misura,
                      COALESCE(SUM(t.quantity) FILTER (WHERE t.transition_type='CONSUMATA'),0),
                      COALESCE(SUM(t.quantity) FILTER (WHERE t.transition_type='RILASCIATA'),0),
                      COALESCE(SUM(t.quantity) FILTER (WHERE t.transition_type='SOSTITUITA'),0),
                      COALESCE(SUM(t.quantity) FILTER (WHERE t.transition_type='INVALIDA'),0),
                      a.state,a.version
               FROM tpo.allocazioni a
               JOIN tpo.righe_piano_semina rps ON rps.id=a.riga_piano_semina_id
               JOIN tpo.righe_ordine ro ON ro.id=rps.riga_ordine_id
               LEFT JOIN tpo.allocazioni_stock ast ON ast.allocation_id=a.id
               LEFT JOIN tpo.stock st ON st.varieta_id=ast.stock_varieta_id
               LEFT JOIN tpo.varieta vs ON vs.id=st.varieta_id
               LEFT JOIN tpo.allocazioni_produzione_in_corso aip ON aip.allocation_id=a.id
               LEFT JOIN tpo.semine sem ON sem.id=aip.semina_id
               LEFT JOIN tpo.allocazioni_raccolta ar ON ar.allocation_id=a.id
               LEFT JOIN tpo.raccolte rac ON rac.id=ar.raccolta_id
               LEFT JOIN tpo.allocazioni_domanda ad ON ad.allocation_id=a.id
               LEFT JOIN tpo.righe_ordine rod ON rod.id=ad.riga_ordine_id
               LEFT JOIN tpo.transizioni_allocazione t ON t.allocation_id=a.id
               GROUP BY a.id,a.public_id,a.allocation_type,vs.public_id,sem.public_id,
                        rac.public_id,rod.public_id,ro.public_id
               ORDER BY a.public_id"""
        )
        snapshots = []
        balances: dict[tuple[str, str], tuple[Decimal, str]] = {}
        for r in cursor.fetchall():
            if r[2] is None:
                raise _input("ALLOCATION_CHILD_INVALID", "Child tipizzato allocazione assente o incoerente.")
            allocated = Decimal(r[4]); parts = tuple(Decimal(v) for v in r[6:10])
            remaining = allocated-sum(parts, Decimal("0"))
            if remaining < 0 or (r[10] == "ATTIVA" and remaining <= 0):
                raise _allocation("ALLOCATION_BALANCE_INVALID", "Saldo allocazione impossibile.")
            unit = UnitOfMeasure(r[5])
            snapshots.append(ActiveAllocationSnapshot(
                PublicId(r[0]), r[1], PublicId(r[2]), PublicId(r[3]),
                ExactQuantity(allocated, unit),
                *(ExactQuantity(value, unit) for value in parts),
                ExactQuantity(remaining, unit), r[10], r[11],
            ))
            if r[10] == "ATTIVA" and r[1] != "DOMANDA":
                key = (r[1], r[2]); previous = balances.get(key)
                if previous is not None and previous[1] != r[5]:
                    raise _allocation("ALLOCATION_UOM_MISMATCH", "UOM allocazioni sorgente incoerenti.")
                balances[key] = ((previous[0] if previous else Decimal("0"))+remaining, r[5])
        return tuple(snapshots), balances

    @staticmethod
    def _stock(cursor: Any, balances) -> tuple[StockResourceSnapshot, ...]:
        cursor.execute(
            """SELECT v.public_id,s.disponibile,s.unita_misura,s.version
               FROM tpo.stock s JOIN tpo.varieta v ON v.id=s.varieta_id
               ORDER BY v.public_id"""
        )
        result = []
        for r in cursor.fetchall():
            eligible, unit = Decimal(r[1]), UnitOfMeasure(r[2])
            allocated, allocated_uom = balances.get(("STOCK", r[0]), (Decimal("0"), r[2]))
            _balance(eligible, r[2], allocated, allocated_uom)
            result.append(StockResourceSnapshot(
                PublicId(r[0]), PublicId(r[0]), ExactQuantity(eligible, unit),
                ExactQuantity(allocated, unit), ExactQuantity(eligible-allocated, unit), r[3],
            ))
        return tuple(result)

    @staticmethod
    def _in_progress(cursor: Any, balances) -> tuple[InProgressResourceSnapshot, ...]:
        cursor.execute(
            """SELECT s.public_id,v.public_id,pv.public_id,s.expected_useful_quantity,
                      s.expected_useful_uom,s.harvest_window_start,s.harvest_window_end,
                      s.stato,s.version
               FROM tpo.semine s JOIN tpo.varieta v ON v.id=s.varieta_id
               JOIN tpo.protocollo_versioni pv ON pv.id=s.protocollo_versione_id
               WHERE s.stato<>'CHIUSA' AND s.expected_useful_quantity IS NOT NULL
                 AND s.expected_useful_uom IS NOT NULL
                 AND s.harvest_window_start IS NOT NULL AND s.harvest_window_end IS NOT NULL
               ORDER BY s.public_id"""
        )
        result = []
        for r in cursor.fetchall():
            eligible, unit = Decimal(r[3]), UnitOfMeasure(r[4])
            allocated, allocated_uom = balances.get(("PRODUZIONE_IN_CORSO", r[0]), (Decimal("0"), r[4]))
            _balance(eligible, r[4], allocated, allocated_uom)
            result.append(InProgressResourceSnapshot(
                PublicId(r[0]), PublicId(r[1]), PublicId(r[2]),
                ExactQuantity(eligible, unit), ExactQuantity(allocated, unit),
                ExactQuantity(eligible-allocated, unit), r[5], r[6],
                SeminaState(r[7]), r[8],
            ))
        return tuple(result)

    @staticmethod
    def _harvests(cursor: Any, balances) -> tuple[HarvestResourceSnapshot, ...]:
        cursor.execute(
            """SELECT r.public_id,s.public_id,v.public_id,r.quantita,r.unita_misura,
                      r.data_raccolta
               FROM tpo.raccolte r JOIN tpo.semine s ON s.id=r.semina_id
               JOIN tpo.varieta v ON v.id=s.varieta_id ORDER BY r.public_id"""
        )
        result = []
        for r in cursor.fetchall():
            eligible, unit = Decimal(r[3]), UnitOfMeasure(r[4])
            allocated, allocated_uom = balances.get(("RACCOLTA", r[0]), (Decimal("0"), r[4]))
            _balance(eligible, r[4], allocated, allocated_uom)
            result.append(HarvestResourceSnapshot(
                PublicId(r[0]), PublicId(r[1]), PublicId(r[2]),
                ExactQuantity(eligible, unit), ExactQuantity(allocated, unit),
                ExactQuantity(eligible-allocated, unit), r[5], "tpo.raccolte",
            ))
        return tuple(result)

    @staticmethod
    def _current_plans(cursor: Any) -> tuple[CurrentPlanSnapshot, ...]:
        cursor.execute(
            """SELECT p.public_id,p.version,r.public_id,r.version,r.numero_revisione
               FROM tpo.piani_produzione p JOIN tpo.piano_produzione_revisioni r
                 ON r.id=p.current_revision_id ORDER BY p.public_id"""
        )
        return tuple(CurrentPlanSnapshot(PublicId(r[0]), r[1], PublicId(r[2]), r[3], r[4]) for r in cursor.fetchall())

    @staticmethod
    def _current_lines(cursor: Any) -> tuple[CurrentPlanningLineSnapshot, ...]:
        cursor.execute(
            """SELECT l.public_id,r.public_id,ro.public_id,l.stato,l.version
               FROM tpo.piani_produzione p JOIN tpo.piano_produzione_revisioni r
                 ON r.id=p.current_revision_id
               JOIN tpo.righe_piano_semina l ON l.piano_revisione_id=r.id
               JOIN tpo.righe_ordine ro ON ro.id=l.riga_ordine_id
               ORDER BY l.public_id"""
        )
        return tuple(CurrentPlanningLineSnapshot(PublicId(r[0]), PublicId(r[1]), PublicId(r[2]), r[3], r[4]) for r in cursor.fetchall())

    @staticmethod
    def _dispositions(cursor: Any, command: ReplanProductionPlanningCommand):
        cursor.execute(
            """SELECT s.id,s.decision_set_key
               FROM tpo.replanning_disposition_sets s
               JOIN tpo.piano_produzione_revisioni pr ON pr.id=s.previous_plan_revision_id
               JOIN tpo.righe_ordine ro ON ro.id=s.order_line_id
               WHERE pr.public_id=%s AND ro.public_id=%s
                 AND s.replanning_reason_code=%s AND s.correlation_id=%s
                 AND s.state='AUTHORIZED' ORDER BY s.id""",
            (command.previous_revision_public_id.value, command.order_line_public_id.value,
             command.replanning_reason_code, command.context.correlation_id),
        )
        sets = cursor.fetchall()
        if len(sets) != 1:
            raise _input("DISPOSITION_SET_NOT_EXACT", "Disposition set autorizzato assente o ambiguo.")
        set_id, persisted_key = sets[0]
        cursor.execute(
            """SELECT a.public_id,d.expected_allocation_version,d.disposition_cause,
                      d.source_usability,d.observed_remaining_quantity,
                      d.consumed_quantity_delta,d.target_disposition,d.reason,d.provenance,
                      rr.replacement_allocation_slot_key,rr.destination_planning_line_slot_key,
                      rr.allocation_type,rr.source_public_id,ro.public_id,rr.quantity,
                      rr.unita_misura,rr.provenance
               FROM tpo.replanning_disposition_decisions d
               JOIN tpo.allocazioni a ON a.id=d.allocation_id
               LEFT JOIN tpo.replanning_disposition_replacements rr
                 ON rr.disposition_decision_id=d.id
               LEFT JOIN tpo.righe_ordine ro ON ro.id=rr.destination_order_line_id
               WHERE d.disposition_set_id=%s ORDER BY a.public_id""", (set_id,),
        )
        decisions = []
        for r in cursor.fetchall():
            replacement = None
            if r[9] is not None:
                destination = PublicId(r[13])
                expected_line = planning_line_slot_key_v1(command.previous_revision_public_id, destination)
                expected_replacement = replacement_allocation_slot_key_v1(
                    PublicId(r[0]), r[11], PublicId(r[12]), destination, expected_line,
                )
                if r[10] != expected_line or r[9] != expected_replacement:
                    raise _input("REPLACEMENT_SLOT_MISMATCH", "Canonical replacement slot key non coincidente.")
                replacement = AllocationReplacementSpecification(
                    r[9], r[11], PublicId(r[12]), destination, r[10],
                    ExactQuantity(Decimal(r[14]), UnitOfMeasure(r[15])), r[16],
                )
            decisions.append(AllocationDispositionDecision(
                PublicId(r[0]), r[1], r[2], r[3], Decimal(r[4]), Decimal(r[5]),
                r[6], replacement, r[7], r[8],
            ))
        result = tuple(decisions)
        calculated = disposition_set_key_v1(
            previous_plan_revision_public_id=command.previous_revision_public_id,
            order_line_public_id=command.order_line_public_id,
            replanning_reason_code=command.replanning_reason_code,
            correlation_id=command.context.correlation_id, decisions=result,
        )
        if calculated.value != persisted_key:
            raise _input("DISPOSITION_SET_KEY_MISMATCH", "Decision set key non coincide con il contenuto autorevole.")
        return result


def _balance(eligible: Decimal, eligible_uom: str, allocated: Decimal, allocated_uom: str) -> None:
    if eligible_uom != allocated_uom:
        raise _allocation("RESOURCE_UOM_MISMATCH", "UOM risorsa e allocazioni incoerenti.")
    if allocated < 0 or eligible-allocated < 0:
        raise _allocation("RESOURCE_OVERALLOCATED", "Risorsa sovra-allocata.")


def _decimal_or_none(value):
    return None if value is None else Decimal(value)


def _input(code: str, message: str) -> ProductionPlanningError:
    return ProductionPlanningError("PLANNING_INPUT_INVALID", code, message)


def _allocation(code: str, message: str) -> ProductionPlanningError:
    return ProductionPlanningError("ALLOCATION_CONFLICT", code, message)


def _cleanup(cursor: Any, connection: Any, *, rollback: bool) -> None:
    if rollback:
        try: connection.rollback()
        except Exception: pass
    if cursor is not None:
        try: cursor.close()
        except Exception: pass
    try: connection.close()
    except Exception: pass
