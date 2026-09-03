from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.semente_commissioning.models import (
    CommissionSemente, SementeCommissioningAuthority,
)
from src.tpo_core.application.semente_impiego_commissioning.errors import (
    ProtocolContextUnavailableError, SementeImpiegoDuplicateError,
    SementeImpiegoIdempotencyConflictError,
)
from src.tpo_core.application.semente_impiego_commissioning.models import (
    CommissionSementeImpiego, SementeImpiegoCommissioningAuthority,
)
from src.tpo_core.domain.identifiers import ActorId, ProtocolloVersioneId
from src.tpo_core.domain.states import SementeRaccomandazione
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.semente_commissioning import (
    PostgreSQLSementeCommissioningWriter,
)
from src.tpo_core.infrastructure.postgresql.semente_impiego_commissioning import (
    PostgreSQLSementeImpiegoCommissioningWriter,
)
from tests.infrastructure.postgresql.test_production_planning_commit_writer import (
    _Factory, _seed_authorities,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql


def command(key="key-1", protocol_version="PV-000001", raccomandazione=SementeRaccomandazione.RACCOMANDATA):
    return CommissionSementeImpiego(
        "INTERSEMILLAS", "VERDE MICROGREENS", ProtocolloVersioneId(protocol_version),
        raccomandazione, Decimal("85"), "Prova di germinazione.",
        SementeImpiegoCommissioningAuthority(ActorId("owner"), "commission", "corr-1", key),
    )


@pytest.fixture
def environment(isolated_postgresql):
    cluster_engine = isolated_postgresql.engine
    database_name = f"tpo_semente_impiego_{uuid.uuid4().hex}"
    with cluster_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    engine = sa.create_engine(cluster_engine.url.set(database=database_name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
        _seed_authorities(connection)
    factory = _Factory(engine)
    semente_writer = PostgreSQLSementeCommissioningWriter(factory)
    semente_writer.commission(CommissionSemente(
        "INTERSEMILLAS", "VERDE MICROGREENS", None, None, "Sin tratamiento", None,
        SementeCommissioningAuthority(ActorId("owner"), "commission", "corr-0", "seed-key"),
    ))
    try:
        yield engine, PostgreSQLSementeImpiegoCommissioningWriter(factory)
    finally:
        engine.dispose()
        with cluster_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')


def test_atomic_persistence_context_resolution_and_replay(environment):
    engine, writer = environment
    first = writer.commission(command())
    replay = writer.commission(command())
    assert first.semente_impiego_id == replay.semente_impiego_id
    assert first.outcome == "INSERTED" and replay.outcome == "COMPATIBLE_REPLAY"
    assert first.varieta_public_id == "VAR-000001"
    assert first.cultivar_denominazione == "Afila"
    assert first.uso_produttivo_denominazione == "Microgreen"
    assert first.raccomandazione is SementeRaccomandazione.RACCOMANDATA
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT raccomandazione,rating,ultima_revisione FROM tpo.semente_impieghi"
        ).one()
        counts = connection.exec_driver_sql(
            """SELECT (SELECT count(*) FROM tpo.semente_impiego_commissioning_requests),
                      (SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='SEMENTE_IMPIEGO')"""
        ).one()
    assert row.raccomandazione == "RACCOMANDATA"
    assert row.rating == Decimal("85.00")
    assert row.ultima_revisione is not None
    assert counts[0] == 1
    assert counts[1] == 1


def test_same_key_different_payload_is_a_typed_conflict(environment):
    _, writer = environment
    writer.commission(command())
    with pytest.raises(SementeImpiegoIdempotencyConflictError):
        writer.commission(command(raccomandazione=SementeRaccomandazione.SCONSIGLIATA))


def test_same_pair_different_request_is_a_typed_duplicate(environment):
    _, writer = environment
    writer.commission(command(key="key-1"))
    with pytest.raises(SementeImpiegoDuplicateError):
        writer.commission(command(key="key-2"))


def test_unresolvable_protocol_version_fails_closed(environment):
    _, writer = environment
    with pytest.raises(ProtocolContextUnavailableError):
        writer.commission(command(key="key-x", protocol_version="PV-999999"))


def test_concurrent_identical_commissioning_converges_to_one_semente_impiego(environment):
    engine, writer = environment
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: writer.commission(command()), range(8)))
    ids = {result.semente_impiego_id for result in results}
    assert ids == {results[0].semente_impiego_id}
    with engine.connect() as connection:
        count = connection.exec_driver_sql("SELECT count(*) FROM tpo.semente_impieghi").scalar_one()
    assert count == 1


def test_constitutive_pair_is_immutable_at_the_database_level(environment):
    engine, writer = environment
    writer.commission(command())
    with engine.begin() as connection:
        with pytest.raises(sa.exc.DBAPIError):
            connection.exec_driver_sql("UPDATE tpo.semente_impieghi SET semente_id=semente_id+1")
