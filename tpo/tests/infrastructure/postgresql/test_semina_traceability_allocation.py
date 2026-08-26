from datetime import datetime, timezone

import pytest

from src.tpo_core.application.semina_commissioning.errors import TraceabilityDiscriminatorExhaustedError
from src.tpo_core.infrastructure.postgresql.semina_commissioning import PostgreSQLSeminaCommissioningWriter


class Cursor:
    def __init__(self, codes):
        self.codes = codes
        self.calls = []

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))

    def fetchall(self):
        return [(code,) for code in self.codes]


def test_allocator_uses_first_free_letter_and_database_transaction_lock():
    cursor = Cursor(["AFI-2508-A", "AFI-2508-C"])
    result = PostgreSQLSeminaCommissioningWriter._allocate_traceability(
        cursor, "AFI", datetime(2026, 8, 25, 8, tzinfo=timezone.utc)
    )
    assert result.value == "AFI-2508-B"
    assert "pg_advisory_xact_lock" in cursor.calls[0][0]


def test_allocator_fails_closed_after_z():
    cursor = Cursor([f"AFI-2508-{letter}" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"])
    with pytest.raises(TraceabilityDiscriminatorExhaustedError):
        PostgreSQLSeminaCommissioningWriter._allocate_traceability(
            cursor, "AFI", datetime(2026, 8, 25, 8, tzinfo=timezone.utc)
        )


def test_different_variety_or_local_day_has_independent_a_scope():
    for variety, instant, expected in (
        ("RAB", datetime(2026, 8, 25, 8, tzinfo=timezone.utc), "RAB-2508-A"),
        ("AFI", datetime(2026, 8, 26, 8, tzinfo=timezone.utc), "AFI-2608-A"),
    ):
        assert PostgreSQLSeminaCommissioningWriter._allocate_traceability(
            Cursor([]), variety, instant
        ).value == expected
