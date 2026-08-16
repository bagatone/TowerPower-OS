from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, time, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import get_type_hints

import pytest

from src.tpo_core.application.production_planning.errors import (
    InvalidProductionPlanningModelError,
    ProductionPlanningError,
    ProductionPlanningOutcomeUncertain,
)
from src.tpo_core.application.production_planning.models import (
    ActiveAllocationSnapshot,
    AllocationDispositionDecision,
    AllocationDraft,
    AllocationReplacementSpecification,
    AllocationTransitionDraft,
    AuditDraft,
    CanonicalHash,
    CanonicalReplanningSnapshot,
    CurrentPlanningLineSnapshot,
    DemandSnapshot,
    ExactQuantity,
    InitialProductionPlanningCommand,
    PlanningCandidate,
    PlanningExecutionContext,
    PlanningInputSnapshot,
    PlanningLineDraft,
    PlanningPolicySnapshot,
    PlanRevisionDraft,
    PolicyVersionReference,
    ProductionKnowledgeSnapshot,
    ProductionPlanningCommit,
    ProductionPlanningReconciliationRequiredResult,
    ProductionPlanningResult,
    ProductionPlanningRunOutcome,
    ProductionPlanningRunCounters,
    ProductionPlanningRunSnapshot,
    PublicId,
    ReplanProductionPlanningCommand,
    RevisionCommitResult,
    RunMessage,
    SeedResourceDraft,
    StockResourceSnapshot,
)
from src.tpo_core.application.production_planning.service import ProductionPlanningService
from src.tpo_core.application.production_planning.ports import (
    ProductionPlanningCommitPort,
    ProductionPlanningRunPort,
)
from src.tpo_core.domain.identifiers import ActorId
from src.tpo_core.domain.quantities import UnitOfMeasure
from src.tpo_core.domain.states import OrdineState


UTC = timezone.utc
BUSINESS_AT = datetime(2026, 8, 15, 6, 0, tzinfo=UTC)
HASH = CanonicalHash("a" * 64)


def pid(value: str) -> PublicId:
    return PublicId(value)


def qty(value: str, unit: UnitOfMeasure = UnitOfMeasure.SET) -> ExactQuantity:
    return ExactQuantity(Decimal(value), unit)


def allocation_snapshot() -> ActiveAllocationSnapshot:
    return ActiveAllocationSnapshot(
        allocation_public_id=pid("ALL-000001"),
        allocation_type="DOMANDA",
        source_public_id=pid("RO-000001"),
        destination_order_line_public_id=pid("RO-000001"),
        allocated_quantity=qty("1"),
        consumed_quantity=qty("0"),
        released_quantity=qty("0"),
        transferred_quantity=qty("0"),
        invalidated_quantity=qty("0"),
        remaining_quantity=qty("1"),
        state="ATTIVA",
        version=0,
    )


def allocation_transition(**overrides) -> AllocationTransitionDraft:
    values = {
        "allocation_public_id": pid("ALL-000001"),
        "expected_version": 0,
        "current_state": "ATTIVA",
        "target_state": "ATTIVA",
        "observed_allocated_quantity": Decimal("1"),
        "observed_consumed_quantity": Decimal("0"),
        "observed_released_quantity": Decimal("0"),
        "observed_transferred_quantity": Decimal("0"),
        "observed_invalidated_quantity": Decimal("0"),
        "observed_remaining_quantity": Decimal("1"),
        "consumed_quantity_delta": Decimal("0.4"),
        "released_quantity_delta": Decimal("0"),
        "transferred_quantity_delta": Decimal("0"),
        "invalidated_quantity_delta": Decimal("0"),
        "replacement_allocation_public_id": None,
        "reason": "allocation lifecycle",
        "provenance": "planning snapshot",
    }
    values.update(overrides)
    return AllocationTransitionDraft(**values)


def replacement_specification(**overrides) -> AllocationReplacementSpecification:
    values = {
        "replacement_allocation_public_id": pid("ALL-000002"),
        "allocation_type": "DOMANDA",
        "source_public_id": pid("RO-000001"),
        "destination_order_line_public_id": pid("RO-000001"),
        "destination_planning_line_public_id": pid("RPS-000002"),
        "quantity": qty("1"),
        "provenance": "replanning replacement",
    }
    values.update(overrides)
    return AllocationReplacementSpecification(**values)


def disposition_decision(**overrides) -> AllocationDispositionDecision:
    values = {
        "allocation_public_id": pid("ALL-000001"),
        "expected_version": 0,
        "disposition_cause": "DEMAND_REDUCED",
        "source_usability": "REUSABLE",
        "observed_remaining_quantity": Decimal("1"),
        "consumed_quantity_delta": Decimal("0"),
        "target_disposition": "RILASCIATA",
        "replacement_specification": None,
        "reason": "demand reduced",
        "provenance": "authoritative replanning decision",
    }
    values.update(overrides)
    return AllocationDispositionDecision(**values)


def command() -> InitialProductionPlanningCommand:
    return InitialProductionPlanningCommand(
        business_at=BUSINESS_AT,
        policy=PolicyVersionReference("DEFAULT", 1),
        context=PlanningExecutionContext(ActorId("tpo.planning"), "planning", "corr-1"),
    )


