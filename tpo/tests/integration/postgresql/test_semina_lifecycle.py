from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
import uuid

from src.tpo_core.application.semina_commissioning.models import SeminaFactSource
from src.tpo_core.application.semina_lifecycle.errors import (
    SeminaAlreadyClosedError, SeminaLifecycleCommitOutcomeUncertainError,
    SeminaLifecycleCommitRolledBackError,
    SeminaLifecycleIdempotencyConflictError,
    SeminaLifecycleTimestampRegressionError, SeminaTransitionInvalidError,
    SeminaVersionConflictError,
)
from src.tpo_core.application.semina_lifecycle.models import (
    SeminaFinalOutcome, SeminaLifecycleAuthority, TransitionSemina,
)
from src.tpo_core.domain.identifiers import ActorId, SeminaId
from src.tpo_core.domain.states import SeminaState
from src.tpo_core.infrastructure.postgresql.semina_lifecycle import PostgreSQLSeminaLifecycleWriter
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql
from tests.integration.postgresql.test_semina_commissioning import command as commission_command
from tests.integration.postgresql.test_semina_commissioning import environment

BASE = datetime(2026, 8, 25, 9, tzinfo=timezone.utc)


def transition(target, version, *, key=None, at=None, outcome=None):
    if target is SeminaState.CHIUSA and outcome is None:
        outcome = SeminaFinalOutcome.INTERRUZIONE
    facts = {"target_state", "effective_at"}
    if target is SeminaState.CHIUSA:
        facts.add("final_outcome")
    key = key or f"transition-{version}-{target.value}"
    return TransitionSemina(
        SeminaId("SEM-000001"), version, target,
        at or BASE + timedelta(minutes=version), outcome,
        tuple((fact, SeminaFactSource.OWNER_AUTHORIZED) for fact in facts),
        SeminaLifecycleAuthority(ActorId("owner"), "physical transition", f"corr-{key}", key),
    )


@pytest.fixture
def lifecycle(environment):
    engine, commissioner = environment
    commissioner.commission(commission_command())
    return engine, PostgreSQLSeminaLifecycleWriter(_Factory(engine))


def scalar(engine, sql):
    with engine.connect() as connection:
        return connection.exec_driver_sql(sql).scalar_one()


def test_ordinary_graph_event_audit_replay_and_no_downstream_mutation(lifecycle):
    engine, writer = lifecycle
    with engine.connect() as connection:
        downstream_before = connection.exec_driver_sql(
            "SELECT (SELECT count(*) FROM tpo.raccolte),"
            "(SELECT count(*) FROM tpo.stock),"
            "(SELECT count(*) FROM tpo.piano_produzione_revisioni)"
        ).one()
    edges = [SeminaState.GERMINAZIONE, SeminaState.LUCE, SeminaState.CRESCITA,
             SeminaState.PRONTA_ALLA_RACCOLTA]
    results = [writer.transition(transition(target, version))
               for version, target in enumerate(edges)]
    replay = writer.transition(transition(SeminaState.GERMINAZIONE, 0))
    assert [result.version_after for result in results] == [1, 2, 3, 4]
    assert replay.outcome == "COMPATIBLE_REPLAY" and replay.version_after == 1
    with engine.connect() as connection:
        semina = connection.exec_driver_sql(
            "SELECT stato,version,esito_finale,expected_useful_quantity,expected_useful_uom,harvest_window_start,harvest_window_end FROM tpo.semine WHERE public_id='SEM-000001'"
        ).one()
        authority_counts = connection.exec_driver_sql(
            "SELECT (SELECT count(*) FROM tpo.semina_lifecycle_eventi),"
            "(SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='SEMINA' AND operation='STATE_TRANSITION'),"
            "(SELECT count(*) FROM tpo.semina_lifecycle_transition_requests "
            " WHERE outcome='COMMITTED' AND result_event_id IS NOT NULL)"
        ).one()
        downstream_after = connection.exec_driver_sql(
            "SELECT (SELECT count(*) FROM tpo.raccolte),"
            "(SELECT count(*) FROM tpo.stock),"
            "(SELECT count(*) FROM tpo.piano_produzione_revisioni)"
        ).one()
    assert semina == ("PRONTA_ALLA_RACCOLTA", 4, None, None, None, None, None)
    assert authority_counts == (4, 4, 4)
    assert downstream_after == downstream_before


