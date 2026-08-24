from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.identity import (
    CommissionIdentityRegistration, IdentityRegistrationCommissioningService,
)
from src.tpo_core.application.seed_lot_commissioning.errors import (
    SeedLotDuplicateError, SeedLotIdempotencyConflictError,
)
from src.tpo_core.application.seed_lot_commissioning.models import (
    FACT_FIELDS, CommissionSeedLot, SeedLotCommissioningAuthority, SeedLotFactSource,
)
from src.tpo_core.domain.identifiers import ActorId, LottoSemeId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.identity_commissioning import PostgreSQLIdentityRegistrationCommissioningWriter
from src.tpo_core.infrastructure.postgresql.seed_lot_commissioning import PostgreSQLSeedLotCommissioningWriter
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory


def command(key="key-1", lot="LOT-1", quantity="10.123456"):
    provenance = tuple((field, SeedLotFactSource.UNKNOWN if field in {"expiry_date", "anomaly"}
                        else SeedLotFactSource.OWNER_AUTHORIZED) for field in FACT_FIELDS)
    return CommissionSeedLot(
        "Supplier", "REF-1", lot, date(2026, 8, 24), None,
        Quantity(Decimal(quantity), UnitOfMeasure.GRAM), None, provenance,
        SeedLotCommissioningAuthority(ActorId("owner"), "commission", "corr-1", key),
    )