def demand() -> DemandSnapshot:
    return DemandSnapshot(
        order_public_id=pid("ORD-000001"),
        order_line_public_id=pid("RO-000001"),
        order_version=0,
        order_line_version=0,
        order_state=OrdineState.APERTO,
        variety_public_id=pid("VAR-000001"),
        ordered=qty("1"),
        delivered=qty("0"),
        commercial_residual=qty("1"),
        order_date=date(2026, 8, 1),
        delivery_date=date(2026, 8, 15),
        commercial_priority=None,
        provenance="tpo.righe_ordine",
    )


def knowledge(approval_state: str = "APPROVATA") -> ProductionKnowledgeSnapshot:
    return ProductionKnowledgeSnapshot(
        protocol_version_public_id=pid("PV-000001"),
        protocol_version_number=1,
        approval_state=approval_state,
        variety_public_id=pid("VAR-000001"),
        cultivar_reference="Afila",
        productive_use_reference="MICROGREEN",
        valid_from=date(2026, 1, 1),
        valid_to=None,
        hydration_hours=Decimal("8"),
        planned_sowing_time=time(6, 0),
        target_harvest_time=time(6, 0),
        germination_days=2,
        light_growth_days=7,
        seed_grams_per_set=Decimal("25"),
        expected_yield=qty("1"),
        production_granularity=Decimal("0.5"),
        harvest_min_lead_days=1,
        harvest_max_lead_days=2,
        temporal_buffer_minutes=0,
        provenance="approved-protocol",
    )


def policy() -> PlanningPolicySnapshot:
    return PlanningPolicySnapshot(
        reference=PolicyVersionReference("DEFAULT", 1),
        valid_from=date(2026, 1, 1),
        valid_to=None,
        quantitative_buffer_type="NONE",
        quantitative_buffer_value=None,
        priority_policy_code="DELIVERY_THEN_PUBLIC_ID",
        algorithm_version="production-planning-v1",
        harvest_target_strategy="EARLIEST_APPROVED_WINDOW",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("priority_policy_code", "UNKNOWN_PRIORITY"),
        ("algorithm_version", "unknown-algorithm"),
        ("harvest_target_strategy", "LATEST_WINDOW"),
    ),
)
def test_planning_policy_v1_rifiuta_vocabulary_sconosciuto(
    field: str, value: str
) -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        replace(policy(), **{field: value})


def test_planning_policy_v1_non_contiene_authority_estranee() -> None:
    fields = PlanningPolicySnapshot.__dataclass_fields__
    assert "timezone" not in fields
    assert "cutoff" not in fields
    assert "temporal_buffer_minutes" not in fields
    assert "production_granularity" not in fields
    assert "readiness" not in fields


def snapshot() -> PlanningInputSnapshot:
    return PlanningInputSnapshot(
        business_at=BUSINESS_AT,
        policy=policy(),
        demands=(demand(),),
        knowledge=(knowledge(),),
        stock=(),
        in_progress=(),
        harvests=(),
        allocations=(),
        current_plans=(),
        current_planning_lines=(),
    )


def candidate() -> PlanningCandidate:
    return PlanningCandidate(
        demand=demand(),
        knowledge=knowledge(),
        hydration_at=datetime(2026, 8, 3, 22, 0, tzinfo=UTC),
        sowing_at=datetime(2026, 8, 4, 6, 0, tzinfo=UTC),
        light_at=datetime(2026, 8, 6, 6, 0, tzinfo=UTC),
        harvest_target_at=datetime(2026, 8, 13, 6, 0, tzinfo=UTC),
        provenance="calculated",
    )


def write_set(run: ProductionPlanningRunSnapshot) -> ProductionPlanningCommit:
    line = PlanningLineDraft(
        public_id=pid("RPS-000001"),
        candidate=candidate(),
        state="PIANIFICATA",
        planning_key=HASH,
        expected_order_version=0,
        expected_order_line_version=0,
        stock_coverage=qty("0"),
        in_progress_coverage=qty("0"),
        allocated_harvest_coverage=qty("0"),
        production_deficit=qty("1"),
        quantitative_buffer_type="NONE",
        quantitative_buffer_value=None,
        calculated_quantitative_buffer=Decimal("0"),
        pre_granularity_quantity=Decimal("1"),
        authorized_productive_quantity=qty("1"),
        remaining_to_start=qty("1"),
        harvest_window_start=date(2026, 8, 12),
        harvest_window_end=date(2026, 8, 14),
    )
    revision = PlanRevisionDraft(
        plan_public_id=pid("PP-000001"),
        revision_public_id=pid("RVP-000001"),
        revision_number=1,
        request_key=HASH,
        lines=(line,),
        plan_state="APERTO",
    )
    return ProductionPlanningCommit(
        run=run,
        policy=PolicyVersionReference("DEFAULT", 1),
        business_at=BUSINESS_AT,
        context=command().context,
        revisions=(revision,),
        seed_resources=(SeedResourceDraft(pid("RPS-000001"), Decimal("25"), Decimal("25")),),
        allocations=(
            AllocationDraft(
                public_id=pid("ALL-000001"),
                allocation_type="DOMANDA",
                planning_line_public_id=pid("RPS-000001"),
                source_public_id=pid("RO-000001"),
                destination_order_line_public_id=pid("RO-000001"),
                quantity=qty("1"),
            ),
        ),
        allocation_transitions=(),
        messages=(),
        counters=ProductionPlanningRunCounters(1, 1, 0, 0, 1, 1, 0, 0, 0),
        audits=(
            AuditDraft(
                entity_type="PIANO_PRODUZIONE",
                entity_public_id=pid("PP-000001"),
                operation="INSERT",
                before_payload=(),
                after_payload=(("current_revision_public_id", "RVP-000001"), ("state", "APERTO")),
                provenance="production-planning:piano",
            ),
            AuditDraft(
                entity_type="PRODUCTION_PLANNING_RUN",
                entity_public_id=run.public_id,
                operation="STATE_TRANSITION",
                before_payload=(("state", "OPEN"),),
                after_payload=(("state", "COMMITTED"),),
                provenance="production-planning:run",
            ),
        ),
        input_snapshot=snapshot(),
    )


