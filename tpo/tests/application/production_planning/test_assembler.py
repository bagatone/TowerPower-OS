from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, time, timezone
from decimal import Decimal
import inspect

import pytest

from src.tpo_core.application.production_planning.assembler import (
    ProductionPlanningCommitAssembler,
)
from src.tpo_core.application.production_planning.engine import ProductionPlanningEngine
from src.tpo_core.application.production_planning.errors import ProductionPlanningError
from src.tpo_core.application.production_planning.models import (
    ActiveAllocationSnapshot,
    AllocationDispositionDecision,
    AllocationReplacementSpecification,
    CurrentPlanSnapshot,
    CurrentPlanningLineSnapshot,
    ExactQuantity,
    HarvestResourceSnapshot,
    InitialProductionPlanningCommand,
    InProgressResourceSnapshot,
    PlanningExecutionContext,
    PlanningInputSnapshot,
    PlanningPolicySnapshot,
    PolicyVersionReference,
    ProductionKnowledgeSnapshot,
    ProductionPlanningAssemblyInput,
    ProductionPlanningIdentityBundle,
    ProductionPlanningRunSnapshot,
    PublicId,
    ReplanProductionPlanningCommand,
    StockResourceSnapshot,
    planning_line_slot_key_v1,
    replacement_allocation_slot_key_v1,
)
from src.tpo_core.domain.identifiers import ActorId
from src.tpo_core.domain.quantities import UnitOfMeasure
from src.tpo_core.domain.states import OrdineState, SeminaState
from tests.application.production_planning.test_application_layer import demand as base_demand


UTC = timezone.utc
BUSINESS_AT = datetime(2026, 8, 15, 6, tzinfo=UTC)


def pid(value: str) -> PublicId:
    return PublicId(value)


def qty(value: str, unit: UnitOfMeasure = UnitOfMeasure.SET) -> ExactQuantity:
    return ExactQuantity(Decimal(value), unit)


def policy(buffer_type: str = "NONE", buffer_value: str | None = None):
    return PlanningPolicySnapshot(
        PolicyVersionReference("DEFAULT", 1), date(2026, 1, 1), None,
        buffer_type, Decimal(buffer_value) if buffer_value is not None else None,
        "DELIVERY_THEN_PUBLIC_ID", "production-planning-v1",
        "EARLIEST_APPROVED_WINDOW",
    )


def knowledge(variety: str = "VAR-000001", protocol: str = "PV-000001"):
    return ProductionKnowledgeSnapshot(
        pid(protocol), 1, "APPROVATA", pid(variety), "Afila", "MICROGREEN",
        date(2026, 1, 1), None, Decimal("8"), time(6), time(6), 2, 7,
        Decimal("25"), qty("1"), Decimal("0.5"), 1, 2, 0,
        "approved-protocol",
    )


def stock(public_id: str, amount: str, *, allocated: str = "0"):
    total = Decimal(amount)
    used = Decimal(allocated)
    return StockResourceSnapshot(
        pid(public_id), pid("VAR-000001"), qty(amount), qty(allocated),
        qty(str(total - used)), 0,
    )


def harvest(public_id: str, amount: str, *, allocated: str = "0", hour=4):
    total = Decimal(amount)
    used = Decimal(allocated)
    return HarvestResourceSnapshot(
        pid(public_id), pid("SEM-000090"), pid("VAR-000001"), qty(amount),
        qty(allocated), qty(str(total - used)),
        datetime(2026, 8, 15, hour, tzinfo=UTC), "harvest-authority",
    )


def semina(public_id: str, amount: str, *, allocated: str = "0", day=14):
    total = Decimal(amount)
    used = Decimal(allocated)
    return InProgressResourceSnapshot(
        pid(public_id), pid("VAR-000001"), pid("PV-000001"), qty(amount),
        qty(allocated), qty(str(total - used)),
        datetime(2026, 8, day, 5, tzinfo=UTC),
        datetime(2026, 8, day, 8, tzinfo=UTC), SeminaState.CRESCITA, 0,
    )


