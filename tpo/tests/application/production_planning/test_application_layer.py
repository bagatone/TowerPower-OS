from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.tpo_core.application.production_planning.errors import (
    InvalidProductionPlanningModelError,
    ProductionPlanningError,
    ProductionPlanningOutcomeUncertain,
)
from src.tpo_core.application.production_planning.models import (
    ActiveAllocationSnapshot,
    AllocationDraft,
    CanonicalHash,
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
    ProductionPlanningResult,
    ProductionPlanningRunSnapshot,
    PublicId,
    ReplanProductionPlanningCommand,
    RunMessage,
    SeedResourceDraft,
    StockResourceSnapshot,
)
from src.tpo_core.application.production_planning.service import ProductionPlanningService
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


def knowledge() -> ProductionKnowledgeSnapshot:
    return ProductionKnowledgeSnapshot(
        protocol_version_public_id=pid("PV-000001"),
        protocol_version_number=1,
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
        timezone="Atlantic/Canary",
        valid_from=date(2026, 1, 1),
        valid_to=None,
        quantitative_buffer_type="NONE",
        quantitative_buffer_value=None,
        priority_policy_code="DELIVERY_THEN_PUBLIC_ID",
        algorithm_version="production-planning-v1",
    )


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
    )


def candidate() -> PlanningCandidate:
    return PlanningCandidate(
        demand=demand(),
        knowledge=knowledge(),
        hydration_at=datetime(2026, 8, 3, 22, 0, tzinfo=UTC),
        sowing_at=datetime(2026, 8, 4, 6, 0, tzinfo=UTC),
        light_at=datetime(2026, 8, 6, 6, 0, tzinfo=UTC),
        harvest_target_at=datetime(2026, 8, 13, 6, 0, tzinfo=UTC),
        productive_quantity=qty("1"),
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
    )
    revision = PlanRevisionDraft(
        plan_public_id=pid("PP-000001"),
        revision_public_id=pid("RVP-000001"),
        revision_number=1,
        request_key=HASH,
        lines=(line,),
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
        messages=(),
        input_snapshot=snapshot(),
    )


def result(run_id: PublicId, *, state: str = "COMMITTED") -> ProductionPlanningResult:
    return ProductionPlanningResult(
        planning_run_public_id=run_id,
        run_state=state,
        plan_public_ids=(pid("PP-000001"),),
        current_revision_public_ids=(pid("RVP-000001"),),
        planning_line_public_ids=(pid("RPS-000001"),),
        allocation_public_ids=(pid("ALL-000001"),),
        planning_key_v1=HASH,
        replanning_key_v1=None,
        reused_existing_revision=False,
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


def test_stock_snapshot_impone_saldo_e_ordine_deterministico() -> None:
    first = StockResourceSnapshot(pid("VAR-000001"), pid("VAR-000001"), qty("1"), qty("0"), qty("1"), 0, "READY")
    second = StockResourceSnapshot(pid("VAR-000002"), pid("VAR-000002"), qty("1"), qty("0"), qty("1"), 0, "READY")
    valid = PlanningInputSnapshot(**{**snapshot().__dict__, "stock": (first, second)})
    assert valid.stock == (first, second)
    with pytest.raises(InvalidProductionPlanningModelError):
        PlanningInputSnapshot(**{**snapshot().__dict__, "stock": (second, first)})


def test_active_allocation_usa_solo_tipo_e_stato_congelati() -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        ActiveAllocationSnapshot(
            pid("ALL-000001"), "UNKNOWN", pid("VAR-000001"), pid("RO-000001"), qty("1"), "ATTIVA", 0
        )


def test_candidate_rappresenta_backplanning_senza_calcolarlo() -> None:
    value = candidate()
    assert value.hydration_at < value.sowing_at < value.light_at < value.harvest_target_at
    with pytest.raises(InvalidProductionPlanningModelError):
        PlanningCandidate(**{**value.__dict__, "sowing_at": value.harvest_target_at})


def test_revisioni_iniziale_e_replanning_non_possono_mescolare_forme() -> None:
    line = write_set(ProductionPlanningRunSnapshot(pid("RPP-000001"), 0, "OPEN")).revisions[0].lines
    with pytest.raises(InvalidProductionPlanningModelError):
        PlanRevisionDraft(pid("PP-000001"), pid("RVP-000001"), 1, HASH, line, pid("RVP-000000"))
    with pytest.raises(InvalidProductionPlanningModelError):
        PlanRevisionDraft(pid("PP-000001"), pid("RVP-000002"), 2, HASH, line)


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
        return result(kwargs["run"].public_id, state="RECONCILIATION_REQUIRED")


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
    assert runs.failures == []
    assert len(runs.reconciliations) == 1


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
