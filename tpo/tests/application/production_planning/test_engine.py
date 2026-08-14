from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.production_planning.engine import ProductionPlanningEngine
from src.tpo_core.application.production_planning.errors import ProductionPlanningError
from src.tpo_core.application.production_planning.models import (
    DemandSnapshot,
    ExactQuantity,
    PlanningInputSnapshot,
    PlanningPolicySnapshot,
    PolicyVersionReference,
    ProductionKnowledgeSnapshot,
    PublicId,
)
from src.tpo_core.domain.quantities import UnitOfMeasure
from src.tpo_core.domain.states import OrdineState
from src.tpo_core.domain.time_reference import OFFICIAL_TIMEZONE


CANARY = ZoneInfo("Atlantic/Canary")


def pid(value: str) -> PublicId:
    return PublicId(value)


def qty(value: str) -> ExactQuantity:
    return ExactQuantity(Decimal(value), UnitOfMeasure.SET)


def demand(
    *, order: str = "ORD-000001", line: str = "RO-000001", variety: str = "VAR-000001",
    delivery: date = date(2026, 8, 15), amount: str = "1", priority: int | None = None,
) -> DemandSnapshot:
    return DemandSnapshot(
        order_public_id=pid(order), order_line_public_id=pid(line), order_version=0,
        order_line_version=0, order_state=OrdineState.APERTO,
        variety_public_id=pid(variety), ordered=qty(amount), delivered=qty("0"),
        commercial_residual=qty(amount), order_date=date(2026, 8, 1),
        delivery_date=delivery, commercial_priority=priority, provenance="ORDINI",
    )


def protocol(
    *, public_id: str = "PV-000001", variety: str = "VAR-000001",
    approval: str = "APPROVATA", germination: int = 2, growth: int = 7,
) -> ProductionKnowledgeSnapshot:
    return ProductionKnowledgeSnapshot(
        protocol_version_public_id=pid(public_id), protocol_version_number=1,
        approval_state=approval, variety_public_id=pid(variety), cultivar_reference="Afila",
        productive_use_reference="MICROGREEN", valid_from=date(2026, 1, 1), valid_to=None,
        hydration_hours=Decimal("8"), planned_sowing_time=time(6),
        target_harvest_time=time(6), germination_days=germination,
        light_growth_days=growth, seed_grams_per_set=Decimal("25"),
        expected_yield=qty("1"), production_granularity=Decimal("0.5"),
        harvest_min_lead_days=1, harvest_max_lead_days=2,
        temporal_buffer_minutes=0, provenance="PROTOCOLLO_APPROVATO",
    )


def snapshot(
    demands: tuple[DemandSnapshot, ...] | None = None,
    knowledge: tuple[ProductionKnowledgeSnapshot, ...] | None = None,
) -> PlanningInputSnapshot:
    return PlanningInputSnapshot(
        business_at=datetime(2026, 8, 1, 6, tzinfo=CANARY),
        policy=PlanningPolicySnapshot(
            PolicyVersionReference("DEFAULT", 1), date(2026, 1, 1),
            None, "NONE", None, "DELIVERY_THEN_PUBLIC_ID", "production-planning-v1",
            "EARLIEST_APPROVED_WINDOW",
        ),
        demands=demands or (demand(),), knowledge=knowledge or (protocol(),), stock=(),
        in_progress=(), harvests=(), allocations=(), current_plans=(),
        current_planning_lines=(),
    )


def test_singola_varieta_calcola_backplanning_completo() -> None:
    candidate = ProductionPlanningEngine().calculate(snapshot())[0]
    assert candidate.demand.delivery_date == date(2026, 8, 15)
    assert candidate.harvest_target_at == datetime(2026, 8, 13, 6, tzinfo=CANARY)
    assert candidate.sowing_at == datetime(2026, 8, 4, 6, tzinfo=CANARY)
    assert candidate.light_at == datetime(2026, 8, 6, 6, tzinfo=CANARY)
    assert candidate.hydration_at == datetime(2026, 8, 3, 22, tzinfo=CANARY)
    assert candidate.productive_quantity.value == Decimal("1.0")
    assert candidate.provenance == "ORDINI|PROTOCOLLO_APPROVATO"


def test_engine_usa_esclusivamente_timezone_ufficiale() -> None:
    from src.tpo_core.application.production_planning import engine

    assert engine.OFFICIAL_TIMEZONE is OFFICIAL_TIMEZONE
    assert "_TIMEZONE" not in vars(engine)