@pytest.mark.parametrize("advance", [0, 1, 2, 3, 4])
def test_every_active_state_can_close_with_frozen_outcome(lifecycle, advance):
    engine, writer = lifecycle
    path = [SeminaState.GERMINAZIONE, SeminaState.LUCE, SeminaState.CRESCITA,
            SeminaState.PRONTA_ALLA_RACCOLTA]
    for version, target in enumerate(path[:advance]):
        writer.transition(transition(target, version))
    result = writer.transition(transition(
        SeminaState.CHIUSA, advance, key=f"close-{advance}",
        outcome=SeminaFinalOutcome.SCARTO_TOTALE,
    ))
    assert result.resulting_state is SeminaState.CHIUSA
    assert scalar(engine, "SELECT esito_finale::text FROM tpo.semine WHERE public_id='SEM-000001'") == "SCARTO_TOTALE"
    with pytest.raises(SeminaAlreadyClosedError):
        writer.transition(transition(SeminaState.CHIUSA, advance + 1, key="close-again"))


def test_skips_backwards_same_state_timestamp_and_idempotency_fail_closed(lifecycle):
    engine, writer = lifecycle
    with pytest.raises(SeminaTransitionInvalidError):
        writer.transition(transition(SeminaState.LUCE, 0, key="skip"))
    first = writer.transition(transition(SeminaState.GERMINAZIONE, 0, key="first"))
    with pytest.raises(SeminaTransitionInvalidError):
        writer.transition(transition(SeminaState.GERMINAZIONE, 1, key="duplicate"))
    with pytest.raises(SeminaTransitionInvalidError):
        writer.transition(transition(SeminaState.AVVIATA, 1, key="back"))
    with pytest.raises(SeminaLifecycleTimestampRegressionError):
        writer.transition(transition(SeminaState.LUCE, 1, key="regress", at=first.effective_at))
    with pytest.raises(SeminaLifecycleIdempotencyConflictError):
        writer.transition(transition(SeminaState.GERMINAZIONE, 0, key="first",
                                     at=first.effective_at + timedelta(seconds=1)))
    assert scalar(engine, "SELECT count(*) FROM tpo.semina_lifecycle_eventi") == 1


def test_start_bound_event_immutability_and_atomic_rollback(lifecycle):
    engine, writer = lifecycle
    with pytest.raises(SeminaLifecycleTimestampRegressionError):
        writer.transition(transition(SeminaState.GERMINAZIONE, 0, key="early",
                                     at=datetime(2026, 8, 25, 7, 59, tzinfo=timezone.utc)))
    writer.transition(transition(SeminaState.GERMINAZIONE, 0))
    with engine.connect() as connection:
        with pytest.raises(
            sa.exc.DBAPIError,
            match="Semina lifecycle event authority is immutable",
        ):
            connection.exec_driver_sql("UPDATE tpo.semina_lifecycle_eventi SET reason='changed'")
        connection.rollback()
    assert scalar(engine, "SELECT count(*) FROM tpo.semina_lifecycle_transition_requests") == 1


def test_concurrent_same_version_allows_at_most_one(lifecycle):
    engine, writer = lifecycle
    commands = [transition(SeminaState.GERMINAZIONE, 0, key="race-forward"),
                transition(SeminaState.CHIUSA, 0, key="race-close")]
    def execute(command):
        try:
            return writer.transition(command).outcome
        except Exception as exc:
            return type(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, commands))
    assert results.count("INSERTED") == 1
    assert any(result in (SeminaVersionConflictError, SeminaAlreadyClosedError,
                          SeminaTransitionInvalidError) for result in results)
    assert scalar(engine, "SELECT count(*) FROM tpo.semina_lifecycle_eventi") == 1


