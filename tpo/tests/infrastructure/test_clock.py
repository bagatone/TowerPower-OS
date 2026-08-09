from src.tpo_core.domain.time_reference import CurrentSystemDate
from src.tpo_core.infrastructure.clock import SystemClock


def test_system_clock_restituisce_current_system_date_timezone_aware() -> None:
    clock = SystemClock()
    value = clock.now()

    assert isinstance(value, CurrentSystemDate)
    assert value.datetime.tzinfo is not None
    assert value.datetime.utcoffset() is not None
