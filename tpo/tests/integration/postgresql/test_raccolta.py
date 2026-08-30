from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import psycopg
import sqlalchemy as sa

from src.tpo_core.application.raccolta.errors import (
    RaccoltaCommitOutcomeUncertainError, RaccoltaCommitRolledBackError,
    RaccoltaIdempotencyConflictError, RaccoltaIdentityUnavailableError,
    RaccoltaSeminaNotFoundError, RaccoltaSeminaStateError,
    RaccoltaTraceabilityUnavailableError,
)
from src.tpo_core.application.raccolta.models import RaccoltaAuthority, RecordRaccolta
from src.tpo_core.application.semina_commissioning.models import SeminaFactSource
from src.tpo_core.application.semina_lifecycle.models import (
    SeminaLifecycleAuthority, TransitionSemina,
)
from src.tpo_core.domain.identifiers import ActorId, SeminaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import SeminaState
from src.tpo_core.infrastructure.postgresql.raccolta import PostgreSQLRaccoltaWriter
from src.tpo_core.infrastructure.postgresql.semina_lifecycle import PostgreSQLSeminaLifecycleWriter
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql
from tests.integration.postgresql.test_semina_commissioning import command as commission_command
from tests.integration.postgresql.test_semina_commissioning import environment

BASE = datetime(2026, 8, 30, 8, tzinfo=timezone.utc)


def harvest(key="harvest-1", *, quantity="0.5", semina="SEM-000001", at=BASE, notes=None):
    return RecordRaccolta(
        SeminaId(semina), Quantity(Decimal(quantity), UnitOfMeasure.SET), at,
        RaccoltaAuthority(ActorId("owner"), "physical harvest", f"corr-{key}", key),
        notes,
    )


def ready(engine):
    writer = PostgreSQLSeminaLifecycleWriter(_Factory(engine))
    path = [SeminaState.GERMINAZIONE, SeminaState.LUCE, SeminaState.CRESCITA,
            SeminaState.PRONTA_ALLA_RACCOLTA]
    for version, state in enumerate(path):
        facts = tuple((name, SeminaFactSource.OWNER_AUTHORIZED)
                      for name in ("target_state", "effective_at"))
        writer.transition(TransitionSemina(
            SeminaId("SEM-000001"), version, state,
            BASE - timedelta(hours=4 - version), None, facts,
            SeminaLifecycleAuthority(
                ActorId("owner"), "physical transition", f"ready-{version}",
                f"ready-{version}",
            ),
        ))


@pytest.fixture
def harvest_environment(environment):
    engine, commissioner = environment
    commissioner.commission(commission_command())
    return engine, PostgreSQLRaccoltaWriter(_Factory(engine))


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.exec_driver_sql(sql).scalar_one()


def test_missing_and_ineligible_semina_fail_without_identity_consumption(harvest_environment):
    engine, writer = harvest_environment
    before = scalar(engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'")
    with pytest.raises(RaccoltaSeminaNotFoundError):
        writer.record(harvest(semina="SEM-999999"))
    with pytest.raises(RaccoltaSeminaStateError):
        writer.record(harvest())
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 0
    assert scalar(engine, "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'") == before


@pytest.mark.parametrize(
    ("state", "outcome"),
    [("AVVIATA", None), ("GERMINAZIONE", None), ("LUCE", None),
     ("CRESCITA", None), ("CHIUSA", "INTERRUZIONE")],
)
def test_every_noneligible_semina_state_is_rejected(harvest_environment, state, outcome):
    engine, writer = harvest_environment
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE tpo.semine SET stato=%s,esito_finale=%s WHERE public_id='SEM-000001'",
            (state, outcome),
        )
    with pytest.raises(RaccoltaSeminaStateError):
        writer.record(harvest(key=f"ineligible-{state}"))
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 0