def test_request_result_integrity_replay_and_immutability(lifecycle):
    engine, writer = lifecycle
    with engine.begin() as connection:
        reserved = connection.exec_driver_sql(
            """INSERT INTO tpo.semina_lifecycle_transition_requests
               (operation_scope,idempotency_key,canonical_payload_hash,result_event_id,
                outcome,recorded_at,created_by)
               VALUES ('SEMINA_LIFECYCLE_TRANSITION_V1','reserved-only',%s,NULL,
                       'RESERVED',CURRENT_TIMESTAMP,'test') RETURNING id""",
            ("a" * 64,),
        ).scalar_one()
    with pytest.raises(
        sa.exc.DBAPIError,
        match="Semina lifecycle request authority is immutable",
    ):
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE tpo.semina_lifecycle_transition_requests SET outcome='COMMITTED' WHERE id=%s",
                (reserved,),
            )

    command = transition(SeminaState.GERMINAZIONE, 0, key="authoritative")
    inserted = writer.transition(command)
    replay = writer.transition(command)
    assert replay.outcome == "COMPATIBLE_REPLAY"
    assert replay.semina_public_id == inserted.semina_public_id
    assert replay.resulting_state == inserted.resulting_state
    assert inserted.version_after == replay.version_after == 1
    with engine.connect() as connection:
        request_id, result_event_id, event_id, event_request_id = connection.exec_driver_sql(
            """SELECT r.id,r.result_event_id,e.id,e.request_id
               FROM tpo.semina_lifecycle_transition_requests r
               JOIN tpo.semina_lifecycle_eventi e
                 ON e.id=r.result_event_id AND e.request_id=r.id
               WHERE r.idempotency_key='authoritative'"""
        ).one()
        replay_counts = connection.exec_driver_sql(
            """SELECT
                 (SELECT count(*) FROM tpo.semina_lifecycle_eventi
                    WHERE request_id=%s),
                 (SELECT count(*) FROM tpo.audit_eventi
                    WHERE correlation_id='corr-authoritative'
                      AND entity_type='SEMINA' AND operation='STATE_TRANSITION'),
                 (SELECT version FROM tpo.semine WHERE public_id='SEM-000001')""",
            (request_id,),
        ).one()
    assert request_id == event_request_id and result_event_id == event_id
    assert replay_counts == (1, 1, 1)

    with engine.begin() as connection:
        unrelated = connection.exec_driver_sql(
            """INSERT INTO tpo.semina_lifecycle_transition_requests
               (operation_scope,idempotency_key,canonical_payload_hash,result_event_id,
                outcome,recorded_at,created_by)
               VALUES ('SEMINA_LIFECYCLE_TRANSITION_V1','unrelated',%s,NULL,
                       'RESERVED',CURRENT_TIMESTAMP,'test') RETURNING id""",
            ("b" * 64,),
        ).scalar_one()
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """UPDATE tpo.semina_lifecycle_transition_requests
                   SET outcome='COMMITTED',result_event_id=%s WHERE id=%s""",
                (event_id, unrelated),
            )
            connection.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
    for statement in (
        "UPDATE tpo.semina_lifecycle_transition_requests SET result_event_id=NULL WHERE id=%s",
        "DELETE FROM tpo.semina_lifecycle_transition_requests WHERE id=%s",
    ):
        with pytest.raises(sa.exc.DBAPIError):
            with engine.begin() as connection:
                connection.exec_driver_sql(statement, (request_id,))
    for statement in (
        "UPDATE tpo.semina_lifecycle_eventi SET reason='changed' WHERE id=%s",
        "DELETE FROM tpo.semina_lifecycle_eventi WHERE id=%s",
    ):
        with pytest.raises(sa.exc.DBAPIError):
            with engine.begin() as connection:
                connection.exec_driver_sql(statement, (event_id,))


def test_failure_after_event_insert_rolls_back_every_authority(lifecycle):
    engine, writer = lifecycle
    with engine.begin() as connection:
        connection.exec_driver_sql("""
        CREATE FUNCTION tpo.fail_lifecycle_audit() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF NEW.correlation_id='corr-audit-fail' THEN
          RAISE EXCEPTION 'test-only lifecycle audit failure';
        END IF; RETURN NEW; END $$;
        CREATE TRIGGER fail_lifecycle_audit BEFORE INSERT ON tpo.audit_eventi
        FOR EACH ROW EXECUTE FUNCTION tpo.fail_lifecycle_audit()
        """)
    command = transition(SeminaState.GERMINAZIONE, 0, key="audit-fail")
    with pytest.raises(SeminaLifecycleCommitRolledBackError):
        writer.transition(command)
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT stato,version FROM tpo.semine WHERE public_id='SEM-000001'"
        ).one() == ("AVVIATA", 0)
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.semina_lifecycle_eventi"
        ).scalar_one() == 0
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.semina_lifecycle_transition_requests WHERE idempotency_key='audit-fail'"
        ).scalar_one() == 0
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE correlation_id='corr-audit-fail'"
        ).scalar_one() == 0