def result(run_id: PublicId) -> ProductionPlanningResult:
    revision_result = RevisionCommitResult(
        plan_public_id=pid("PP-000001"),
        revision_public_id=pid("RVP-000001"),
        revision_request_key=HASH,
        planning_key_v1=HASH,
        replanning_key_v1=None,
        reused_existing_revision=False,
    )
    return ProductionPlanningResult(
        planning_run_public_id=run_id,
        run_state="COMMITTED",
        plan_public_ids=(pid("PP-000001"),),
        current_revision_public_ids=(pid("RVP-000001"),),
        revision_results=(revision_result,),
        planning_line_public_ids=(pid("RPS-000001"),),
        allocation_public_ids=(pid("ALL-000001"),),
        committed_at=BUSINESS_AT,
        warnings=(),
    )


def test_command_e_value_objects_sono_immutabili() -> None:
    value = command()
    with pytest.raises(FrozenInstanceError):
        value.business_at = BUSINESS_AT  # type: ignore[misc]


@pytest.mark.parametrize("bad", ["", " PP-000001", "PP-1", "pp-000001"])
def test_public_id_rifiuta_formati_non_canonici(bad: str) -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        PublicId(bad)


def test_quantity_rifiuta_float_e_precisione_oltre_il_contratto() -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        ExactQuantity(0.5, UnitOfMeasure.SET)
    with pytest.raises(InvalidProductionPlanningModelError):
        ExactQuantity(Decimal("0.0000001"), UnitOfMeasure.SET)


def test_command_rifiuta_business_at_naive_e_policy_non_positiva() -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        InitialProductionPlanningCommand(
            datetime(2026, 8, 15, 6), PolicyVersionReference("DEFAULT", 1), command().context
        )
    with pytest.raises(InvalidProductionPlanningModelError):
        PolicyVersionReference("DEFAULT", 0)


def test_replanning_richiede_identita_e_reason_congelate() -> None:
    valid = ReplanProductionPlanningCommand(
        BUSINESS_AT,
        command().policy,
        command().context,
        pid("RVP-000001"),
        pid("RO-000001"),
        "STOCK_CHANGED",
    )
    assert valid.replanning_reason_code == "STOCK_CHANGED"
    with pytest.raises(InvalidProductionPlanningModelError):
        ReplanProductionPlanningCommand(
            BUSINESS_AT, command().policy, command().context,
            pid("RVP-000001"), pid("RO-000001"), "NEW_REASON"
        )


def test_domanda_preserva_authority_e_formula_del_residuo() -> None:
    assert demand().commercial_residual.value == Decimal("1")
    with pytest.raises(InvalidProductionPlanningModelError):
        DemandSnapshot(**{**demand().__dict__, "commercial_residual": qty("0.5")})


@pytest.mark.parametrize("approval_state", ["APPROVATA", "BOZZA", "RITIRATA"])
def test_protocol_approval_state_congelato_e_rappresentabile(approval_state: str) -> None:
    value = knowledge(approval_state)
    assert value.approval_state == approval_state


def test_protocol_approval_state_non_congelato_e_rifiutato() -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        knowledge("ARCHIVIATA")


def test_protocol_approval_state_e_immutabile() -> None:
    value = knowledge()
    with pytest.raises(FrozenInstanceError):
        value.approval_state = "BOZZA"  # type: ignore[misc]


def test_stock_snapshot_impone_saldo_e_ordine_deterministico() -> None:
    first = StockResourceSnapshot(pid("VAR-000001"), pid("VAR-000001"), qty("1"), qty("0"), qty("1"), 0, "READY")
    second = StockResourceSnapshot(pid("VAR-000002"), pid("VAR-000002"), qty("1"), qty("0"), qty("1"), 0, "READY")
    valid = PlanningInputSnapshot(**{**snapshot().__dict__, "stock": (first, second)})
    assert valid.stock == (first, second)
    with pytest.raises(InvalidProductionPlanningModelError):
        PlanningInputSnapshot(**{**snapshot().__dict__, "stock": (second, first)})


def test_active_allocation_usa_solo_tipo_e_stato_congelati() -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        ActiveAllocationSnapshot(**{**allocation_snapshot().__dict__, "allocation_type": "UNKNOWN"})


def test_active_allocation_snapshot_impone_formula_saldi_observed() -> None:
    value = allocation_snapshot()
    assert value.remaining_quantity.value == Decimal("1")
    with pytest.raises(InvalidProductionPlanningModelError):
        ActiveAllocationSnapshot(**{**value.__dict__, "remaining_quantity": qty("0.5")})


