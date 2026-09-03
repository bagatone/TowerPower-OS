from dataclasses import FrozenInstanceError
from inspect import Parameter, signature

import pytest

from src.tpo_core.domain.errors import InvalidIdentifierError
from src.tpo_core.domain.identifiers import (
    ActorId,
    ClienteId,
    ConsegnaId,
    IdGenerator,
    MovimentoId,
    NumeroFattura,
    OrdineId,
    PermanentId,
    ProgrammaFornituraId,
    RaccoltaId,
    RunId,
    SeminaId,
    VarietaId,
)


def test_actor_id_valido_stabile_e_immutabile() -> None:
    actor = ActorId("actor-test")
    assert actor.value == "actor-test"
    assert str(actor) == "actor-test"
    assert signature(ActorId).parameters["value"].default is Parameter.empty
    with pytest.raises(FrozenInstanceError):
        actor.value = "altro"


@pytest.mark.parametrize("value", ["", "   ", " actor", "actor ", None, 1])
def test_actor_id_rifiuta_valori_invalidi(value) -> None:
    with pytest.raises(InvalidIdentifierError):
        ActorId(value)


VALID_IDS = [
    (VarietaId, "VAR-000001"),
    (SeminaId, "SEM-000001"),
    (RaccoltaId, "RAC-000001"),
    (MovimentoId, "MOV-000001"),
    (ProgrammaFornituraId, "PF-000001"),
    (OrdineId, "ORD-000001"),
    (ConsegnaId, "CON-000001"),
    (RunId, "RUN-000001"),
    (ClienteId, "CLI-000001"),
]


@pytest.mark.parametrize(("identifier_type", "value"), VALID_IDS)
def test_valid_identifiers(identifier_type, value) -> None:
    identifier = identifier_type(value)
    assert identifier.value == value
    assert str(identifier) == value


@pytest.mark.parametrize("value", ["", "VAR-000000", "VAR-00001", "VAR--000001", "VAR-ABCDEF"])
def test_invalid_numeric_part_or_empty_value(value) -> None:
    with pytest.raises(InvalidIdentifierError):
        VarietaId(value)


def test_permanent_id_cannot_be_instantiated_directly() -> None:
    with pytest.raises(InvalidIdentifierError):
        PermanentId("VAR-000001")


def test_wrong_prefix_is_rejected() -> None:
    with pytest.raises(InvalidIdentifierError):
        VarietaId("SEM-000001")


def test_no_ambiguous_normalization_is_applied() -> None:
    with pytest.raises(InvalidIdentifierError):
        VarietaId(" var-000001 ")


def test_identifier_types_are_not_interchangeable() -> None:
    assert VarietaId("VAR-000001") != SeminaId("SEM-000001")
    with pytest.raises(InvalidIdentifierError):
        SeminaId("VAR-000001")


def test_identifiers_compare_by_type_and_value() -> None:
    assert OrdineId("ORD-000001") == OrdineId("ORD-000001")
    assert OrdineId("ORD-000001") != OrdineId("ORD-000002")


def test_identifier_is_immutable() -> None:
    identifier = RunId("RUN-000001")
    with pytest.raises(FrozenInstanceError):
        identifier.value = "RUN-000002"


class DeterministicIdGenerator:
    def __init__(self) -> None:
        self._next_by_type: dict[type[PermanentId], int] = {}

    def next_id(self, identifier_type):
        number = self._next_by_type.get(identifier_type, 0) + 1
        self._next_by_type[identifier_type] = number
        return identifier_type(f"{identifier_type.prefix}-{number:06d}")


def next_two(generator: IdGenerator, identifier_type):
    return generator.next_id(identifier_type), generator.next_id(identifier_type)


def test_fake_id_generator_is_deterministic_and_typed() -> None:
    generator = DeterministicIdGenerator()
    first, second = next_two(generator, OrdineId)
    assert first == OrdineId("ORD-000001")
    assert second == OrdineId("ORD-000002")
    assert generator.next_id(SeminaId) == SeminaId("SEM-000001")


def test_numero_fattura_valido_stabile_e_immutabile() -> None:
    numero = NumeroFattura("2026/0001")
    assert numero.value == "2026/0001"
    assert str(numero) == "2026/0001"
    assert numero.anno == 2026
    with pytest.raises(FrozenInstanceError):
        numero.value = "2026/0002"


@pytest.mark.parametrize("value", [
    "", "   ", None, 1, "2026-0001", "26/0001", "2026/001", "2026/00001",
    "2026/0000", " 2026/0001", "2026/0001 ",
])
def test_numero_fattura_rifiuta_formati_invalidi(value) -> None:
    with pytest.raises(InvalidIdentifierError):
        NumeroFattura(value)


def test_numero_fattura_non_e_un_permanent_id() -> None:
    assert not isinstance(NumeroFattura("2026/0001"), PermanentId)


def test_numero_fattura_compare_per_valore() -> None:
    assert NumeroFattura("2026/0001") == NumeroFattura("2026/0001")
    assert NumeroFattura("2026/0001") != NumeroFattura("2026/0002")