def test_creation_multiple_replay_conflict_audit_and_stock_separation(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    with engine.connect() as connection:
        before = connection.exec_driver_sql(
            "SELECT (SELECT count(*) FROM tpo.stock),(SELECT count(*) FROM tpo.movimenti_magazzino)"
        ).one()
    first = writer.record(harvest())
    replay = writer.record(harvest())
    second = writer.record(harvest("harvest-2", quantity="1.25", at=BASE + timedelta(minutes=1)))
    assert (first.raccolta_id.value, second.raccolta_id.value) == ("RAC-000001", "RAC-000002")
    assert replay.outcome == "COMPATIBLE_REPLAY" and replay.raccolta_id == first.raccolta_id
    assert first.semina_id == second.semina_id == SeminaId("SEM-000001")
    assert first.traceability_code == second.traceability_code
    with pytest.raises(RaccoltaIdempotencyConflictError):
        writer.record(harvest(quantity="0.75"))
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT public_id,quantita,unita_misura::text,operatore,destinazione_prevista "
            "FROM tpo.raccolte ORDER BY public_id"
        ).all()
        authority = connection.exec_driver_sql(
            "SELECT (SELECT count(*) FROM tpo.raccolte),"
            "(SELECT count(*) FROM tpo.raccolta_recording_requests WHERE outcome='COMMITTED'),"
            "(SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='RACCOLTA' AND operation='INSERT'),"
            "(SELECT stato FROM tpo.semine WHERE public_id='SEM-000001'),"
            "(SELECT count(*) FROM tpo.semina_lifecycle_eventi)"
        ).one()
        after = connection.exec_driver_sql(
            "SELECT (SELECT count(*) FROM tpo.stock),(SELECT count(*) FROM tpo.movimenti_magazzino)"
        ).one()
    assert rows == [("RAC-000001", Decimal("0.500000"), "SET", None, None),
                    ("RAC-000002", Decimal("1.250000"), "SET", None, None)]
    assert authority == (2, 2, 2, "PRONTA_ALLA_RACCOLTA", 4)
    assert after == before