def test_allocation_transition_partial_e_full_consume() -> None:
    partial = allocation_transition()
    assert partial.target_state == "ATTIVA"
    assert partial.expected_remaining_after == Decimal("0.6")
    full = allocation_transition(
        target_state="CONSUMATA", consumed_quantity_delta=Decimal("1")
    )
    assert full.expected_remaining_after == Decimal("0")


def test_allocation_transition_partial_e_full_invalidation() -> None:
    partial = allocation_transition(
        consumed_quantity_delta=Decimal("0"),
        invalidated_quantity_delta=Decimal("0.2"),
    )
    assert partial.target_state == "ATTIVA"
    full = allocation_transition(
        target_state="INVALIDA",
        consumed_quantity_delta=Decimal("0"),
        invalidated_quantity_delta=Decimal("1"),
    )
    assert full.expected_remaining_after == Decimal("0")


def test_allocation_transition_consume_e_disposizione_residuale() -> None:
    released = allocation_transition(
        target_state="RILASCIATA",
        released_quantity_delta=Decimal("0.6"),
    )
    transferred = allocation_transition(
        target_state="SOSTITUITA",
        transferred_quantity_delta=Decimal("0.6"),
        replacement_allocation_public_id=pid("ALL-000002"),
    )
    assert released.expected_remaining_after == transferred.expected_remaining_after == Decimal("0")


@pytest.mark.parametrize(
    "changes",
    [
        {"observed_remaining_quantity": Decimal("0.5")},
        {"consumed_quantity_delta": Decimal("-0.1")},
        {"consumed_quantity_delta": Decimal("0"), "released_quantity_delta": Decimal("0")},
        {"released_quantity_delta": Decimal("0.3"), "transferred_quantity_delta": Decimal("0.3"), "replacement_allocation_public_id": pid("ALL-000002")},
        {"transferred_quantity_delta": Decimal("0.6")},
        {"replacement_allocation_public_id": pid("ALL-000002")},
        {"current_state": "CONSUMATA"},
        {"consumed_quantity_delta": Decimal("1.1")},
        {"consumed_quantity_delta": 0.4},
    ],
)
def test_allocation_transition_rifiuta_combinazioni_incoerenti(changes) -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        allocation_transition(**changes)


def test_allocation_transition_target_state_deriva_dai_saldi() -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        allocation_transition(target_state="CONSUMATA")
    with pytest.raises(InvalidProductionPlanningModelError):
        allocation_transition(target_state="ATTIVA", consumed_quantity_delta=Decimal("1"))


def test_allocation_transition_e_immutabile() -> None:
    value = allocation_transition()
    with pytest.raises(FrozenInstanceError):
        value.target_state = "CONSUMATA"  # type: ignore[misc]


@pytest.mark.parametrize("cause", ["DEMAND_REDUCED", "DEMAND_CANCELLED"])
def test_allocation_disposition_release_per_domanda_e_source_reusable(cause: str) -> None:
    decision = disposition_decision(disposition_cause=cause)
    transition = decision.to_transition_draft(allocation_snapshot())
    assert transition.target_state == "RILASCIATA"
    assert transition.released_quantity_delta == Decimal("1")
    assert transition.replacement_allocation_public_id is None


@pytest.mark.parametrize("cause", ["REALLOCATION_REQUIRED", "REVISION_REPLACEMENT"])
def test_allocation_disposition_replacement_esplicita(cause: str) -> None:
    decision = disposition_decision(
        disposition_cause=cause,
        source_usability="TRANSFERABLE_ONLY",
        target_disposition="SOSTITUITA",
        replacement_specification=replacement_specification(),
    )
    transition = decision.to_transition_draft(allocation_snapshot())
    assert transition.target_state == "SOSTITUITA"
    assert transition.transferred_quantity_delta == Decimal("1")
    assert transition.replacement_allocation_public_id == pid("ALL-000002")


@pytest.mark.parametrize(
    "cause",
    [
        "SOURCE_UNUSABLE",
        "SEEDING_FAILED",
        "HARVEST_UNAVAILABLE",
        "STOCK_QUANTITY_INVALIDATED",
    ],
)
def test_allocation_disposition_invalidation_per_source_non_usabile(cause: str) -> None:
    decision = disposition_decision(
        disposition_cause=cause,
        source_usability="UNUSABLE",
        target_disposition="INVALIDA",
    )
    transition = decision.to_transition_draft(allocation_snapshot())
    assert transition.target_state == "INVALIDA"
    assert transition.invalidated_quantity_delta == Decimal("1")


def test_protocol_retirement_non_e_una_causa_di_invalidation() -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        disposition_decision(
            disposition_cause="PROTOCOL_RETIRED",
            source_usability="UNUSABLE",
            target_disposition="INVALIDA",
        )


@pytest.mark.parametrize(
    "changes",
    [
        {
            "disposition_cause": "REALLOCATION_REQUIRED",
            "source_usability": "TRANSFERABLE_ONLY",
            "target_disposition": "SOSTITUITA",
        },
        {"replacement_specification": replacement_specification()},
        {
            "source_usability": "UNUSABLE",
            "target_disposition": "INVALIDA",
        },
        {
            "disposition_cause": "SOURCE_UNUSABLE",
            "source_usability": "REUSABLE",
            "target_disposition": "RILASCIATA",
        },
        {"expected_version": -1},
        {"observed_remaining_quantity": Decimal("0")},
        {"observed_remaining_quantity": Decimal("1"), "consumed_quantity_delta": Decimal("1")},
        {"observed_remaining_quantity": 1.0},
    ],
)
def test_allocation_disposition_rifiuta_combinazioni_non_autorizzate(changes) -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        disposition_decision(**changes)


