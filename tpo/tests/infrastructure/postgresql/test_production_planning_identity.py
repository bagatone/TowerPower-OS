"""Contratto del bridge Identity PostgreSQL per Production Planning."""

from __future__ import annotations

import inspect

import pytest

from src.tpo_core.application.identity.errors import (
    IdentifierSequenceNotFoundError,
    InvalidIdentifierSequenceError,
)
from src.tpo_core.application.identity.models import IdentifierSequence
from src.tpo_core.application.identity.production_planning import (
    PRODUCTION_PLANNING_SEQUENCE_TYPES,
    production_planning_identifier_type,
)
from src.tpo_core.application.identity.service import PersistentIdAllocator
from src.tpo_core.application.production_planning.models import PublicId
from src.tpo_core.application.production_planning.ports import IdentityAllocationPort
from src.tpo_core.domain.identifiers import (
    AllocazioneId,
    PermanentId,
    PianoProduzioneId,
    RevisionePianoProduzioneId,
    RigaPianoSeminaId,
    RunPianificazioneProduzioneId,
)
from src.tpo_core.infrastructure.postgresql.production_planning_identity import (
    PostgreSQLProductionPlanningIdentityAdapter,
)


CASES = (
    ("RUN_PIANIFICAZIONE_PRODUZIONE_ID", RunPianificazioneProduzioneId, "RPP"),
    ("PIANO_PRODUZIONE_ID", PianoProduzioneId, "PP"),
    ("REVISIONE_PIANO_PRODUZIONE_ID", RevisionePianoProduzioneId, "RVP"),
    ("RIGA_PIANO_SEMINA_ID", RigaPianoSeminaId, "RPS"),
    ("ALLOCAZIONE_ID", AllocazioneId, "ALL"),
)


class MemorySequenceRepository:
    def __init__(self) -> None:
        self.sequences = {
            identifier_type.__name__: IdentifierSequence(
                identifier_type.__name__, prefix, 1, 0
            )
            for _, identifier_type, prefix in CASES
        }
        self.requested_types: list[type[PermanentId]] = []

    def get_sequence(self, identifier_type):
        self.requested_types.append(identifier_type)
        try:
            return self.sequences[identifier_type.__name__]
        except KeyError as exc:
            raise IdentifierSequenceNotFoundError(identifier_type.__name__) from exc

    def compare_and_set(
        self, *, identifier_type, expected_version, expected_next_value,
        new_next_value,
    ):
        current = self.sequences[identifier_type.__name__]
        assert (current.version, current.next_value) == (
            expected_version, expected_next_value,
        )
        self.sequences[identifier_type.__name__] = IdentifierSequence(
            current.identifier_type, current.prefix, new_next_value,
            current.version + 1,
        )
        return True


@pytest.mark.parametrize("sequence_name,identifier_type,prefix", CASES)
def test_frozen_sequence_maps_to_typed_identifier(sequence_name, identifier_type, prefix) -> None:
    assert production_planning_identifier_type(sequence_name) is identifier_type
    assert PRODUCTION_PLANNING_SEQUENCE_TYPES[sequence_name] is identifier_type
    assert identifier_type.sequence_name == sequence_name
    assert identifier_type.prefix == prefix
    assert identifier_type(f"{prefix}-000001").value == f"{prefix}-000001"


@pytest.mark.parametrize("unknown", ["", "ORDINE_ID", "PIANO_PRODUZIONE", None])
def test_unknown_sequence_fails_closed(unknown) -> None:
    with pytest.raises(InvalidIdentifierSequenceError):
        production_planning_identifier_type(unknown)


def test_adapter_satisfies_planning_port_and_delegates_to_existing_allocator() -> None:
    repository = MemorySequenceRepository()
    allocator = PersistentIdAllocator(repository)
    adapter: IdentityAllocationPort = PostgreSQLProductionPlanningIdentityAdapter(
        allocator
    )

    result = adapter.allocate("PIANO_PRODUZIONE_ID")

    assert result == PublicId("PP-000001")
    assert repository.requested_types == [PianoProduzioneId]
    assert repository.sequences["PianoProduzioneId"] == IdentifierSequence(
        "PianoProduzioneId", "PP", 2, 1
    )


def test_repeated_allocation_uses_existing_monotonic_cas_stack() -> None:
    repository = MemorySequenceRepository()
    adapter = PostgreSQLProductionPlanningIdentityAdapter(
        PersistentIdAllocator(repository)
    )

    first = adapter.allocate("ALLOCAZIONE_ID")
    second = adapter.allocate("ALLOCAZIONE_ID")

    assert (first, second) == (PublicId("ALL-000001"), PublicId("ALL-000002"))
    assert repository.requested_types == [AllocazioneId, AllocazioneId]


def test_adapter_contains_no_uuid_or_random_generation() -> None:
    source = inspect.getsource(PostgreSQLProductionPlanningIdentityAdapter)
    assert "uuid" not in source.lower()
    assert "random" not in source.lower()
    assert ".allocate(identifier_type)" in source