def test_ready_vs_close_from_crescita_same_version(lifecycle):
    engine, writer = lifecycle
    for version, target in enumerate((SeminaState.GERMINAZIONE, SeminaState.LUCE,
                                      SeminaState.CRESCITA)):
        writer.transition(transition(target, version, key=f"prepare-{version}"))
    commands = (
        transition(SeminaState.PRONTA_ALLA_RACCOLTA, 3, key="race-ready"),
        transition(SeminaState.CHIUSA, 3, key="race-closed"),
    )
    def execute(command):
        try:
            return writer.transition(command).resulting_state
        except Exception as exc:
            return type(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, commands))
    winners = [value for value in results if isinstance(value, SeminaState)]
    assert len(winners) == 1
    losers = [value for value in results if isinstance(value, type)]
    assert len(losers) == 1
    assert losers[0] in (
        SeminaVersionConflictError,
        SeminaAlreadyClosedError,
        SeminaTransitionInvalidError,
    )
    with engine.connect() as connection:
        state, version = connection.exec_driver_sql(
            "SELECT stato,version FROM tpo.semine WHERE public_id='SEM-000001'"
        ).one()
        events = connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.semina_lifecycle_eventi"
        ).scalar_one()
        audits = connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.audit_eventi WHERE entity_type='SEMINA' AND operation='STATE_TRANSITION'"
        ).scalar_one()
    assert state == winners[0].value and version == 4
    assert events == audits == 4


def test_uncertain_commit_reconciles_by_same_key(lifecycle):
    engine, _ = lifecycle
    class CommitRaisesAfter:
        def __init__(self, connection): self._connection = connection
        def __getattr__(self, name): return getattr(self._connection, name)
        def commit(self):
            self._connection.commit()
            raise psycopg.OperationalError("test-only uncertain commit")
    class UncertainFactory:
        def connect(self): return CommitRaisesAfter(_Factory(engine).connect())
    command = transition(SeminaState.GERMINAZIONE, 0, key="uncertain")
    with pytest.raises(SeminaLifecycleCommitOutcomeUncertainError):
        PostgreSQLSeminaLifecycleWriter(UncertainFactory()).transition(command)
    replay = PostgreSQLSeminaLifecycleWriter(_Factory(engine)).transition(command)
    assert replay.outcome == "COMPATIBLE_REPLAY" and replay.version_after == 1
    assert scalar(engine, "SELECT count(*) FROM tpo.semina_lifecycle_eventi") == 1


def test_lifecycle_migration_empty_roundtrip(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_lifecycle_migration_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    try:
        with engine.connect() as connection:
            config = make_config(connection=connection)
            alembic_command.upgrade(config, "20260825_0019")
            alembic_command.upgrade(config, "20260825_0020")
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260825_0020"
            alembic_command.downgrade(config, "20260825_0019")
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260825_0019"
            alembic_command.upgrade(config, "20260825_0020")
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260825_0020"
    finally:
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


def test_lifecycle_downgrade_with_history_fails_without_partial_destruction(lifecycle):
    engine, writer = lifecycle
    writer.transition(transition(SeminaState.GERMINAZIONE, 0, key="history"))
    with engine.connect() as connection:
        starting_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
        with pytest.raises(Exception):
            alembic_command.downgrade(make_config(connection=connection), "20260825_0019")
        connection.rollback()
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == starting_revision
        assert connection.exec_driver_sql("SELECT count(*) FROM tpo.semina_lifecycle_eventi").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT count(*) FROM tpo.semina_lifecycle_transition_requests").scalar_one() == 1