def test_allocation_disposition_partial_consumption_mapping_deterministico() -> None:
    decision = disposition_decision(
        observed_remaining_quantity=Decimal("1"),
        consumed_quantity_delta=Decimal("0.4"),
    )
    first = decision.to_transition_draft(allocation_snapshot())
    second = decision.to_transition_draft(allocation_snapshot())
    assert first == second
    assert first.consumed_quantity_delta == Decimal("0.4")
    assert first.released_quantity_delta == Decimal("0.6")
    assert first.expected_remaining_after == Decimal("0")


def test_allocation_replacement_impone_quantita_uom_e_identita_coerenti() -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        disposition_decision(
            disposition_cause="REALLOCATION_REQUIRED",
            source_usability="TRANSFERABLE_ONLY",
            target_disposition="SOSTITUITA",
            replacement_specification=replacement_specification(quantity=qty("0.5")),
        )
    decision = disposition_decision(
        disposition_cause="REALLOCATION_REQUIRED",
        source_usability="TRANSFERABLE_ONLY",
        target_disposition="SOSTITUITA",
        replacement_specification=replacement_specification(
            quantity=qty("1", UnitOfMeasure.GRAM)
        ),
    )
    with pytest.raises(InvalidProductionPlanningModelError):
        decision.to_transition_draft(allocation_snapshot())


def test_allocation_disposition_models_sono_immutabili_e_provider_neutral() -> None:
    decision = disposition_decision()
    with pytest.raises(FrozenInstanceError):
        decision.target_disposition = "INVALIDA"  # type: ignore[misc]
    annotations = get_type_hints(AllocationDispositionDecision)
    assert all(
        forbidden not in repr(annotations)
        for forbidden in ("psycopg", "sqlalchemy", "Connection", "Cursor")
    )