def test_concurrent_identical_and_distinct_requests(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        identical = list(pool.map(lambda _: writer.record(harvest("same")), range(2)))
    assert {result.raccolta_id.value for result in identical} == {"RAC-000001"}
    assert {result.outcome for result in identical} == {"INSERTED", "COMPATIBLE_REPLAY"}
    commands = [harvest("distinct-a", at=BASE + timedelta(minutes=1)),
                harvest("distinct-b", at=BASE + timedelta(minutes=2))]
    with ThreadPoolExecutor(max_workers=2) as pool:
        distinct = list(pool.map(writer.record, commands))
    assert len({result.raccolta_id.value for result in distinct}) == 2
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 3


def test_missing_traceability_fails_closed(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    before = scalar(
        engine,
        "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'",
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE tpo.semine ALTER COLUMN codice_tracciabilita DROP NOT NULL")
        connection.exec_driver_sql("ALTER TABLE tpo.semine DISABLE TRIGGER protect_semina_constitutive_authority")
        connection.exec_driver_sql("UPDATE tpo.semine SET codice_tracciabilita=NULL WHERE public_id='SEM-000001'")
        connection.exec_driver_sql("ALTER TABLE tpo.semine ENABLE TRIGGER protect_semina_constitutive_authority")
    with pytest.raises(RaccoltaTraceabilityUnavailableError):
        writer.record(harvest())
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 0
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolta_recording_requests") == 0
    assert scalar(
        engine,
        "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'",
    ) == before


def test_malformed_raccolta_identity_fails_closed(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    before = scalar(
        engine,
        "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'",
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE tpo.id_sequences SET identifier_type='Wrong' WHERE sequence_name='RACCOLTA_ID'")
    with pytest.raises(RaccoltaIdentityUnavailableError):
        writer.record(harvest("missing-id"))
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 0
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolta_recording_requests") == 0
    assert scalar(
        engine,
        "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'",
    ) == before


def test_malformed_traceability_fails_closed(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    before = scalar(
        engine,
        "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'",
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE tpo.semine DROP CONSTRAINT ck_semine_codice_tracciabilita"
        )
        connection.exec_driver_sql(
            "ALTER TABLE tpo.semine DISABLE TRIGGER protect_semina_constitutive_authority"
        )
        connection.exec_driver_sql(
            "UPDATE tpo.semine SET codice_tracciabilita='INVALID' "
            "WHERE public_id='SEM-000001'"
        )
        connection.exec_driver_sql(
            "ALTER TABLE tpo.semine ENABLE TRIGGER protect_semina_constitutive_authority"
        )
    with pytest.raises(RaccoltaTraceabilityUnavailableError):
        writer.record(harvest("malformed-traceability"))
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 0
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolta_recording_requests") == 0
    assert scalar(
        engine,
        "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'",
    ) == before


def test_absent_raccolta_identity_fails_closed(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    with engine.begin() as connection:
        unrelated_before = connection.exec_driver_sql(
            "SELECT sequence_name,identifier_type,prefix,next_value,version "
            "FROM tpo.id_sequences WHERE sequence_name<>'RACCOLTA_ID' "
            "ORDER BY sequence_name"
        ).all()
        connection.exec_driver_sql(
            "DELETE FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'"
        )
    with pytest.raises(RaccoltaIdentityUnavailableError):
        writer.record(harvest("absent-identity"))
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 0
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolta_recording_requests") == 0
    with engine.connect() as connection:
        unrelated_after = connection.exec_driver_sql(
            "SELECT sequence_name,identifier_type,prefix,next_value,version "
            "FROM tpo.id_sequences WHERE sequence_name<>'RACCOLTA_ID' "
            "ORDER BY sequence_name"
        ).all()
    assert unrelated_after == unrelated_before


def test_failure_after_identity_allocation_rolls_back_and_reuses_id(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    before = scalar(
        engine,
        "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'",
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("""
            CREATE FUNCTION tpo.fail_raccolta_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.entity_type='RACCOLTA' THEN
                RAISE EXCEPTION 'test-only Raccolta audit failure';
              END IF;
              RETURN NEW;
            END $$;
            CREATE TRIGGER fail_raccolta_audit BEFORE INSERT ON tpo.audit_eventi
            FOR EACH ROW EXECUTE FUNCTION tpo.fail_raccolta_audit()
        """)
    with pytest.raises(RaccoltaCommitRolledBackError):
        writer.record(harvest("post-allocation-failure"))
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 0
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolta_recording_requests") == 0
    assert scalar(
        engine,
        "SELECT next_value FROM tpo.id_sequences WHERE sequence_name='RACCOLTA_ID'",
    ) == before
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TRIGGER fail_raccolta_audit ON tpo.audit_eventi")
        connection.exec_driver_sql("DROP FUNCTION tpo.fail_raccolta_audit()")
    recovered = writer.record(harvest("after-post-allocation-failure"))
    assert recovered.raccolta_id.value == f"RAC-{before:06d}"


def test_recording_request_transition_and_history_are_immutable(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest("request-history"))
    with engine.begin() as connection:
        semina_pk = connection.exec_driver_sql(
            "SELECT id FROM tpo.semine WHERE public_id='SEM-000001'"
        ).scalar_one()
        raccolta_pk = connection.exec_driver_sql(
            """INSERT INTO tpo.raccolte
               (public_id,semina_id,data_raccolta,quantita,unita_misura,created_by)
               VALUES ('RAC-999999',%s,%s,0.5,'SET','test') RETURNING id""",
            (semina_pk, BASE + timedelta(minutes=5)),
        ).scalar_one()
        request_pk = connection.exec_driver_sql(
            """INSERT INTO tpo.raccolta_recording_requests
               (operation_scope,idempotency_key,canonical_payload_hash,raccolta_id,
                result_public_id,outcome,recorded_at,created_by)
               VALUES ('RACCOLTA_RECORDING_V1','authorized-transition',%s,NULL,NULL,
                       'RESERVED',CURRENT_TIMESTAMP,'test') RETURNING id""",
            ("a" * 64,),
        ).scalar_one()
        connection.exec_driver_sql(
            """UPDATE tpo.raccolta_recording_requests
               SET raccolta_id=%s,result_public_id='RAC-999999',outcome='COMMITTED'
               WHERE id=%s""",
            (raccolta_pk, request_pk),
        )
    for statement in (
        "UPDATE tpo.raccolta_recording_requests SET canonical_payload_hash='" + "b" * 64
        + "' WHERE id=" + str(request_pk),
        "DELETE FROM tpo.raccolta_recording_requests WHERE id=" + str(request_pk),
    ):
        with pytest.raises(sa.exc.DBAPIError, match="Raccolta recording request authority is immutable"):
            with engine.begin() as connection:
                connection.exec_driver_sql(statement)
    with engine.begin() as connection:
        reserved_pk = connection.exec_driver_sql(
            """INSERT INTO tpo.raccolta_recording_requests
               (operation_scope,idempotency_key,canonical_payload_hash,raccolta_id,
                result_public_id,outcome,recorded_at,created_by)
               VALUES ('RACCOLTA_RECORDING_V1','arbitrary-update',%s,NULL,NULL,
                       'RESERVED',CURRENT_TIMESTAMP,'test') RETURNING id""",
            ("c" * 64,),
        ).scalar_one()
    with pytest.raises(sa.exc.DBAPIError, match="Raccolta recording request authority is immutable"):
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE tpo.raccolta_recording_requests SET created_by='other' WHERE id=%s",
                (reserved_pk,),
            )


def test_effective_and_recorded_times_are_distinct_authorities(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    result = writer.record(harvest("time-authorities"))
    with engine.connect() as connection:
        effective_at, recorded_at = connection.exec_driver_sql(
            "SELECT data_raccolta,created_at FROM tpo.raccolte WHERE public_id=%s",
            (result.raccolta_id.value,),
        ).one()
    assert effective_at == result.effective_at == BASE
    assert recorded_at == result.recorded_at
    assert effective_at != recorded_at
    assert effective_at.utcoffset() is not None and recorded_at.utcoffset() is not None


def test_uncertain_commit_reconciles_by_same_request(harvest_environment):
    engine, _ = harvest_environment
    ready(engine)

    class CommitRaisesAfter:
        def __init__(self, connection): self._connection = connection
        def __getattr__(self, name): return getattr(self._connection, name)
        def commit(self):
            self._connection.commit()
            raise psycopg.OperationalError("test-only uncertain commit")

    class UncertainFactory:
        def connect(self): return CommitRaisesAfter(_Factory(engine).connect())

    command = harvest("uncertain")
    with pytest.raises(RaccoltaCommitOutcomeUncertainError):
        PostgreSQLRaccoltaWriter(UncertainFactory()).record(command)
    replay = PostgreSQLRaccoltaWriter(_Factory(engine)).record(command)
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolte") == 1
    assert scalar(engine, "SELECT count(*) FROM tpo.raccolta_recording_requests") == 1
    assert scalar(
        engine,
        "SELECT count(*) FROM tpo.audit_eventi "
        "WHERE entity_type='RACCOLTA' AND operation='INSERT'",
    ) == 1


def test_database_immutability(harvest_environment):
    engine, writer = harvest_environment
    ready(engine)
    writer.record(harvest())
    for statement in (
        "UPDATE tpo.raccolte SET quantita=2 WHERE public_id='RAC-000001'",
        "DELETE FROM tpo.raccolte WHERE public_id='RAC-000001'",
    ):
        with pytest.raises(sa.exc.DBAPIError, match="Raccolta physical fact authority is immutable"):
            with engine.begin() as connection:
                connection.exec_driver_sql(statement)
