"""Fail-closed helpers and frozen SQL contract for the Planning input loader."""

from decimal import Decimal
import inspect

import pytest

from src.tpo_core.application.production_planning.errors import ProductionPlanningError
from src.tpo_core.infrastructure.postgresql.production_planning_input import (
    PostgreSQLProductionPlanningInputAdapter, _balance,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import (
    migration_postgresql, writer_cluster,
    writer_database as planning_input_database,
)


def test_resource_balance_rejects_negative_residual_and_uom_mismatch():
    with pytest.raises(ProductionPlanningError) as overallocated:
        _balance(Decimal("1"), "SET", Decimal("1.1"), "SET")
    assert overallocated.value.category == "ALLOCATION_CONFLICT"
    with pytest.raises(ProductionPlanningError) as mismatch:
        _balance(Decimal("1"), "SET", Decimal("0.1"), "GRAM")
    assert mismatch.value.code == "RESOURCE_UOM_MISMATCH"


def test_loader_uses_one_read_only_repeatable_read_transaction():
    source = inspect.getsource(PostgreSQLProductionPlanningInputAdapter.load)
    assert "REPEATABLE READ READ ONLY" in source
    assert source.count("self._connection_factory.connect()") == 1
    assert source.count("connection.commit()") == 1


def test_stock_has_no_readiness_and_semina_reads_0015_authority_directly():
    source = inspect.getsource(PostgreSQLProductionPlanningInputAdapter)
    stock_method = inspect.getsource(PostgreSQLProductionPlanningInputAdapter._stock)
    semina_method = inspect.getsource(PostgreSQLProductionPlanningInputAdapter._in_progress)
    assert "readiness" not in stock_method.lower()
    for field in ("expected_useful_quantity", "expected_useful_uom",
                  "harvest_window_start", "harvest_window_end"):
        assert field in semina_method
    assert "data_avvio" not in semina_method and "protocol fallback" not in source.lower()


def test_all_semantic_queries_have_explicit_deterministic_ordering():
    for method_name in (
        "_demands", "_knowledge", "_allocations", "_stock", "_in_progress",
        "_harvests", "_current_plans", "_current_lines", "_dispositions",
    ):
        source = inspect.getsource(getattr(PostgreSQLProductionPlanningInputAdapter, method_name))
        assert "ORDER BY" in source


def test_current_lines_executes_against_schema_migrated_to_0015(
    planning_input_database,
):
    with planning_input_database.connect() as connection:
        with connection.connection.cursor() as cursor:
            assert PostgreSQLProductionPlanningInputAdapter._current_lines(cursor) == ()
