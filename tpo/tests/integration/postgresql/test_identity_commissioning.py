"""Real PostgreSQL incremental Identity commissioning and conflict rollback."""

import inspect

from alembic import command as alembic_command
import pytest

from src.tpo_core.application.identity import (
    CommissionIdentityRegistration,
    IdentityCommissioningConflictError,
    IdentityRegistrationCommissioningService,
    PersistentIdAllocator,
)
from src.tpo_core.application.identity.production_planning import (
    PRODUCTION_PLANNING_SEQUENCE_TYPES,
)
from src.tpo_core.domain.identifiers import ActorId, RunPianificazioneProduzioneId
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.identity_commissioning import (
    PostgreSQLIdentityRegistrationCommissioningWriter,
)
from src.tpo_core.infrastructure.postgresql.identity_repository import (
    PostgreSQLPersistentIdRepository,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import (
    _Factory,
)


ACTOR = ActorId("tpo.identity-commissioner")


@pytest.fixture(scope="module")
def database(isolated_postgresql):
    with isolated_postgresql.engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
        connection.exec_driver_sql(
            """INSERT INTO tpo.id_sequences
                 (sequence_name,identifier_type,prefix,next_value,version,
                  updated_at,updated_by)
               VALUES
                 ('RUN_ID','RunId','RUN',1,0,CURRENT_TIMESTAMP,'tpo.identity'),
                 ('ORDINE_ID','OrdineId','ORD',1,0,CURRENT_TIMESTAMP,'tpo.identity')"""
        )
    return isolated_postgresql.engine


def _commands():
    return tuple(
        CommissionIdentityRegistration(name, identifier_type,
                                       identifier_type.prefix, ACTOR)
        for name, identifier_type in PRODUCTION_PLANNING_SEQUENCE_TYPES.items()
    )


def test_incremental_commissioning_replay_preserves_existing_and_counters(database):
    writer = PostgreSQLIdentityRegistrationCommissioningWriter(_Factory(database))
    service = IdentityRegistrationCommissioningService(writer)
    before = _rows(database)
    first = tuple(service.commission(item) for item in _commands())
    replay = tuple(service.commission(item) for item in _commands())
    after = _rows(database)

    assert len(after) == 7
    assert after["RUN_ID"] == before["RUN_ID"]
    assert after["ORDINE_ID"] == before["ORDINE_ID"]
    assert all(item.sequence.next_value == 1 and item.sequence.version == 0
               for item in (*first, *replay))
    for command in _commands():
        assert after[command.sequence_name][:4] == (
            command.permanent_id_type.__name__, command.prefix, 1, 0
        )


def test_conflicting_sequence_fails_closed_rolls_back_and_connection_is_healthy(database):
    service = IdentityRegistrationCommissioningService(
        PostgreSQLIdentityRegistrationCommissioningWriter(_Factory(database))
    )
    original = _commands()[0]
    service.commission(original)
    conflicting_type = type(
        "ConflictingPlanningId", (original.permanent_id_type,),
        {"sequence_name": original.sequence_name, "prefix": "BAD"},
    )
    conflict = CommissionIdentityRegistration(
        original.sequence_name, conflicting_type, "BAD", ACTOR
    )
    with pytest.raises(IdentityCommissioningConflictError):
        service.commission(conflict)
    assert _rows(database)[original.sequence_name][:4] == (
        original.permanent_id_type.__name__, original.prefix, 1, 0
    )
    with database.connect() as connection:
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_first_allocation_consumes_expected_id_only_in_test_database(database):
    service = IdentityRegistrationCommissioningService(
        PostgreSQLIdentityRegistrationCommissioningWriter(_Factory(database))
    )
    command = next(
        item for item in _commands()
        if item.permanent_id_type is RunPianificazioneProduzioneId
    )
    service.commission(command)
    allocated = PersistentIdAllocator(
        PostgreSQLPersistentIdRepository(_Factory(database))
    ).allocate(command.permanent_id_type)
    assert allocated.identifier.value == "RPP-000001"
    assert allocated.sequence_after.next_value == 2
    assert allocated.sequence_after.version == 1


def test_commissioning_has_no_google_migration_or_random_dependency():
    import src.tpo_core.application.identity.models as models
    import src.tpo_core.application.identity.service as service
    import src.tpo_core.infrastructure.postgresql.identity_commissioning as writer
    source = "\n".join(inspect.getsource(item) for item in (models, service, writer)).lower()
    assert "google" not in source
    assert "sheets" not in source
    assert "uuid" not in source
    assert "random" not in source


def _rows(engine):
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            """SELECT sequence_name,identifier_type,prefix,next_value,version,
                      updated_by,updated_at
               FROM tpo.id_sequences ORDER BY sequence_name"""
        ).all()
    return {
        row[0]: (row[1], row[2], row[3], row[4], row[5], row[6])
        for row in rows
    }