def assembly_input(
    *,
    stocks=(),
    harvests=(),
    progress=(),
    buffer_type="NONE",
    buffer_value=None,
    demand_value="1",
    allocation_count=1,
):
    demand = replace(
        base_demand(),
        ordered=qty(demand_value),
        commercial_residual=qty(demand_value),
    )
    snapshot = PlanningInputSnapshot(
        BUSINESS_AT, policy(buffer_type, buffer_value), (demand,), (knowledge(),),
        tuple(sorted(stocks, key=lambda item: item.resource_public_id.value)),
        tuple(sorted(progress, key=lambda item: item.semina_public_id.value)),
        tuple(sorted(harvests, key=lambda item: item.harvest_public_id.value)),
        (), (), (),
    )
    command = InitialProductionPlanningCommand(
        BUSINESS_AT, snapshot.policy.reference,
        PlanningExecutionContext(ActorId("tpo.planning"), "planning", "corr-1"),
    )
    candidates = tuple(ProductionPlanningEngine().calculate(snapshot))
    identities = ProductionPlanningIdentityBundle(
        (pid("PP-000001"),), (pid("RVP-000001"),), (pid("RPS-000001"),),
        tuple(pid(f"ALL-{index:06d}") for index in range(1, allocation_count + 1)),
    )
    return ProductionPlanningAssemblyInput(
        command, ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN"),
        snapshot, candidates, (), identities,
    )


def assemble(**kwargs):
    return ProductionPlanningCommitAssembler().assemble(assembly_input(**kwargs))


def replanning_value(base):
    previous = pid("RVP-900001")
    snapshot = replace(
        base.snapshot,
        current_plans=(CurrentPlanSnapshot(pid("PP-000001"), 1, previous, 0, 1),),
        current_planning_lines=(CurrentPlanningLineSnapshot(
            pid("RPS-900001"), previous, pid("RO-000001"), "PIANIFICATA", 0,
        ),),
    )
    command = ReplanProductionPlanningCommand(
        BUSINESS_AT, snapshot.policy.reference,
        PlanningExecutionContext(ActorId("tpo.planning"), "replanning", "corr-1"),
        previous, pid("RO-000001"), "MANUAL_REPLAN_AUTHORIZED",
    )
    return replace(
        base, command=command, snapshot=snapshot,
        candidates=tuple(ProductionPlanningEngine().calculate(snapshot)),
    )


def test_full_stock_coverage_crea_linea_zero_senza_seed_o_produzione() -> None:
    result = assemble(stocks=(stock("STK-000001", "1"),), allocation_count=1)
    line = result.revisions[0].lines[0]
    assert line.stock_coverage.value == Decimal("1")
    assert line.production_deficit.value == Decimal("0")
    assert line.authorized_productive_quantity.value == Decimal("0")
    assert result.seed_resources == ()
    assert [(item.allocation_type, item.quantity.value) for item in result.allocations] == [
        ("STOCK", Decimal("1"))
    ]


def test_full_mixed_coverage_rispetta_precedenza_e_non_crea_seed() -> None:
    result = assemble(
        stocks=(stock("STK-000001", "0.4"),),
        harvests=(harvest("RAC-000001", "0.3"),),
        progress=(semina("SEM-000001", "0.3"),), allocation_count=3,
    )
    assert [item.allocation_type for item in result.allocations] == [
        "STOCK", "RACCOLTA", "PRODUZIONE_IN_CORSO"
    ]
    assert result.revisions[0].lines[0].authorized_productive_quantity.value == 0
    assert result.seed_resources == ()


def test_deficit_misto_applica_buffer_percentuale_e_granularita_dopo_coverage() -> None:
    result = assemble(
        stocks=(stock("STK-000001", "0.2"),),
        harvests=(harvest("RAC-000001", "0.1"),),
        progress=(semina("SEM-000001", "0.1"),),
        buffer_type="PERCENTAGE", buffer_value="0.10", allocation_count=4,
    )
    line = result.revisions[0].lines[0]
    assert line.production_deficit.value == Decimal("0.6")
    assert line.calculated_quantitative_buffer == Decimal("0.060")
    assert line.pre_granularity_quantity == Decimal("0.660")
    assert line.authorized_productive_quantity.value == Decimal("1.0")
    assert result.seed_resources[0].required_grams == Decimal("25.0")
    assert result.allocations[-1].allocation_type == "DOMANDA"


