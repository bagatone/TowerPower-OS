from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.semente_commissioning.errors import (
    SementeDuplicateError, SementeIdempotencyConflictError,
)
from src.tpo_core.application.semente_commissioning.models import (
    CommissionSemente, SementeCommissioningAuthority,
)
from src.tpo_core.domain.identifiers import ActorId
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.semente_commissioning import PostgreSQLSementeCommissioningWriter
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql


def command(key="key-1", fornitore="INTERSEMILLAS", referenza="VERDE MICROGREENS"):
    return CommissionSemente(
        fornitore, referenza, None, None, "Sin tratamiento", None,
        SementeCommissioningAuthority(ActorId("owner"), "commission", "corr-1", key),
    )


@pytest.fixture
def environment(isolated_postgresql):
    cluster_engine = isolated_postgresql.engine
    database_name = f"tpo_semente_{uuid.uuid4().hex}"
    with cluster_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    engine = sa.create_engine(cluster_engine.url.set(database=database_name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
    factory = _Factory(engine)
    try:
        yield engine, PostgreSQLSementeCommissioningWriter(factory)
    finally:
        engine.dispose()
        with cluster_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')


def test_atomic_persistence_identity_audit_precision_and_replay(environment):
    engine, writer = environment
    first = writer.commission(command())
    replay = writer.commission(command())
    assert first.semente_id == replay.semente_id
    assert first.outcome == "INSERTED" and replay.outcome == "COMPATIBLE_REPLAY"
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT fornitore,referenza_commerciale,trattamento,attiva FROM tpo.sementi"
        ).one()
        counts = connection.exec_driver_sql(
            """SELECT (SELECT count(*) FROM tpo.semente_commissioning_requests),
                      (SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='SEMENTE')"""
        ).one()
    assert row.fornitore == "INTERSEMILLAS"
    assert row.referenza_commerciale == "VERDE MICROGREENS"
    assert row.trattamento == "Sin tratamiento"
    assert row.attiva is True
    assert counts[0] == 1
    assert counts[1] == 1


def test_same_key_different_payload_is_a_typed_conflict(environment):
    _, writer = environment
    writer.commission(command())
    with pytest.raises(SementeIdempotencyConflictError):
        writer.commission(command(referenza="ALTRO"))


def test_same_business_key_different_request_is_a_typed_duplicate(environment):
    _, writer = environment
    writer.commission(command(key="key-1"))
    with pytest.raises(SementeDuplicateError):
        writer.commission(command(key="key-2"))


def test_normalization_backstop_prevents_case_and_whitespace_duplicates(environment):
    _, writer = environment
    writer.commission(command(key="key-1", fornitore="INTERSEMILLAS", referenza="VERDE MICROGREENS"))
    with pytest.raises(SementeDuplicateError):
        writer.commission(command(key="key-2", fornitore="  intersemillas  ", referenza="  verde microgreens  "))


def test_concurrent_identical_commissioning_converges_to_one_semente(environment):
    engine, writer = environment
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: writer.commission(command()), range(8)))
    ids = {result.semente_id for result in results}
    assert ids == {results[0].semente_id}
    with engine.connect() as connection:
        count = connection.exec_driver_sql("SELECT count(*) FROM tpo.sementi").scalar_one()
    assert count == 1


def test_constitutive_fields_are_immutable_at_the_database_level(environment):
    engine, writer = environment
    writer.commission(command())
    with engine.begin() as connection:
        with pytest.raises(sa.exc.DBAPIError):
            connection.exec_driver_sql("UPDATE tpo.sementi SET fornitore='OTHER'")
