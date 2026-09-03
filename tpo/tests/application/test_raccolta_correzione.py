from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.raccolta.errors import (
    InvalidRaccoltaCommandError, InvalidRaccoltaEffectiveAtError,
    InvalidRaccoltaQuantityError,
)
from src.tpo_core.application.raccolta.models import CorreggiRaccolta, RaccoltaAuthority
from src.tpo_core.application.raccolta.service import RaccoltaService
from src.tpo_core.domain.identifiers import ActorId, RaccoltaId, SeminaId
from src.tpo_core.domain.quantities import UnitOfMeasure


AUTH = RaccoltaAuthority(ActorId("owner"), "physical correction", "corr", "idem")


def command(**changes):
    values = dict(
        original_raccolta_id=RaccoltaId("RAC-000001"),
        semina_id=SeminaId("SEM-000001"),
        quantity=Decimal("-0.25"),
        unit=UnitOfMeasure.SET,
        effective_at=datetime(2026, 9, 3, 8, tzinfo=timezone.utc),
        authority=AUTH,
    )
    values.update(changes)
    return CorreggiRaccolta(**values)


def test_negative_correction_and_canonical_payload_are_valid():
    value = command()
    assert value.quantity == Decimal("-0.25")
    assert len(value.canonical_payload_hash) == 64
    assert value.effective_at.tzinfo is timezone.utc


def test_positive_correction_is_valid():
    value = command(quantity=Decimal("0.25"))
    assert value.quantity == Decimal("0.25")


@pytest.mark.parametrize("value", ["0", "0.0000001", "-0.0000001"])
def test_zero_or_overprecision_correction_quantity_is_rejected(value):
    with pytest.raises(InvalidRaccoltaQuantityError):
        command(quantity=Decimal(value))


def test_wrong_uom_and_naive_time_are_rejected():
    with pytest.raises(InvalidRaccoltaQuantityError):
        command(unit=UnitOfMeasure.UNIT)
    with pytest.raises(InvalidRaccoltaEffectiveAtError):
        command(effective_at=datetime(2026, 9, 3, 8))


def test_invalid_original_and_semina_identifiers_are_rejected():
    with pytest.raises(InvalidRaccoltaCommandError):
        command(original_raccolta_id="RAC-000001")
    with pytest.raises(InvalidRaccoltaCommandError):
        command(semina_id="SEM-000001")


def test_distinct_correction_payloads_hash_differently():
    base = command()
    other_quantity = command(quantity=Decimal("-0.5"))
    other_original = command(original_raccolta_id=RaccoltaId("RAC-000002"))
    assert base.canonical_payload_hash != other_quantity.canonical_payload_hash
    assert base.canonical_payload_hash != other_original.canonical_payload_hash


def test_service_correct_is_thin_and_typed():
    class Writer:
        def record(self, value):
            raise AssertionError("record non deve essere invocato")

        def correct(self, value):
            assert value == command()
            return "ok"

    service = RaccoltaService(Writer())
    assert service.correct(command()) == "ok"
    with pytest.raises(InvalidRaccoltaCommandError):
        service.correct(object())