def test_buffer_assoluto_si_applica_solo_al_deficit() -> None:
    result = assemble(
        stocks=(stock("STK-000001", "0.4"),), buffer_type="ABSOLUTE_SET",
        buffer_value="0.2", allocation_count=2,
    )
    line = result.revisions[0].lines[0]
    assert line.production_deficit.value == Decimal("0.6")
    assert line.calculated_quantitative_buffer == Decimal("0.2")
    assert line.authorized_productive_quantity.value == Decimal("1.0")


@pytest.mark.parametrize("buffer_type,buffer_value", [("PERCENTAGE", "0.2"), ("ABSOLUTE_SET", "1")])
def test_zero_deficit_ignora_buffer_e_granularita(buffer_type, buffer_value) -> None:
    result = assemble(
        stocks=(stock("STK-000001", "1"),), buffer_type=buffer_type,
        buffer_value=buffer_value, allocation_count=1,
    )
    line = result.revisions[0].lines[0]
    assert (line.calculated_quantitative_buffer, line.pre_granularity_quantity) == (Decimal("0"), Decimal("0"))
    assert line.authorized_productive_quantity.value == 0


def test_same_class_ordering_usa_ready_allocato_residuo_e_public_id() -> None:
    result = assemble(
        stocks=(stock("STK-000002", "0.7", allocated="0.2"), stock("STK-000001", "0.5")),
        demand_value="0.6", allocation_count=2,
    )
    assert [item.source_public_id.value for item in result.allocations] == [
        "STK-000001", "STK-000002"
    ]
    assert [item.quantity.value for item in result.allocations] == [Decimal("0.5"), Decimal("0.1")]


def test_harvest_e_semina_ordering_usano_ready_time_prima_del_public_id() -> None:
    harvest_result = assemble(
        harvests=(harvest("RAC-000001", "0.5", hour=5), harvest("RAC-000002", "0.5", hour=4)),
        allocation_count=2,
    )
    assert [item.source_public_id.value for item in harvest_result.allocations] == [
        "RAC-000002", "RAC-000001"
    ]
    semina_result = assemble(
        progress=(semina("SEM-000001", "0.5", day=15), semina("SEM-000002", "0.5", day=14)),
        allocation_count=2,
    )
    assert [item.source_public_id.value for item in semina_result.allocations] == [
        "SEM-000002", "SEM-000001"
    ]


def test_multi_source_non_aggrega_e_non_overalloca() -> None:
    result = assemble(
        stocks=(stock("STK-000001", "0.4"), stock("STK-000002", "0.6")),
        allocation_count=2,
    )
    assert len(result.allocations) == 2
    assert sum(item.quantity.value for item in result.allocations) == Decimal("1")


def test_stock_uom_mismatch_fallisce_chiuso_senza_readiness_artificiale() -> None:
    bad_uom = replace(stock("STK-000001", "1"), eligible=qty("1", UnitOfMeasure.UNIT), allocated=qty("0", UnitOfMeasure.UNIT), allocable_residual=qty("1", UnitOfMeasure.UNIT))
    with pytest.raises(ProductionPlanningError) as uom:
        assemble(stocks=(bad_uom,), allocation_count=1)
    assert uom.value.code == "RESOURCE_UOM_MISMATCH"


def test_output_chiavi_audit_contatori_e_ordinamenti_sono_deterministici() -> None:
    value = assembly_input(stocks=(stock("STK-000001", "0.5"),), allocation_count=2)
    first = ProductionPlanningCommitAssembler().assemble(value)
    second = ProductionPlanningCommitAssembler().assemble(value)
    assert first == second
    assert first.revisions[0].request_key == second.revisions[0].request_key
    assert first.counters.orders_read == first.counters.order_lines_evaluated == 1
    assert first.counters.lines_partially_covered == 1
    assert first.messages == ()
    assert first.audits == tuple(sorted(first.audits, key=lambda item: (item.entity_type, item.entity_public_id.value, item.operation)))