def test_engine_non_introduce_cutoff_o_readiness_nella_policy() -> None:
    fields = PlanningPolicySnapshot.__dataclass_fields__
    assert "cutoff" not in fields
    assert "readiness" not in fields


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("priority_policy_code", "UNKNOWN_PRIORITY"),
        ("algorithm_version", "unknown-algorithm"),
        ("harvest_target_strategy", "LATEST_WINDOW"),
    ),
)
def test_engine_rifiuta_policy_v1_non_supportata(field: str, value: str) -> None:
    invalid = snapshot()
    object.__setattr__(invalid.policy, field, value)

    with pytest.raises(ProductionPlanningError) as raised:
        ProductionPlanningEngine().calculate(invalid)

    assert raised.value.code == "UNSUPPORTED_PLANNING_POLICY"


def test_piu_varieta_e_ordine_jaira_producono_un_candidato_per_riga() -> None:
    demands = (
        demand(order="ORD-000010", line="RO-000010", variety="VAR-000001", amount="1"),
        demand(order="ORD-000010", line="RO-000011", variety="VAR-000002", amount="0.5"),
        demand(order="ORD-000010", line="RO-000012", variety="VAR-000003", amount="0.5"),
    )
    protocols = (
        protocol(public_id="PV-000001", variety="VAR-000001"),
        protocol(public_id="PV-000002", variety="VAR-000002"),
        protocol(public_id="PV-000003", variety="VAR-000003"),
    )
    result = ProductionPlanningEngine().calculate(snapshot(demands, protocols))
    assert [item.demand.order_line_public_id.value for item in result] == [
        "RO-000010", "RO-000011", "RO-000012"
    ]
    assert [item.productive_quantity.value for item in result] == [
        Decimal("1.0"), Decimal("0.5"), Decimal("0.5")
    ]


@pytest.mark.parametrize("approval", ["BOZZA", "RITIRATA"])
def test_protocollo_non_approvato_fallisce_chiuso(approval: str) -> None:
    with pytest.raises(ProductionPlanningError) as captured:
        ProductionPlanningEngine().calculate(snapshot(knowledge=(protocol(approval=approval),)))
    assert captured.value.category == "PRODUCTION_KNOWLEDGE_INVALID"
    assert captured.value.code == "PROTOCOL_NOT_AVAILABLE"


def test_protocollo_assente_fallisce_chiuso() -> None:
    value = snapshot()
    value = replace(value, knowledge=())
    with pytest.raises(ProductionPlanningError) as captured:
        ProductionPlanningEngine().calculate(value)
    assert captured.value.code == "PROTOCOL_NOT_AVAILABLE"


def test_protocollo_ambiguo_fallisce_chiuso() -> None:
    protocols = (protocol(), protocol(public_id="PV-000002"))
    with pytest.raises(ProductionPlanningError) as captured:
        ProductionPlanningEngine().calculate(snapshot(knowledge=protocols))
    assert captured.value.code == "PROTOCOL_AMBIGUOUS"


def test_output_e_deterministico_indipendentemente_dall_ordine_input() -> None:
    late = demand(order="ORD-000001", line="RO-000001", delivery=date(2026, 8, 15))
    early = demand(
        order="ORD-000002", line="RO-000002", variety="VAR-000002",
        delivery=date(2026, 8, 14),
    )
    demands = (late, early)
    protocols = (
        protocol(public_id="PV-000001", variety="VAR-000001"),
        protocol(public_id="PV-000002", variety="VAR-000002"),
    )
    first = ProductionPlanningEngine().calculate(snapshot(demands, protocols))
    second = ProductionPlanningEngine().calculate(snapshot(demands, tuple(reversed(protocols))))
    assert [item.demand.order_line_public_id for item in first] == [
        item.demand.order_line_public_id for item in second
    ]
    assert first[0].demand.order_line_public_id == pid("RO-000002")


def test_timezone_e_decimal_sono_preservati_senza_float() -> None:
    candidate = ProductionPlanningEngine().calculate(snapshot())[0]
    assert candidate.sowing_at.tzinfo == CANARY
    assert isinstance(candidate.productive_quantity.value, Decimal)
    assert not isinstance(candidate.productive_quantity.value, float)


def test_engine_non_dipende_da_provider_database_o_google() -> None:
    source = (Path(__file__).parents[3] / "src/tpo_core/application/production_planning/engine.py").read_text()
    forbidden = ("psycopg", "sqlalchemy", "postgresql", "google", "connection", "cursor")
    assert all(name not in source.lower() for name in forbidden)
