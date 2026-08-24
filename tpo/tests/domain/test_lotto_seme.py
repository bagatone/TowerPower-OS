from datetime import date
from decimal import Decimal

import pytest

from src.tpo_core.domain.entities.lotto_seme import LottoSeme
from src.tpo_core.domain.errors import (
    InvalidIdentifierError,
    InvalidQuantityError,
    InvariantViolationError,
)
from src.tpo_core.domain.identifiers import LottoSemeId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure


def lot(**changes):
    values = dict(
        id=LottoSemeId("LSE-000001"), seed_supplier="Supplier",
        seed_commercial_reference="REF-1", manufacturer_lot_number="LOT-1",
        received_date=date(2026, 8, 24), expiry_date=None,
        initial_quantity=Quantity(Decimal("10.123456"), UnitOfMeasure.GRAM),
        remaining_quantity=Quantity(Decimal("4.123456"), UnitOfMeasure.GRAM),
    )
    values.update(changes)
    return LottoSeme(**values)


def test_lotto_seme_identity_and_exact_derived_consumption():
    item = lot()
    assert item.id.value == "LSE-000001"
    assert item.consumed_quantity == Quantity(Decimal("6.000000"), UnitOfMeasure.GRAM)


@pytest.mark.parametrize("value", ["LSE-000000", "LSE-1", "SEM-000001"])
def test_lotto_seme_id_rejects_invalid_values(value):
    with pytest.raises(InvalidIdentifierError):
        LottoSemeId(value)


@pytest.mark.parametrize("field", ["seed_supplier", "seed_commercial_reference", "manufacturer_lot_number"])
def test_lotto_seme_requires_constitutive_text(field):
    with pytest.raises(InvariantViolationError):
        lot(**{field: ""})


def test_lotto_seme_requires_gram_and_valid_balances():
    with pytest.raises(InvalidQuantityError):
        lot(initial_quantity=Quantity(Decimal("1"), UnitOfMeasure.SET))
    with pytest.raises(InvalidQuantityError):
        lot(remaining_quantity=Quantity(Decimal("11"), UnitOfMeasure.GRAM))
    with pytest.raises(InvalidQuantityError):
        lot(remaining_quantity=Quantity(Decimal("-1"), UnitOfMeasure.GRAM))


def test_lotto_seme_is_frozen_and_dates_are_authoritative():
    item = lot()
    with pytest.raises(AttributeError):
        item.manufacturer_lot_number = "OTHER"
    with pytest.raises(InvariantViolationError):
        lot(expiry_date=date(2026, 8, 23))
