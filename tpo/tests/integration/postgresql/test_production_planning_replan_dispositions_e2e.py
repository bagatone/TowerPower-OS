"""Real PostgreSQL: un replanning con disposition set AUTHORIZED si completa.

Regressione 5/10/2026: ``ReplanProductionPlanningCommand`` e' sottoclasse di
``InitialProductionPlanningCommand`` e il service rifiutava ogni replanning
con disposition (INITIAL_DISPOSITIONS_NOT_EMPTY): il percorso non era mai stato
esercitato end to end.
"""

from __future__ import annotations

import pytest

from src.tpo_core.application.production_planning.errors import ProductionPlanningError
from src.tpo_core.application.production_planning.models import (
    PlanningExecutionContext, PolicyVersionReference, PublicId,
    ReplanProductionPlanningCommand,
)
from src.tpo_core.domain.identifiers import ActorId
from tests.integration.postgresql.replan_disposition_authoring import (
    DispositionAuthoringError, author_invalidation_set,
)
from tests.integration.postgresql.test_production_planning_end_to_end import (
    BUSINESS_AT, _command, _scalar, _seed_identity, _service,
)
from tests.integration.postgresql.test_production_planning_end_to_end import (  # noqa: F401
    migration_postgresql, planning_database, writer_cluster,
)

CORRELATION = "replan-con-disposition"


def _replan_command(correlation_id: str = CORRELATION) -> ReplanProductionPlanningCommand:
    return ReplanProductionPlanningCommand(
        business_at=BUSINESS_AT,
        policy=PolicyVersionReference("DEFAULT", 1),
        context=PlanningExecutionContext(
            ActorId("tpo.planning-e2e"), "Replanning con disposition", correlation_id,
        ),
        previous_revision_public_id=PublicId("RVP-000001"),
        order_line_public_id=PublicId("RO-000001"),
        replanning_reason_code="STOCK_CHANGED",
    )


def _initial_full_stock_plan(engine) -> None:
    _seed_identity(engine)
    assert _service(engine).execute(_command("e2e-initial-stock")).run_state == "COMMITTED"
    assert _scalar(engine, "SELECT count(*) FROM tpo.allocazioni WHERE state='ATTIVA' "
                           "AND allocation_type='STOCK'") == 1


def _author(engine, *, allocations=("ALL-000001",), correlation=CORRELATION):
    with engine.begin() as connection:
        cursor = connection.connection.cursor()
        try:
            return author_invalidation_set(
                cursor, previous_revision="RVP-000001", order_line="RO-000001",
                reason_code="STOCK_CHANGED", correlation_id=correlation,
                allocation_public_ids=allocations, cause="STOCK_QUANTITY_INVALIDATED",
                reason="regressione e2e", provenance="test-e2e", authorized_by="matteo",
            )
        finally:
            cursor.close()


def test_replan_with_authorized_disposition_commits_and_invalidates(planning_database):
    engine = planning_database
    _initial_full_stock_plan(engine)
    _author(engine)
    # l'autorizzazione e' inerte: nessuna allocazione cambia prima del replanning.
    assert _scalar(engine, "SELECT state FROM tpo.allocazioni WHERE public_id='ALL-000001'") == "ATTIVA"
    assert _scalar(engine, "SELECT count(*) FROM tpo.transizioni_allocazione") == 0

    result = _service(engine).execute(_replan_command())

    assert result.run_state == "COMMITTED"
    assert _scalar(engine, "SELECT state FROM tpo.allocazioni WHERE public_id='ALL-000001'") == "INVALIDA"
    assert _scalar(engine, "SELECT transition_type FROM tpo.transizioni_allocazione") == "INVALIDA"
    assert _scalar(engine, "SELECT count(*) FROM tpo.piano_produzione_revisioni") == 2


def test_replan_without_authorized_disposition_fails_and_changes_nothing(planning_database):
    engine = planning_database
    _initial_full_stock_plan(engine)
    with pytest.raises(ProductionPlanningError):
        _service(engine).execute(_replan_command())
    assert _scalar(engine, "SELECT count(*) FROM tpo.piano_produzione_revisioni") == 1
    assert _scalar(engine, "SELECT state FROM tpo.allocazioni WHERE public_id='ALL-000001'") == "ATTIVA"


def test_authoring_rejects_unknown_allocation_and_writes_nothing(planning_database):
    engine = planning_database
    _initial_full_stock_plan(engine)
    with pytest.raises(DispositionAuthoringError, match="inesistenti"):
        _author(engine, allocations=("ALL-999999",))
    assert _scalar(engine, "SELECT count(*) FROM tpo.replanning_disposition_sets") == 0