@pytest.fixture
def environment(isolated_postgresql):
    cluster_engine = isolated_postgresql.engine
    database_name = f"tpo_seed_lot_{uuid.uuid4().hex}"
    with cluster_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    engine = sa.create_engine(cluster_engine.url.set(database=database_name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
        connection.exec_driver_sql(
            """INSERT INTO tpo.sementi
               (fornitore,referenza_commerciale,attiva,created_by,updated_at,updated_by,version)
               VALUES ('Supplier','REF-1',true,'test',CURRENT_TIMESTAMP,'test',0)"""
        )
    factory = _Factory(engine)
    service = IdentityRegistrationCommissioningService(
        PostgreSQLIdentityRegistrationCommissioningWriter(factory)
    )
    service.commission(CommissionIdentityRegistration(
        LottoSemeId.sequence_name, LottoSemeId, LottoSemeId.prefix, ActorId("identity"),
    ))
    try:
        yield engine, PostgreSQLSeedLotCommissioningWriter(factory)
    finally:
        engine.dispose()
        with cluster_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')


def test_atomic_persistence_identity_audit_precision_and_replay(environment):
    engine, writer = environment
    first = writer.commission(command())
    replay = writer.commission(command())
    assert first.seed_lot_id == replay.seed_lot_id == LottoSemeId("LSE-000001")
    assert first.outcome == "INSERTED" and replay.outcome == "COMPATIBLE_REPLAY"
    with engine.connect() as connection:
        lot = connection.exec_driver_sql(
            "SELECT public_id,quantita_iniziale,quantita_residua,unita_misura FROM tpo.lotti_seme"
        ).one()
        counts = connection.exec_driver_sql(
            """SELECT (SELECT count(*) FROM tpo.seed_lot_commissioning_requests),
                      (SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='LOTTO_SEME')"""
        ).one()
        sequence = connection.exec_driver_sql(
            "SELECT next_value,version FROM tpo.id_sequences WHERE sequence_name='LOTTO_SEME_ID'"
        ).one()
    assert lot == ("LSE-000001", Decimal("10.123456"), Decimal("10.123456"), "GRAM")
    assert counts == (1, 1) and sequence == (2, 1)


def test_idempotency_conflict_and_duplicate_are_distinct(environment):
    engine, writer = environment; writer.commission(command())
    with pytest.raises(SeedLotIdempotencyConflictError):
        writer.commission(command(quantity="11"))
    with pytest.raises(SeedLotDuplicateError):
        writer.commission(command(key="key-2"))
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM tpo.lotti_seme").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT next_value FROM tpo.id_sequences WHERE sequence_name='LOTTO_SEME_ID'").scalar_one() == 2


def test_audit_failure_rolls_back_lot_request_and_identity(environment):
    engine, writer = environment
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE FUNCTION tpo.fail_seed_lot_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.entity_type='LOTTO_SEME' THEN RAISE EXCEPTION 'test audit failure'; END IF; RETURN NEW; END $$
        """)
        connection.exec_driver_sql("""
            CREATE TRIGGER fail_seed_lot_audit BEFORE INSERT ON tpo.audit_eventi
            FOR EACH ROW EXECUTE FUNCTION tpo.fail_seed_lot_audit()
        """)
    with pytest.raises(Exception):
        writer.commission(command())
    with engine.connect() as connection:
        counts = connection.exec_driver_sql(
            """SELECT (SELECT count(*) FROM tpo.lotti_seme),
                      (SELECT count(*) FROM tpo.seed_lot_commissioning_requests),
                      (SELECT next_value FROM tpo.id_sequences WHERE sequence_name='LOTTO_SEME_ID')"""
        ).one()
    assert counts == (0, 0, 1)


def test_constitutive_and_idempotency_authorities_are_immutable(environment):
    engine, writer = environment
    writer.commission(command())
    forbidden = (
        "UPDATE tpo.lotti_seme SET public_id='LSE-999999'",
        "UPDATE tpo.lotti_seme SET semente_id=semente_id+1",
        "UPDATE tpo.lotti_seme SET numero_lotto_produttore='OTHER'",
        "UPDATE tpo.seed_lot_commissioning_requests SET canonical_payload_hash=repeat('a',64)",
        "DELETE FROM tpo.seed_lot_commissioning_requests",
    )
    for statement in forbidden:
        with engine.connect() as connection:
            with pytest.raises(sa.exc.DBAPIError):
                connection.exec_driver_sql(statement)
                connection.commit()
            connection.rollback()
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            """SELECT l.public_id,r.result_public_id,r.outcome
               FROM tpo.lotti_seme l
               JOIN tpo.seed_lot_commissioning_requests r ON r.seed_lot_id=l.id"""
        ).one()
    assert row == ("LSE-000001", "LSE-000001", "COMMITTED")


def _concurrently(*calls):
    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        futures = [executor.submit(call) for call in calls]
        results, errors = [], []
        for future in futures:
            try:
                results.append(future.result(timeout=15))
            except Exception as exc:
                errors.append(exc)
    return results, errors


def test_concurrent_same_key_same_payload_reconciles_to_one_result(environment):
    engine, writer = environment
    results, errors = _concurrently(
        lambda: writer.commission(command()), lambda: writer.commission(command()),
    )
    assert errors == []
    assert {result.seed_lot_id for result in results} == {LottoSemeId("LSE-000001")}
    assert {result.outcome for result in results} == {"INSERTED", "COMPATIBLE_REPLAY"}
    with engine.connect() as connection:
        counts = connection.exec_driver_sql(
            """SELECT (SELECT count(*) FROM tpo.lotti_seme),
                      (SELECT count(*) FROM tpo.seed_lot_commissioning_requests),
                      (SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='LOTTO_SEME'),
                      (SELECT next_value FROM tpo.id_sequences WHERE sequence_name='LOTTO_SEME_ID')"""
        ).one()
    assert counts == (1, 1, 1, 2)


def test_concurrent_same_key_different_payload_is_typed_conflict(environment):
    engine, writer = environment
    results, errors = _concurrently(
        lambda: writer.commission(command(quantity="10")),
        lambda: writer.commission(command(quantity="11")),
    )
    assert len(results) == 1 and results[0].outcome == "INSERTED"
    assert len(errors) == 1 and isinstance(errors[0], SeedLotIdempotencyConflictError)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM tpo.lotti_seme").scalar_one() == 1


def test_concurrent_different_keys_same_lot_is_genuine_duplicate(environment):
    engine, writer = environment
    results, errors = _concurrently(
        lambda: writer.commission(command(key="key-a")),
        lambda: writer.commission(command(key="key-b")),
    )
    assert len(results) == 1 and results[0].outcome == "INSERTED"
    assert len(errors) == 1 and isinstance(errors[0], SeedLotDuplicateError)
    with engine.connect() as connection:
        counts = connection.exec_driver_sql(
            """SELECT (SELECT count(*) FROM tpo.lotti_seme),
                      (SELECT count(*) FROM tpo.seed_lot_commissioning_requests),
                      (SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='LOTTO_SEME')"""
        ).one()
    assert counts == (1, 1, 1)
