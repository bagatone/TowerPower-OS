from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.delivery_fulfilment import (
    DeliveryFulfilmentCommand,
    DeliveryFulfilmentLine,
    DeliveryLineReference,
    InvalidDeliveryCommandError,
)
from src.tpo_core.domain.identifiers import (
    ActorId, ClienteId, ConsegnaId, MovimentoId, OrdineId,
)
from src.tpo_core.domain.quantities import UnitOfMeasure


NOW = datetime(2026, 8, 13, 10, tzinfo=ZoneInfo("Atlantic/Canary"))


def ordinary_line() -> DeliveryFulfilmentLine:
    return DeliveryFulfilmentLine(
        OrdineId("ORD-900001"), "RO-900001", Decimal("0.5"),
        UnitOfMeasure.SET, 0, 0, MovimentoId("MOV-900001"),
    )


def test_ordinary_and_correction_contracts_are_explicit() -> None:
    ordinary = ordinary_line()
    correction = DeliveryFulfilmentLine(
        OrdineId("ORD-900001"), "RO-900001", Decimal("-0.25"),
        UnitOfMeasure.SET, 1, 1,
        correction_of=DeliveryLineReference(ConsegnaId("CON-900001"), 1),
    )
    assert not ordinary.is_correction
    assert correction.is_correction
    command = DeliveryFulfilmentCommand(
        ConsegnaId("CON-900002"), ClienteId("CLI-900001"), date(2026, 8, 13),
        NOW, (correction,), ActorId("test-actor"), "commercial correction", "corr-1",
    )
    assert command.is_correction


@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("0.0000001")])
def test_zero_or_excess_precision_is_rejected(quantity: Decimal) -> None:
    with pytest.raises(InvalidDeliveryCommandError):
        DeliveryFulfilmentLine(
            OrdineId("ORD-900001"), "RO-900001", quantity,
            UnitOfMeasure.SET, 0, 0, MovimentoId("MOV-900001"),
        )


def test_ordinary_requires_movement_and_correction_forbids_it() -> None:
    with pytest.raises(InvalidDeliveryCommandError):
        DeliveryFulfilmentLine(
            OrdineId("ORD-900001"), "RO-900001", Decimal("0.5"),
            UnitOfMeasure.SET, 0, 0,
        )
    with pytest.raises(InvalidDeliveryCommandError):
        DeliveryFulfilmentLine(
            OrdineId("ORD-900001"), "RO-900001", Decimal("-0.5"),
            UnitOfMeasure.SET, 0, 0, MovimentoId("MOV-900001"),
            DeliveryLineReference(ConsegnaId("CON-900001"), 1),
        )


def test_command_rejects_mixed_ordinary_and_correction() -> None:
    correction = DeliveryFulfilmentLine(
        OrdineId("ORD-900002"), "RO-900002", Decimal("-0.25"),
        UnitOfMeasure.SET, 0, 0,
        correction_of=DeliveryLineReference(ConsegnaId("CON-900001"), 1),
    )
    command = DeliveryFulfilmentCommand(
        ConsegnaId("CON-900003"), ClienteId("CLI-900001"), date(2026, 8, 13),
        NOW, (ordinary_line(), correction), ActorId("test-actor"), "mixed", "corr-2",
    )
    with pytest.raises(InvalidDeliveryCommandError):
        _ = command.is_correction
