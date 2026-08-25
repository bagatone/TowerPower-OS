from datetime import datetime, timezone
from decimal import Decimal
import pytest

from src.tpo_core.application.semina_commissioning import (
    CommissionSemina, PlannedSeminaStart, SeminaCommissioningAuthority,
    SeminaCommissioningService, SeminaFactSource, SeminaOrigin,
)
from src.tpo_core.application.semina_commissioning.errors import (
    InvalidPhysicalStartError, InvalidSeminaCommandError, InvalidSeminaOriginError,
)
from src.tpo_core.domain.identifiers import (
    ActorId, LottoSemeId, ProtocolloVersioneId, RigaPianoSeminaId, SeminaId,
)
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure


def _command(origin=SeminaOrigin.ORDINE_CLIENTE, planning=None):
    facts = {
        "physical_started_at", "actual_seed_grams", "selected_lse", "selected_pv", "origin",
    }
    if planning: facts.add("planned_started_quantity")
    return CommissionSemina(
        LottoSemeId("LSE-000001"), 0, ProtocolloVersioneId("PV-000001"),
        Quantity(Decimal("1.250000"), UnitOfMeasure.GRAM),
        datetime(2026, 8, 25, 8, tzinfo=timezone.utc), origin, planning,
        tuple((key, SeminaFactSource.OWNER_AUTHORIZED) for key in facts),
        SeminaCommissioningAuthority(ActorId("tpo.owner"), "Physical start",
                                     "corr-1", "idem-1"),
    )


def test_identity_metadata_and_closed_origin_vocabulary():
    assert SeminaId.sequence_name == "SEMINA_ID"
    assert {item.value for item in SeminaOrigin} == {
        "PIANO_PRODUZIONE", "ORDINE_CLIENTE", "RIPRISTINO_STOCK",
    }
    with pytest.raises(ValueError): SeminaOrigin("TEST")


def test_independent_command_is_immutable_and_canonical():
    command = _command()
    assert command.planning_start is None
    assert len(command.canonical_payload_hash) == 64
    with pytest.raises(Exception): command.origin = SeminaOrigin.RIPRISTINO_STOCK


def test_planned_command_requires_complete_planning_and_provenance():
    planned = PlannedSeminaStart(
        RigaPianoSeminaId("RPS-000001"), 2,
        Quantity(Decimal("0.5"), UnitOfMeasure.SET),
    )
    assert _command(SeminaOrigin.PIANO_PRODUZIONE, planned).planning_start == planned
    with pytest.raises(InvalidSeminaOriginError):
        _command(SeminaOrigin.PIANO_PRODUZIONE)
    with pytest.raises(InvalidSeminaOriginError):
        _command(SeminaOrigin.ORDINE_CLIENTE, planned)


def test_naive_timestamp_and_wrong_quantity_are_rejected():
    values = _command().__dict__
    with pytest.raises(InvalidPhysicalStartError):
        CommissionSemina(**{**values, "physical_started_at": datetime(2026, 8, 25, 8)})
    with pytest.raises(InvalidSeminaCommandError):
        CommissionSemina(**{**values, "actual_seed_quantity": Quantity(Decimal("1"), UnitOfMeasure.SET)})


def test_service_delegates_to_writer():
    class Writer:
        def commission(self, command): return command.canonical_payload_hash
    command = _command()
    assert SeminaCommissioningService(Writer()).commission(command) == command.canonical_payload_hash
