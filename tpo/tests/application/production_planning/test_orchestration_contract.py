from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from src.tpo_core.application.production_planning.assembler import ProductionPlanningCommitAssembler
from src.tpo_core.application.production_planning.errors import ProductionPlanningError
from src.tpo_core.application.production_planning.models import (
    ProductionPlanningIdentityBundle,
    ProductionPlanningLoadedInput,
    PublicId,
)
from tests.application.production_planning.test_assembler import assembly_input


def _bundle(plan):
    prefixes = {
        "PLAN": "PP", "REVISION": "RVP", "PLANNING_LINE": "RPS",
        "ALLOCATION": "ALL", "REPLACEMENT_ALLOCATION": "ALL",
    }
    counters = {key: 0 for key in prefixes}
    assignments = []
    for slot in plan.identity_slots:
        counters[slot.slot_kind] += 1
        assignments.append(
            (slot, PublicId(f"{prefixes[slot.slot_kind]}-{counters[slot.slot_kind]:06d}"))
        )
    return ProductionPlanningIdentityBundle.from_slot_assignments(tuple(assignments))


def test_plan_e_deterministico_id_free_e_materialization_e_pura(monkeypatch) -> None:
    assembler = ProductionPlanningCommitAssembler()
    source = replace(assembly_input(allocation_count=1), identities=None)
    first = assembler.plan(source)
    second = assembler.plan(source)
    assert first == second
    assert tuple(slot.ordering_key for slot in first.identity_slots) == tuple(
        sorted(slot.ordering_key for slot in first.identity_slots)
    )
    bundle = _bundle(first)
    monkeypatch.setattr(
        "src.tpo_core.application.production_planning.assembler._production_quantity",
        lambda *_args: (_ for _ in ()).throw(AssertionError("business recalculated")),
    )
    assert assembler.materialize(first, bundle) == assembler.materialize(first, bundle)
    with pytest.raises(FrozenInstanceError):
        first.identity_slots = ()  # type: ignore[misc]


def test_materialize_rifiuta_slot_mancanti_extra_ordine_e_id_duplicati() -> None:
    assembler = ProductionPlanningCommitAssembler()
    plan = assembler.plan(replace(assembly_input(allocation_count=1), identities=None))
    bundle = _bundle(plan)
    with pytest.raises(ProductionPlanningError, match="slot canonici"):
        assembler.materialize(plan, ProductionPlanningIdentityBundle.from_slot_assignments(bundle.slot_assignments[:-1]))
    with pytest.raises(Exception):
        ProductionPlanningIdentityBundle.from_slot_assignments(tuple(reversed(bundle.slot_assignments)))
    slot = plan.identity_slots[0]
    with pytest.raises(Exception):
        ProductionPlanningIdentityBundle.from_slot_assignments(((slot, PublicId("PP-000001")),))
    if len(plan.identity_slots) > 1:
        with pytest.raises(Exception):
            ProductionPlanningIdentityBundle.from_slot_assignments(
                ((plan.identity_slots[0], PublicId("ALL-000001")),
                 (plan.identity_slots[1], PublicId("ALL-000001")))
            )


def test_assemble_wrapper_equivale_a_plan_materialize() -> None:
    assembler = ProductionPlanningCommitAssembler()
    value = assembly_input(allocation_count=1)
    plan = assembler.plan(replace(value, identities=None))
    assignments = []
    by_kind = {
        "PLAN": value.identities.plan_public_ids,
        "REVISION": value.identities.revision_public_ids,
        "PLANNING_LINE": value.identities.planning_line_public_ids,
        "ALLOCATION": value.identities.allocation_public_ids,
    }
    used = {kind: 0 for kind in by_kind}
    for slot in plan.identity_slots:
        assignments.append((slot, by_kind[slot.slot_kind][used[slot.slot_kind]]))
        used[slot.slot_kind] += 1
    assert assembler.assemble(value) == assembler.materialize(
        plan, ProductionPlanningIdentityBundle.from_slot_assignments(tuple(assignments))
    )


def test_loaded_input_e_immutabile_e_disposition_ordinate() -> None:
    loaded = ProductionPlanningLoadedInput(assembly_input().snapshot, ())
    assert loaded.allocation_disposition_decisions == ()
    with pytest.raises(FrozenInstanceError):
        loaded.snapshot = assembly_input().snapshot  # type: ignore[misc]