def test_input_resource_semanticamente_equivalente_produce_stesso_commit() -> None:
    resources = (stock("STK-000002", "0.5"), stock("STK-000001", "0.5"))
    first = assemble(stocks=resources, allocation_count=2)
    second = assemble(stocks=tuple(reversed(resources)), allocation_count=2)
    assert first == second


def test_multi_demand_costruisce_un_unica_revisione_completa_ordinata() -> None:
    base = assembly_input(allocation_count=1)
    second_demand = replace(
        base.snapshot.demands[0],
        order_public_id=pid("ORD-000002"),
        order_line_public_id=pid("RO-000002"),
        variety_public_id=pid("VAR-000002"),
    )
    second_knowledge = knowledge("VAR-000002", "PV-000002")
    snapshot = replace(
        base.snapshot,
        demands=(base.snapshot.demands[0], second_demand),
        knowledge=(base.snapshot.knowledge[0], second_knowledge),
    )
    identities = ProductionPlanningIdentityBundle(
        (pid("PP-000001"),), (pid("RVP-000001"),),
        (pid("RPS-000001"), pid("RPS-000002")),
        (pid("ALL-000001"), pid("ALL-000002")),
    )
    value = replace(
        base, snapshot=snapshot,
        candidates=tuple(ProductionPlanningEngine().calculate(snapshot)),
        identities=identities,
    )
    result = ProductionPlanningCommitAssembler().assemble(value)
    reordered = ProductionPlanningCommitAssembler().assemble(
        replace(value, candidates=tuple(reversed(value.candidates)))
    )
    assert len(result.revisions) == 1
    assert [line.candidate.demand.order_line_public_id.value for line in result.revisions[0].lines] == ["RO-000001", "RO-000002"]
    assert result.counters.orders_read == 2
    assert result.counters.order_lines_evaluated == 2
    assert reordered == result


def test_capacita_resource_e_condivisa_tra_piu_demand_senza_overallocation() -> None:
    base = assembly_input(stocks=(stock("STK-000001", "0.6"),), allocation_count=2)
    first = replace(base.snapshot.demands[0], ordered=qty("0.5"), commercial_residual=qty("0.5"))
    second = replace(
        first, order_public_id=pid("ORD-000002"), order_line_public_id=pid("RO-000002")
    )
    snapshot = replace(base.snapshot, demands=(first, second))
    identities = ProductionPlanningIdentityBundle(
        (pid("PP-000001"),), (pid("RVP-000001"),),
        (pid("RPS-000001"), pid("RPS-000002")),
        (pid("ALL-000001"), pid("ALL-000002"), pid("ALL-000003")),
    )
    value = replace(
        base, snapshot=snapshot,
        candidates=tuple(ProductionPlanningEngine().calculate(snapshot)),
        identities=identities,
    )
    result = ProductionPlanningCommitAssembler().assemble(value)
    stock_allocations = [item for item in result.allocations if item.allocation_type == "STOCK"]
    assert sum(item.quantity.value for item in stock_allocations) == Decimal("0.6")
    assert any(item.allocation_type == "DOMANDA" for item in result.allocations)


def test_identity_cardinality_e_zero_quantity_allocations_fail_closed() -> None:
    value = assembly_input(stocks=(stock("STK-000001", "1"),), allocation_count=0)
    with pytest.raises(ProductionPlanningError) as captured:
        ProductionPlanningCommitAssembler().assemble(value)
    assert captured.value.code == "IDENTITY_CARDINALITY_MISMATCH"


def test_input_output_immutabili_e_provider_neutral() -> None:
    value = assembly_input(allocation_count=1)
    result = ProductionPlanningCommitAssembler().assemble(value)
    with pytest.raises(FrozenInstanceError):
        value.candidates = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.counters.orders_read = 2  # type: ignore[misc]
    source = inspect.getsource(ProductionPlanningCommitAssembler).lower()
    assert all(name not in source for name in ("postgres", "sqlalchemy", "psycopg", "select ", "insert "))


