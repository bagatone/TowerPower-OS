from dataclasses import FrozenInstanceError

import pytest

from src.tpo_core.application.identity import (
    IdentifierSequence,
    IdentifierSequenceConflictError,
    IdentifierSequenceNotFoundError,
    InvalidIdentifierSequenceError,
    PersistentIdAllocator,
)
from src.tpo_core.domain.identifiers import OrdineId, RunId


class FakeSequenceRepository:
    def __init__(self, sequences=(), *, force_conflict=False) -> None:
        self.sequences = {item.identifier_type: item for item in sequences}
        self.force_conflict = force_conflict
        self.compare_calls = 0

    def get_sequence(self, identifier_type):
        try:
            return self.sequences[identifier_type.__name__]
        except KeyError as exc:
            raise IdentifierSequenceNotFoundError(identifier_type.__name__) from exc

    def compare_and_set(
        self,
        *,
        identifier_type,
        expected_version,
        expected_next_value,
        new_next_value,
    ):
        self.compare_calls += 1
        if self.force_conflict:
            return False
        current = self.get_sequence(identifier_type)
        if current.version != expected_version or current.next_value != expected_next_value:
            return False
        self.sequences[identifier_type.__name__] = IdentifierSequence(
            current.identifier_type,
            current.prefix,
            new_next_value,
            current.version + 1,
        )
        return True


def sequence(identifier_type, next_value=1, version=0, prefix=None):
    return IdentifierSequence(
        identifier_type.__name__,
        prefix or identifier_type.prefix,
        next_value,
        version,
    )


def test_alloca_ordine_e_avanza_valore_e_versione() -> None:
    repository = FakeSequenceRepository((sequence(OrdineId),))
    allocation = PersistentIdAllocator(repository).allocate(OrdineId)
    assert allocation.identifier == OrdineId("ORD-000001")
    assert allocation.sequence_before == sequence(OrdineId)
    assert allocation.sequence_after == sequence(OrdineId, next_value=2, version=1)
    assert repository.sequences["OrdineId"] == allocation.sequence_after


def test_alloca_run() -> None:
    repository = FakeSequenceRepository((sequence(RunId),))
    assert PersistentIdAllocator(repository).next_id(RunId) == RunId("RUN-000001")


def test_sequenze_separate_per_tipo() -> None:
    repository = FakeSequenceRepository((sequence(OrdineId), sequence(RunId)))
    allocator = PersistentIdAllocator(repository)
    assert allocator.next_id(OrdineId) == OrdineId("ORD-000001")
    assert allocator.next_id(RunId) == RunId("RUN-000001")
    assert repository.sequences["OrdineId"].next_value == 2
    assert repository.sequences["RunId"].next_value == 2


def test_allocazioni_successive_non_riusano_id() -> None:
    repository = FakeSequenceRepository((sequence(OrdineId),))
    allocator = PersistentIdAllocator(repository)
    assert allocator.next_id(OrdineId) == OrdineId("ORD-000001")
    assert allocator.next_id(OrdineId) == OrdineId("ORD-000002")


def test_id_resta_consumato_se_il_chiamante_fallisce() -> None:
    repository = FakeSequenceRepository((sequence(OrdineId),))
    allocator = PersistentIdAllocator(repository)
    allocator.allocate(OrdineId)
    assert allocator.next_id(OrdineId) == OrdineId("ORD-000002")


def test_sequenza_mancante_propaga_errore_specifico() -> None:
    with pytest.raises(IdentifierSequenceNotFoundError):
        PersistentIdAllocator(FakeSequenceRepository()).allocate(OrdineId)


@pytest.mark.parametrize(
    "changes",
    [
        {"identifier_type": ""},
        {"prefix": ""},
        {"next_value": 0},
        {"next_value": True},
        {"version": -1},
        {"version": True},
    ],
)
def test_sequenza_non_valida_rifiutata(changes) -> None:
    values = {"identifier_type": "OrdineId", "prefix": "ORD", "next_value": 1, "version": 0}
    values.update(changes)
    with pytest.raises(InvalidIdentifierSequenceError):
        IdentifierSequence(**values)


@pytest.mark.parametrize(
    "bad_sequence",
    [
        IdentifierSequence("RunId", "ORD", 1, 0),
        IdentifierSequence("OrdineId", "RUN", 1, 0),
    ],
)
def test_tipo_e_prefix_incoerenti_rifiutati(bad_sequence) -> None:
    repository = FakeSequenceRepository((bad_sequence,))
    repository.sequences["OrdineId"] = bad_sequence
    with pytest.raises(InvalidIdentifierSequenceError):
        PersistentIdAllocator(repository).allocate(OrdineId)


def test_compare_and_set_fallito_non_esegue_retry() -> None:
    repository = FakeSequenceRepository((sequence(OrdineId),), force_conflict=True)
    with pytest.raises(IdentifierSequenceConflictError):
        PersistentIdAllocator(repository).allocate(OrdineId)
    assert repository.compare_calls == 1
    assert repository.sequences["OrdineId"] == sequence(OrdineId)


def test_modello_sequenza_immutabile() -> None:
    value = sequence(OrdineId)
    with pytest.raises(FrozenInstanceError):
        value.next_value = 2


def test_servizio_non_usa_uuid_timestamp_clock_o_contatore_globale() -> None:
    import src.tpo_core.application.identity.service as module

    names = set(module.__dict__)
    assert not names.intersection({"uuid", "UUID", "datetime", "date", "time", "random"})
    assert not hasattr(module, "counter")