def test_commit_allocation_transitions_uniche_e_ordinate() -> None:
    base = write_set(ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN"))
    first = allocation_transition()
    second = allocation_transition(
        allocation_public_id=pid("ALL-000002"),
        consumed_quantity_delta=Decimal("0.2"),
    )
    value = ProductionPlanningCommit(
        **{**base.__dict__, "allocation_transitions": (first, second)}
    )
    assert value.allocation_transitions == (first, second)
    with pytest.raises(InvalidProductionPlanningModelError):
        ProductionPlanningCommit(
            **{**base.__dict__, "allocation_transitions": (second, first)}
        )
    with pytest.raises(InvalidProductionPlanningModelError):
        ProductionPlanningCommit(
            **{**base.__dict__, "allocation_transitions": (first, first)}
        )


def test_candidate_rappresenta_backplanning_senza_calcolarlo() -> None:
    value = candidate()
    assert value.hydration_at < value.sowing_at < value.light_at < value.harvest_target_at
    with pytest.raises(InvalidProductionPlanningModelError):
        PlanningCandidate(**{**value.__dict__, "sowing_at": value.harvest_target_at})


def test_revisioni_iniziale_e_replanning_non_possono_mescolare_forme() -> None:
    line = write_set(ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN")).revisions[0].lines
    with pytest.raises(InvalidProductionPlanningModelError):
        PlanRevisionDraft(
            pid("PP-000001"), pid("RVP-000001"), 1, HASH, line, "APERTO",
            previous_revision_public_id=pid("RVP-000000"),
        )
    with pytest.raises(InvalidProductionPlanningModelError):
        PlanRevisionDraft(pid("PP-000001"), pid("RVP-000002"), 2, HASH, line, "APERTO")


def test_line_draft_espone_il_write_set_quantitativo_completo() -> None:
    line = write_set(ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN")).revisions[0].lines[0]
    assert line.stock_coverage.value == Decimal("0")
    assert line.production_deficit.value == Decimal("1")
    assert "productive_quantity" not in line.candidate.__dataclass_fields__
    assert line.harvest_window_start == date(2026, 8, 12)
    with pytest.raises(InvalidProductionPlanningModelError):
        PlanningLineDraft(**{**line.__dict__, "production_deficit": qty("0.5")})


def zero_production_line(
    *, stock: str = "1", harvest: str = "0", in_progress: str = "0"
) -> PlanningLineDraft:
    base = write_set(
        ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN")
    ).revisions[0].lines[0]
    return replace(
        base,
        stock_coverage=qty(stock),
        allocated_harvest_coverage=qty(harvest),
        in_progress_coverage=qty(in_progress),
        production_deficit=qty("0"),
        calculated_quantitative_buffer=Decimal("0"),
        pre_granularity_quantity=Decimal("0"),
        authorized_productive_quantity=qty("0"),
        remaining_to_start=qty("0"),
    )


def commit_with_line(
    line: PlanningLineDraft, *, seed_resources: tuple[SeedResourceDraft, ...]
) -> ProductionPlanningCommit:
    base = write_set(ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN"))
    revision = replace(base.revisions[0], lines=(line,))
    return replace(base, revisions=(revision,), seed_resources=seed_resources)


def test_full_stock_coverage_ammette_planning_line_a_produzione_zero() -> None:
    line = zero_production_line()
    commit = commit_with_line(line, seed_resources=())
    assert line.production_deficit.value == Decimal("0")
    assert line.authorized_productive_quantity.value == Decimal("0")
    assert commit.seed_resources == ()


def test_full_mixed_coverage_ammette_planning_line_a_produzione_zero() -> None:
    line = zero_production_line(stock="0.4", harvest="0.3", in_progress="0.3")
    commit = commit_with_line(line, seed_resources=())
    assert sum(
        quantity.value
        for quantity in (
            line.stock_coverage,
            line.allocated_harvest_coverage,
            line.in_progress_coverage,
        )
    ) == Decimal("1")
    assert commit.seed_resources == ()


@pytest.mark.parametrize(
    "changes",
    [
        {"production_deficit": qty("0.1")},
        {"calculated_quantitative_buffer": Decimal("0.1")},
        {"pre_granularity_quantity": Decimal("0.1")},
        {"remaining_to_start": qty("0.1")},
        {"stock_coverage": qty("0.9")},
    ],
)
def test_produzione_zero_richiede_full_coverage_e_calcolo_zero(changes) -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        replace(zero_production_line(), **changes)


def test_seed_resource_cardinality_e_condizionale() -> None:
    base = write_set(ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN"))
    assert len(base.seed_resources) == 1
    with pytest.raises(InvalidProductionPlanningModelError):
        replace(base, seed_resources=())

    zero_line = zero_production_line()
    with pytest.raises(InvalidProductionPlanningModelError):
        commit_with_line(
            zero_line,
            seed_resources=(
                SeedResourceDraft(zero_line.public_id, Decimal("25"), Decimal("25")),
            ),
        )


def test_seed_resource_zero_e_orfano_sono_rifiutati() -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        SeedResourceDraft(pid("RPS-000001"), Decimal("0"), Decimal("25"))
    base = write_set(ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN"))
    with pytest.raises(InvalidProductionPlanningModelError):
        replace(
            base,
            seed_resources=(
                SeedResourceDraft(pid("RPS-999999"), Decimal("25"), Decimal("25")),
            ),
        )


def test_conditional_seed_contract_e_immutabile_e_provider_neutral() -> None:
    line = zero_production_line()
    with pytest.raises(FrozenInstanceError):
        line.authorized_productive_quantity = qty("1")  # type: ignore[misc]
    hints = repr(get_type_hints(ProductionPlanningCommit)).lower()
    assert all(name not in hints for name in ("psycopg", "sqlalchemy", "connection"))


def test_replanning_snapshot_conserva_testo_hash_versioni_e_input_persistenti() -> None:
    canonical_text = "TPO-REPLANNING-V1|ORDER=ORD-000001"
    value = CanonicalReplanningSnapshot(
        previous_revision_public_id=pid("RVP-000001"),
        previous_plan_revision_version=2,
        order_line_public_id=pid("RO-000001"),
        order_public_id=pid("ORD-000001"),
        order_state=OrdineState.APERTO,
        order_version=3,
        order_line_version=4,
        ordered_quantity=qty("1"),
        delivered_quantity=qty("0"),
        commercial_residual_quantity=qty("1"),
        delivery_date=date(2026, 8, 15),
        variety_public_id=pid("VAR-000001"),
        protocol_version_public_id=pid("PV-000001"),
        protocol_version_number=1,
        protocol_valid_from=date(2026, 1, 1),
        protocol_valid_to=None,
        reason_code="STOCK_CHANGED",
        policy=PolicyVersionReference("DEFAULT", 1),
        quantitative_buffer_type="NONE",
        quantitative_buffer_value=None,
        temporal_buffer_minutes=0,
        production_granularity=Decimal("0.5"),
        stock=(),
        in_progress=(),
        allocations=(),
        canonical_text=canonical_text,
        canonical_snapshot_hash=CanonicalHash(hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()),
        replanning_key_v1=CanonicalHash("b" * 64),
    )
    assert value.previous_plan_revision_version == 2
    assert value.canonical_text.startswith("TPO-REPLANNING-V1")
    with pytest.raises(InvalidProductionPlanningModelError):
        CanonicalReplanningSnapshot(**{**value.__dict__, "canonical_snapshot_hash": HASH})


def test_commit_richiede_contatori_e_audit_immutabili_e_ordinati() -> None:
    value = write_set(ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN"))
    assert value.counters.planning_lines_generated == 1
    assert value.audits[0].entity_type == "PIANO_PRODUZIONE"
    with pytest.raises(FrozenInstanceError):
        value.counters.orders_read = 2  # type: ignore[misc]
    with pytest.raises(InvalidProductionPlanningModelError):
        ProductionPlanningCommit(**{**value.__dict__, "audits": tuple(reversed(value.audits))})


def test_audit_draft_richiede_provenance_ed_e_immutabile() -> None:
    audit = write_set(ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN")).audits[0]
    assert audit.provenance == "production-planning:piano"
    with pytest.raises(FrozenInstanceError):
        audit.provenance = "changed"  # type: ignore[misc]
    with pytest.raises(InvalidProductionPlanningModelError):
        replace(audit, provenance="")
    with pytest.raises(InvalidProductionPlanningModelError):
        replace(audit, provenance=" not-normalized")


def test_audit_context_e_autorevole_e_non_duplicato_nei_draft() -> None:
    value = write_set(ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN"))
    fields = AuditDraft.__dataclass_fields__
    assert "actor" not in fields
    assert "reason" not in fields
    assert "correlation_id" not in fields
    assert value.context == command().context
    assert len({audit.provenance for audit in value.audits}) == len(value.audits)
    for audit in value.audits:
        payload_keys = {key for key, _ in audit.before_payload + audit.after_payload}
        assert payload_keys.isdisjoint({"actor", "reason", "correlation_id", "provenance"})


def test_revision_result_initial_associa_univocamente_la_chiave() -> None:
    value = result(pid("RPP-000001")).revision_results[0]
    assert value.revision_request_key == value.planning_key_v1
    assert value.replanning_key_v1 is None


def test_revision_result_replanning_associa_univocamente_la_chiave() -> None:
    key = CanonicalHash("b" * 64)
    value = RevisionCommitResult(
        pid("PP-000001"), pid("RVP-000002"), key, None, key, True
    )
    assert value.reused_existing_revision is True
    with pytest.raises(InvalidProductionPlanningModelError):
        RevisionCommitResult(pid("PP-000001"), pid("RVP-000002"), HASH, None, key, False)


def test_result_multi_revisione_preserva_associazione_e_replay_parziale() -> None:
    first_key = CanonicalHash("a" * 64)
    second_key = CanonicalHash("b" * 64)
    revisions = (
        RevisionCommitResult(pid("PP-000001"), pid("RVP-000001"), first_key, first_key, None, True),
        RevisionCommitResult(pid("PP-000002"), pid("RVP-000002"), second_key, second_key, None, False),
    )
    value = ProductionPlanningResult(
        planning_run_public_id=pid("RPP-000001"),
        run_state="COMMITTED",
        plan_public_ids=tuple(item.plan_public_id for item in revisions),
        current_revision_public_ids=tuple(item.revision_public_id for item in revisions),
        revision_results=revisions,
        planning_line_public_ids=(pid("RPS-000001"), pid("RPS-000002")),
        allocation_public_ids=(),
        committed_at=BUSINESS_AT,
        warnings=(),
    )
    assert tuple(item.reused_existing_revision for item in value.revision_results) == (True, False)
    assert tuple(item.revision_request_key for item in value.revision_results) == (first_key, second_key)
    with pytest.raises(InvalidProductionPlanningModelError):
        ProductionPlanningResult(**{**value.__dict__, "revision_results": tuple(reversed(revisions))})


def test_revision_result_e_immutabile_e_vieta_chiavi_ambigue() -> None:
    value = result(pid("RPP-000001")).revision_results[0]
    with pytest.raises(FrozenInstanceError):
        value.reused_existing_revision = True  # type: ignore[misc]
    with pytest.raises(InvalidProductionPlanningModelError):
        RevisionCommitResult(pid("PP-000001"), pid("RVP-000001"), HASH, HASH, HASH, False)


def test_snapshot_espone_expected_version_delle_righe_planning_correnti() -> None:
    current = CurrentPlanningLineSnapshot(
        planning_line_public_id=pid("RPS-000001"),
        revision_public_id=pid("RVP-000001"),
        order_line_public_id=pid("RO-000001"),
        state="PIANIFICATA",
        version=7,
    )
    value = PlanningInputSnapshot(**{**snapshot().__dict__, "current_planning_lines": (current,)})
    assert value.current_planning_lines[0].version == 7


def test_new_allocation_e_attiva_e_tipizzata() -> None:
    allocation = write_set(ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN")).allocations[0]
    assert allocation.state == "ATTIVA"
    with pytest.raises(InvalidProductionPlanningModelError):
        AllocationDraft(**{**allocation.__dict__, "state": "CONSUMATA"})


class FakeIdentity:
    calls: list[str]

    def __init__(self) -> None:
        self.calls = []

    def allocate(self, sequence_name: str) -> PublicId:
        self.calls.append(sequence_name)
        return pid("RPP-000001")


class FakeInputs:
    def load(self, requested):
        return snapshot()


class FakeRuns:
    def __init__(self) -> None:
        self.opened = []
        self.failures = []
        self.reconciliations = []

    def open(self, **kwargs):
        self.opened.append(kwargs)
        return ProductionPlanningRunSnapshot(kwargs["public_id"], 0, "OPEN")

    def finalize_failure(self, **kwargs):
        self.failures.append(kwargs)

    def require_reconciliation(self, **kwargs):
        self.reconciliations.append(kwargs)
        return ProductionPlanningReconciliationRequiredResult(
            planning_run_public_id=kwargs["run"].public_id,
            run_state="RECONCILIATION_REQUIRED",
            business_at=kwargs["business_at"],
            observed_at=kwargs["observed_at"],
            correlation_id=kwargs["correlation_id"],
            failure_category=kwargs["error"].category,
            code=kwargs["error"].code,
            message=kwargs["error"].safe_message,
        )


class FakeCommit:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = []

    def commit(self, value, *, completed_at):
        self.calls.append((value, completed_at))
        if self.error:
            raise self.error
        return result(value.run.public_id)


class FakeClock:
    def now(self) -> datetime:
        return BUSINESS_AT


def service(commit_port: FakeCommit, runs: FakeRuns) -> ProductionPlanningService:
    return ProductionPlanningService(
        identity=FakeIdentity(), inputs=FakeInputs(), runs=runs, commit=commit_port,
        clock=FakeClock(), build_commit=lambda _command, _snapshot, run: write_set(run),
    )


def test_service_orchestra_run_snapshot_e_commit_senza_calcolo_interno() -> None:
    runs = FakeRuns()
    commit_port = FakeCommit()
    output = service(commit_port, runs).execute(command())
    assert output.run_state == "COMMITTED"
    assert len(runs.opened) == 1
    assert len(commit_port.calls) == 1
    assert runs.failures == []


def test_failure_certa_finalizza_run_e_non_viene_ritentata() -> None:
    runs = FakeRuns()
    error = ProductionPlanningError("CONCURRENCY_CONFLICT", "ORDER_CHANGED", "Input mutato.")
    commit_port = FakeCommit(error)
    with pytest.raises(ProductionPlanningError) as captured:
        service(commit_port, runs).execute(command())
    assert captured.value is error
    assert len(commit_port.calls) == 1
    assert len(runs.failures) == 1
    assert runs.failures[0]["messages"][0].failure_category == "CONCURRENCY_CONFLICT"


def test_outcome_incerto_usa_reconciliation_e_non_failure_finalization() -> None:
    runs = FakeRuns()
    output = service(FakeCommit(ProductionPlanningOutcomeUncertain()), runs).execute(command())
    assert output.run_state == "RECONCILIATION_REQUIRED"
    assert output.correlation_id == command().context.correlation_id
    assert output.business_at == command().business_at
    assert runs.failures == []
    assert len(runs.reconciliations) == 1


def test_result_committed_non_puo_rappresentare_outcome_incerto() -> None:
    committed = result(pid("RPP-000001"))
    assert committed.run_state == "COMMITTED"
    with pytest.raises(InvalidProductionPlanningModelError):
        ProductionPlanningResult(
            **{**committed.__dict__, "run_state": "RECONCILIATION_REQUIRED"}
        )


def test_uncertain_result_e_minimale_immutabile_e_senza_dati_committed() -> None:
    value = ProductionPlanningReconciliationRequiredResult(
        planning_run_public_id=pid("RPP-000001"),
        run_state="RECONCILIATION_REQUIRED",
        business_at=BUSINESS_AT,
        observed_at=BUSINESS_AT,
        correlation_id="corr-1",
        failure_category="RECONCILIATION_REQUIRED",
        code="COMMIT_OUTCOME_UNCERTAIN",
        message="Esito del commit non determinabile.",
    )
    assert set(value.__dataclass_fields__) == {
        "planning_run_public_id",
        "run_state",
        "business_at",
        "observed_at",
        "correlation_id",
        "failure_category",
        "code",
        "message",
    }
    forbidden = {
        "plan_public_ids",
        "current_revision_public_ids",
        "revision_results",
        "planning_line_public_ids",
        "allocation_public_ids",
        "committed_at",
        "reused_existing_revision",
    }
    assert forbidden.isdisjoint(value.__dataclass_fields__)
    with pytest.raises(FrozenInstanceError):
        value.run_state = "COMMITTED"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field_name", "value"),
    (("run_state", "COMMITTED"), ("failure_category", "INTERNAL_ERROR")),
)
def test_uncertain_result_rifiuta_stato_o_categoria_non_coerenti(
    field_name: str, value: str
) -> None:
    fields = {
        "planning_run_public_id": pid("RPP-000001"),
        "run_state": "RECONCILIATION_REQUIRED",
        "business_at": BUSINESS_AT,
        "observed_at": BUSINESS_AT,
        "correlation_id": "corr-1",
        "failure_category": "RECONCILIATION_REQUIRED",
        "code": "COMMIT_OUTCOME_UNCERTAIN",
        "message": "Esito del commit non determinabile.",
    }
    fields[field_name] = value
    with pytest.raises(InvalidProductionPlanningModelError):
        ProductionPlanningReconciliationRequiredResult(**fields)


def test_public_outcome_union_e_provider_neutral() -> None:
    assert ProductionPlanningRunOutcome == (
        ProductionPlanningResult | ProductionPlanningReconciliationRequiredResult
    )


def test_port_return_types_distinguono_successo_e_riconciliazione() -> None:
    assert get_type_hints(ProductionPlanningCommitPort.commit)["return"] is ProductionPlanningResult
    assert (
        get_type_hints(ProductionPlanningRunPort.require_reconciliation)["return"]
        is ProductionPlanningReconciliationRequiredResult
    )


def test_failure_inattesa_e_sanitizzata_e_finalizzata_come_internal_error() -> None:
    runs = FakeRuns()
    with pytest.raises(ProductionPlanningError) as captured:
        service(FakeCommit(RuntimeError("password=private")), runs).execute(command())
    assert captured.value.category == "INTERNAL_ERROR"
    assert "private" not in str(captured.value)
    assert len(runs.failures) == 1


def test_application_layer_non_importa_provider_o_google() -> None:
    root = Path(__file__).parents[3] / "src/tpo_core/application/production_planning"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = ("sqlalchemy", "psycopg", "alembic", "google_sheets", "googleapiclient")
    assert all(name not in source.lower() for name in forbidden)