def test_disposition_release_diventa_transition_draft() -> None:
    base = assembly_input(allocation_count=1)
    observed = ActiveAllocationSnapshot(
        pid("ALL-900001"), "STOCK", pid("STK-000001"), pid("RO-000001"),
        qty("1"), qty("0.25"), qty("0"), qty("0"), qty("0"), qty("0.75"),
        "ATTIVA", 3,
    )
    decision = AllocationDispositionDecision(
        pid("ALL-900001"), 3, "DEMAND_REDUCED", "REUSABLE", Decimal("0.75"),
        Decimal("0.25"), "RILASCIATA", None, "demand reduced", "replanning decision",
    )
    snapshot = replace(base.snapshot, allocations=(observed,))
    value = replace(
        base, snapshot=snapshot,
        candidates=tuple(ProductionPlanningEngine().calculate(snapshot)),
        allocation_dispositions=(decision,),
    )
    result = ProductionPlanningCommitAssembler().assemble(value)
    transition = result.allocation_transitions[0]
    assert transition.consumed_quantity_delta == Decimal("0.25")
    assert transition.released_quantity_delta == Decimal("0.50")
    assert transition.target_state == "RILASCIATA"


@pytest.mark.parametrize(
    ("cause", "usability", "target", "delta_name"),
    [
        ("SOURCE_UNUSABLE", "UNUSABLE", "INVALIDA", "invalidated_quantity_delta"),
        ("HARVEST_UNAVAILABLE", "UNUSABLE", "INVALIDA", "invalidated_quantity_delta"),
    ],
)
def test_disposition_invalidation_e_assemblata(cause, usability, target, delta_name) -> None:
    base = assembly_input(allocation_count=1)
    observed = ActiveAllocationSnapshot(
        pid("ALL-900001"), "STOCK", pid("STK-000001"), pid("RO-000001"),
        qty("1"), qty("0"), qty("0"), qty("0"), qty("0"), qty("1"),
        "ATTIVA", 0,
    )
    decision = AllocationDispositionDecision(
        observed.allocation_public_id, 0, cause, usability, Decimal("1"),
        Decimal("0"), target, None, "source unusable", "replanning decision",
    )
    snapshot = replace(base.snapshot, allocations=(observed,))
    value = replace(
        base, snapshot=snapshot,
        candidates=tuple(ProductionPlanningEngine().calculate(snapshot)),
        allocation_dispositions=(decision,),
    )
    transition = ProductionPlanningCommitAssembler().assemble(value).allocation_transitions[0]
    assert getattr(transition, delta_name) == Decimal("1")
    assert transition.target_state == target


def test_disposition_replacement_crea_transition_e_allocation_distinta() -> None:
    base = replanning_value(assembly_input(allocation_count=1))
    observed = ActiveAllocationSnapshot(
        pid("ALL-900001"), "STOCK", pid("STK-000001"), pid("RO-000001"),
        qty("1"), qty("0.25"), qty("0"), qty("0"), qty("0"), qty("0.75"),
        "ATTIVA", 4,
    )
    line_slot = planning_line_slot_key_v1(
        base.command.previous_revision_public_id, pid("RO-000001")
    )
    replacement = AllocationReplacementSpecification(
        replacement_allocation_slot_key_v1(
            observed.allocation_public_id, "STOCK", pid("STK-000001"),
            pid("RO-000001"), line_slot,
        ), "STOCK", pid("STK-000001"), pid("RO-000001"),
        line_slot, qty("0.5"), "replacement destination",
    )
    decision = AllocationDispositionDecision(
        observed.allocation_public_id, 4, "REALLOCATION_REQUIRED",
        "TRANSFERABLE_ONLY", Decimal("0.75"), Decimal("0.25"), "SOSTITUITA",
        replacement, "reallocation", "replanning decision",
    )
    snapshot = replace(base.snapshot, allocations=(observed,))
    value = replace(
        base, snapshot=snapshot,
        candidates=tuple(ProductionPlanningEngine().calculate(snapshot)),
        allocation_dispositions=(decision,),
        identities=replace(
            base.identities,
            replacement_allocation_public_ids=(pid("ALL-900002"),),
        ),
    )
    result = ProductionPlanningCommitAssembler().assemble(value)
    transition = result.allocation_transitions[0]
    assert transition.transferred_quantity_delta == Decimal("0.5")
    assert any(item.public_id == pid("ALL-900002") for item in result.allocations)


