from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from src.tpo_core.domain.errors import (
    InvalidQuantityError,
    InvalidUnitOfMeasureError,
    InvariantViolationError,
)
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure


@pytest.mark.parametrize("value", ["1.25", 2, Decimal("3.50")])
def test_quantity_parses_supported_values(value) -> None:
    quantity = Quantity(value, UnitOfMeasure.SET)
    assert quantity.value == Decimal(str(value))


@pytest.mark.parametrize("value", [1.2, float("nan"), float("inf")])
def test_quantity_rejects_float(value) -> None:
    with pytest.raises(InvalidQuantityError):
        Quantity(value, UnitOfMeasure.SET)


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), "NaN", "Infinity"])
def test_quantity_rejects_non_finite_decimal(value) -> None:
    with pytest.raises(InvalidQuantityError):
        Quantity(value, UnitOfMeasure.GRAM)


@pytest.mark.parametrize("value", ["not-a-number", "", None, -1, "-0.1"])
def test_quantity_rejects_invalid_or_negative_values(value) -> None:
    with pytest.raises(InvalidQuantityError):
        Quantity(value, UnitOfMeasure.UNIT)


def test_unit_is_required_and_official() -> None:
    with pytest.raises(InvalidUnitOfMeasureError):
        Quantity("1", None)
    with pytest.raises(InvalidUnitOfMeasureError):
        Quantity("1", "SET")


def test_compatible_quantities_can_be_added_and_subtracted() -> None:
    left = Quantity("2.5", UnitOfMeasure.SET)
    right = Quantity("1.25", UnitOfMeasure.SET)
    assert left + right == Quantity("3.75", UnitOfMeasure.SET)
    assert left - right == Quantity("1.25", UnitOfMeasure.SET)


def test_addition_with_non_quantity_returns_type_error() -> None:
    with pytest.raises(TypeError):
        Quantity(1, UnitOfMeasure.SET) + 2


def test_subtraction_with_non_quantity_returns_type_error() -> None:
    with pytest.raises(TypeError):
        Quantity(1, UnitOfMeasure.SET) - 2


def test_incompatible_units_are_rejected() -> None:
    with pytest.raises(InvalidUnitOfMeasureError):
        Quantity(1, UnitOfMeasure.SET) + Quantity(1, UnitOfMeasure.UNIT)


def test_negative_subtraction_result_is_rejected() -> None:
    with pytest.raises(InvariantViolationError):
        Quantity(1, UnitOfMeasure.GRAM) - Quantity(2, UnitOfMeasure.GRAM)


def test_quantity_is_immutable() -> None:
    quantity = Quantity(1, UnitOfMeasure.UNIT)
    with pytest.raises(FrozenInstanceError):
        quantity.value = Decimal("2")


def test_units_have_stable_representations() -> None:
    assert {unit.value for unit in UnitOfMeasure} == {"SET", "GRAM", "UNIT"}
