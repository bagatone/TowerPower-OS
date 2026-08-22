from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from src.tpo_core.application.production_planning.errors import (
    InvalidProductionPlanningModelError,
)
from src.tpo_core.application.production_planning.models import (
    ActiveAllocationSnapshot,
    AllocationDispositionDecision,
    AllocationReplacementSpecification,
    PublicId,
    canonical_frame,
    disposition_set_key_v1,
    planning_line_slot_key_v1,
    replacement_allocation_slot_key_v1,
)
from src.tpo_core.application.production_planning.assembler import (
    ProductionPlanningCommitAssembler,
)
from src.tpo_core.application.production_planning.engine import ProductionPlanningEngine
from tests.application.production_planning.test_application_layer import qty
from tests.application.production_planning.test_assembler import (
    assembly_input, replanning_value,
)


def pid(value: str) -> PublicId:
    return PublicId(value)


def replacement(*, previous="RVP-000001", parent="ALL-000001",
                source="STK-000001", destination="RO-000001",
                allocation_type="STOCK") -> AllocationReplacementSpecification:
    line_key = planning_line_slot_key_v1(pid(previous), pid(destination))
    return AllocationReplacementSpecification(
        replacement_allocation_slot_key_v1(
            pid(parent), allocation_type, pid(source), pid(destination), line_key,
        ),
        allocation_type, pid(source), pid(destination), line_key, qty("1"),
        "authorized replacement",
    )


def decision(**changes) -> AllocationDispositionDecision:
    values = dict(
        allocation_public_id=pid("ALL-000001"), expected_version=3,
        disposition_cause="REALLOCATION_REQUIRED",
        source_usability="TRANSFERABLE_ONLY",
        observed_remaining_quantity=Decimal("1"),
        consumed_quantity_delta=Decimal("0"), target_disposition="SOSTITUITA",
        replacement_specification=replacement(), reason="reallocation",
        provenance="authorized decision",
    )
    values.update(changes)
    return AllocationDispositionDecision(**values)


def set_key(decisions):
    return disposition_set_key_v1(
        previous_plan_revision_public_id=pid("RVP-000001"),
        order_line_public_id=pid("RO-000001"),
        replanning_reason_code="MANUAL_REPLAN_AUTHORIZED",
        correlation_id="corr-001", decisions=decisions,
    )


def test_slot_keys_are_deterministic_business_keys_without_future_public_ids() -> None:
    first = replacement()
    second = replacement()
    assert first == second
    assert "ALL-000002" not in first.replacement_allocation_slot_key
    assert "RPS-" not in first.destination_planning_line_slot_key


@pytest.mark.parametrize(
    "changed",
    [
        replacement(destination="RO-000002"),
        replacement(parent="ALL-000002"),
        replacement(source="SEM-000001", allocation_type="PRODUZIONE_IN_CORSO"),
        replacement(allocation_type="RACCOLTA", source="RAC-000001"),
    ],
)
def test_replacement_semantic_change_changes_slot_key(changed) -> None:
    assert changed.replacement_allocation_slot_key != replacement().replacement_allocation_slot_key


def test_multibyte_framing_uses_utf8_byte_length() -> None:
    assert canonical_frame("RÁBANO") == "7:RÁBANO"


@pytest.mark.parametrize("malformed", ["", "3:BAD", "01:A", "2:Á"])
def test_malformed_destination_slot_key_is_rejected(malformed) -> None:
    with pytest.raises(InvalidProductionPlanningModelError):
        replace(replacement(), destination_planning_line_slot_key=malformed)


def test_slot_key_mismatch_is_rejected_field_by_field() -> None:
    valid = replacement()
    with pytest.raises(InvalidProductionPlanningModelError):
        AllocationDispositionDecision(
            pid("ALL-000002"), 3, "REALLOCATION_REQUIRED", "TRANSFERABLE_ONLY",
            Decimal("1"), Decimal("0"), "SOSTITUITA", valid,
            "reallocation", "authorized decision",
        )


def test_decision_set_key_is_deterministic_and_payload_sensitive() -> None:
    original = decision()
    assert set_key((original,)) == set_key((original,))
    changed = decision(reason="different authorized reason")
    assert set_key((original,)) != set_key((changed,))


def test_decision_set_requires_canonical_allocation_order_and_rejects_duplicates() -> None:
    first = decision()
    second_replacement = replacement(parent="ALL-000002")
    second = decision(
        allocation_public_id=pid("ALL-000002"),
        replacement_specification=second_replacement,
    )
    with pytest.raises(InvalidProductionPlanningModelError):
        set_key((second, first))
    with pytest.raises(InvalidProductionPlanningModelError):
        set_key((first, first))


def test_replacement_slot_change_changes_decision_set_key() -> None:
    original = decision()
    changed_replacement = replacement(source="SEM-000001",
                                      allocation_type="PRODUZIONE_IN_CORSO")
    changed = decision(replacement_specification=changed_replacement)
    assert set_key((original,)) != set_key((changed,))


def test_disposition_change_alters_snapshot_hash_and_replanning_key() -> None:
    base = replanning_value(assembly_input(allocation_count=1))
    observed = ActiveAllocationSnapshot(
        pid("ALL-000001"), "STOCK", pid("STK-000001"), pid("RO-000001"),
        qty("1"), qty("0"), qty("0"), qty("0"), qty("0"), qty("1"),
        "ATTIVA", 0,
    )
    snapshot = replace(base.snapshot, allocations=(observed,))
    release = AllocationDispositionDecision(
        observed.allocation_public_id, 0, "DEMAND_REDUCED", "REUSABLE",
        Decimal("1"), Decimal("0"), "RILASCIATA", None,
        "first authorized reason", "authorized decision",
    )
    first_input = replace(
        base, snapshot=snapshot,
        candidates=tuple(ProductionPlanningEngine().calculate(snapshot)),
        allocation_dispositions=(release,), identities=None,
    )
    second_input = replace(
        first_input,
        allocation_dispositions=(replace(release, reason="second authorized reason"),),
    )
    first = ProductionPlanningCommitAssembler().plan(first_input).revisions[0]
    second = ProductionPlanningCommitAssembler().plan(second_input).revisions[0]
    assert first.canonical_replanning_snapshot.decision_set_key != second.canonical_replanning_snapshot.decision_set_key
    assert first.canonical_replanning_snapshot.canonical_snapshot_hash != second.canonical_replanning_snapshot.canonical_snapshot_hash
    assert first.canonical_replanning_snapshot.replanning_key_v1 != second.canonical_replanning_snapshot.replanning_key_v1