def test_replacement_destination_planning_line_mismatch_e_rifiutato() -> None:
    base = replanning_value(assembly_input(allocation_count=1))
    observed = ActiveAllocationSnapshot(
        pid("ALL-900001"), "STOCK", pid("STK-000001"), pid("RO-000001"),
        qty("1"), qty("0"), qty("0"), qty("0"), qty("0"), qty("1"),
        "ATTIVA", 0,
    )
    wrong_line_slot = planning_line_slot_key_v1(
        pid("RVP-999999"), pid("RO-000001")
    )
    replacement = AllocationReplacementSpecification(
        replacement_allocation_slot_key_v1(
            observed.allocation_public_id, "STOCK", pid("STK-000001"),
            pid("RO-000001"), wrong_line_slot,
        ), "STOCK", pid("STK-000001"), pid("RO-000001"),
        wrong_line_slot, qty("1"), "replacement destination",
    )
    decision = AllocationDispositionDecision(
        observed.allocation_public_id, 0, "REALLOCATION_REQUIRED",
        "TRANSFERABLE_ONLY", Decimal("1"), Decimal("0"), "SOSTITUITA",
        replacement, "reallocation", "replanning decision",
    )
    snapshot = replace(base.snapshot, allocations=(observed,))
    value = replace(
        base, snapshot=snapshot,
        candidates=tuple(ProductionPlanningEngine().calculate(snapshot)),
        allocation_dispositions=(decision,),
        identities=replace(
            base.identities,
            replacement_allocation_public_ids=(pid("ALL-900002"),),
        ),
    )
    with pytest.raises(ProductionPlanningError) as captured:
        ProductionPlanningCommitAssembler().assemble(value)
    assert captured.value.code == "REPLACEMENT_DESTINATION_INVALID"


def test_replanning_costruisce_snapshot_hash_e_revision_request_key() -> None:
    base = assembly_input(allocation_count=1)
    previous = pid("RVP-900001")
    snapshot = replace(
        base.snapshot,
        current_plans=(CurrentPlanSnapshot(pid("PP-000001"), 2, previous, 3, 1),),
        current_planning_lines=(CurrentPlanningLineSnapshot(pid("RPS-900001"), previous, pid("RO-000001"), "PIANIFICATA", 1),),
    )
    command = ReplanProductionPlanningCommand(
        BUSINESS_AT, snapshot.policy.reference, base.command.context, previous,
        pid("RO-000001"), "STOCK_CHANGED",
    )
    value = replace(base, command=command, snapshot=snapshot, candidates=tuple(ProductionPlanningEngine().calculate(snapshot)))
    revision = ProductionPlanningCommitAssembler().assemble(value).revisions[0]
    assert revision.revision_number == 2
    assert revision.canonical_replanning_snapshot is not None
    assert revision.request_key == revision.canonical_replanning_snapshot.replanning_key_v1
    assert revision.canonical_replanning_snapshot.canonical_text


def test_protocol_retirement_non_invalida_da_solo_allocazioni_osservate() -> None:
    base = assembly_input(allocation_count=1)
    observed = ActiveAllocationSnapshot(
        pid("ALL-900001"), "STOCK", pid("STK-000001"), pid("RO-000001"),
        qty("1"), qty("0"), qty("0"), qty("0"), qty("0"), qty("1"), "ATTIVA", 0,
    )
    snapshot = replace(base.snapshot, allocations=(observed,))
    value = replace(base, snapshot=snapshot, candidates=tuple(ProductionPlanningEngine().calculate(snapshot)))
    assert ProductionPlanningCommitAssembler().assemble(value).allocation_transitions == ()
