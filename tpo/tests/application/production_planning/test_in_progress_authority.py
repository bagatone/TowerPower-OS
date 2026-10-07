from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from src.tpo_core.application.production_planning.in_progress_authority import (
    derive_in_progress_authority, in_progress_compatible_with_delivery, in_progress_eligible_quantity,
)

TZ = timezone(timedelta(hours=1))
START = datetime(2026, 10, 6, 9, tzinfo=TZ)


def derive(**kw):
    args = dict(declared_sets=1, expected_yield=Decimal("1"), yield_uom="SET", started_at=START,
                germination_days=3, light_days=10, buffer_minutes=0)
    args.update(kw)
    return derive_in_progress_authority(**args)


def test_one_set_is_one_set_whatever_the_seed_grams():
    result = derive(declared_sets=1)
    assert result.quantity == Decimal("1") and result.uom == "SET"
    assert derive(declared_sets=7).quantity == Decimal("7")


def test_window_starts_after_protocol_phases_and_lasts_five_days():
    result = derive(buffer_minutes=30)
    assert result.window_start == START + timedelta(days=13, minutes=30)
    assert result.window_end - result.window_start == timedelta(days=5)


def test_no_derivation_for_fractional_non_set_or_naive_inputs():
    assert derive(declared_sets=0) is None and derive(declared_sets=-2) is None
    assert derive(declared_sets=1.5) is None and derive(declared_sets=True) is None
    assert derive(yield_uom="GRAM") is None
    assert derive(started_at=datetime(2026, 10, 6, 9)) is None


def test_eligible_quantity_is_net_of_harvest_never_below_allocation_or_zero():
    assert in_progress_eligible_quantity(Decimal("3"), Decimal("2"), Decimal("0")) == 1
    assert in_progress_eligible_quantity(Decimal("3"), Decimal("3"), Decimal("0")) == 0
    assert in_progress_eligible_quantity(Decimal("3"), Decimal("3"), Decimal("1")) == 1
    assert in_progress_eligible_quantity(Decimal("3"), Decimal("5"), Decimal("0")) == 0


def test_compatibility_requires_window_start_within_delivery_minus_min_lead():
    start = datetime(2026, 8, 14, 5, tzinfo=timezone.utc)
    assert in_progress_compatible_with_delivery(start, date(2026, 8, 15), 1)
    assert not in_progress_compatible_with_delivery(start, date(2026, 8, 14), 1)
    assert not in_progress_compatible_with_delivery(datetime(2026, 8, 16, tzinfo=timezone.utc), date(2026, 8, 15), 1)
