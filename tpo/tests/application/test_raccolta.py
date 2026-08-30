from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.raccolta.errors import (
    InvalidRaccoltaCommandError, InvalidRaccoltaEffectiveAtError,
    InvalidRaccoltaQuantityError,
)
from src.tpo_core.application.raccolta.models import RaccoltaAuthority, RecordRaccolta
from src.tpo_core.application.raccolta.service import RaccoltaService
from src.tpo_core.domain.identifiers import ActorId, SeminaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure


AUTH = RaccoltaAuthority(ActorId("owner"), "physical harvest", "corr", "idem")


def command(**changes):
    values = dict(
        semina_id=SeminaId("SEM-000001"),
        quantity=Quantity(Decimal("0.5"), UnitOfMeasure.SET),
        effective_at=datetime(2026, 8, 30, 8, tzinfo=timezone.utc),
        authority=AUTH,
    )
    values.update(changes)
    return RecordRaccolta(**values)


def test_fractional_set_and_canonical_payload_are_valid():
    value = command()
    assert value.quantity.value == Decimal("0.5")
    assert len(value.canonical_payload_hash) == 64
    assert value.effective_at.tzinfo is timezone.utc


@pytest.mark.parametrize("value", ["0", "0.0000001"])
def test_nonpositive_or_overprecision_quantity_is_rejected(value):
    with pytest.raises(InvalidRaccoltaQuantityError):
        command(quantity=Quantity(Decimal(value), UnitOfMeasure.SET))


def test_wrong_uom_and_naive_time_are_rejected():
    with pytest.raises(InvalidRaccoltaQuantityError):
        command(quantity=Quantity(Decimal("1"), UnitOfMeasure.UNIT))
    with pytest.raises(InvalidRaccoltaEffectiveAtError):
        command(effective_at=datetime(2026, 8, 30, 8))


def test_service_is_thin_and_typed():
    class Writer:
        def record(self, value):
            assert value == command()
            return "ok"
    service = RaccoltaService(Writer())
    assert service.record(command()) == "ok"
    with pytest.raises(InvalidRaccoltaCommandError):
        service.record(object())
