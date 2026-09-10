from datetime import datetime, timedelta, timezone
import uuid

from alembic import command as alembic_command
import pytest
import sqlalchemy as sa

from src.tpo_core.application.run_lettura.errors import RunLetturaRunNotFoundError
from src.tpo_core.application.run_lettura.models import RichiediElencoRun, RichiediRunLog
from src.tpo_core.domain.identifiers import RunId
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.run_lettura import PostgreSQLRunLetturaReader
from tests.infrastructure.postgresql.test_production_planning_commit_writer import _Factory
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql,
)

STARTED = datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)


@pytest.fixture
def run_environment(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_run_lettura_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
        connection.exec_driver_sql(
            "INSERT INTO tpo.runs(public_id,started_at,completed_at,simulation,state,"
            "programmi_letti,righe_valutate,occorrenze_valutate,ordini_generati,"
            "elementi_saltati,created_by) VALUES ('RUN-000001',%s,%s,false,"
            "'SUCCESS_WITH_WARNINGS',3,10,8,2,1,'towerpower-scheduler')",
            (STARTED, STARTED + timedelta(minutes=2)),
        )
        connection.exec_driver_sql(
            "INSERT INTO tpo.run_messaggi(run_id,tipo,posizione,messaggio) "
            "SELECT id,'WARNING',1,'lotto LSE-000004 in scadenza' FROM tpo.runs "
            "WHERE public_id='RUN-000001'"
        )
        connection.exec_driver_sql(
            "INSERT INTO tpo.run_log(run_id,occurred_at,level,event_type,message,context) "
            "SELECT id,%s,'INFO','RUN_STARTED','avvio schedulazione 06:00','{}' "
            "FROM tpo.runs WHERE public_id='RUN-000001'",
            (STARTED,),
        )
        connection.exec_driver_sql(
            "INSERT INTO tpo.run_log(run_id,occurred_at,level,event_type,message,context) "
            "SELECT id,%s,'WARNING','LOTTO_IN_SCADENZA','lotto in scadenza rilevato',"
            "'{\"lotto\": \"LSE-000004\", \"giorni_residui\": 3}' "
            "FROM tpo.runs WHERE public_id='RUN-000001'",
            (STARTED + timedelta(seconds=30),),
        )
        connection.exec_driver_sql(
            "INSERT INTO tpo.runs(public_id,started_at,simulation,created_by) "
            "VALUES ('RUN-000002',%s,true,'towerpower-scheduler')",
            (STARTED + timedelta(days=1),),
        )
    return engine


def test_elenco_orders_by_started_at_descending_and_includes_messaggi(run_environment):
    reader = PostgreSQLRunLetturaReader(_Factory(run_environment))
    result = reader.elenco(RichiediElencoRun())
    ids = [r.run_id.value for r in result.runs]
    assert ids == ["RUN-000002", "RUN-000001"]
    in_progress, completed = result.runs[0], result.runs[1]
    assert in_progress.completed_at is None and in_progress.state is None
    assert in_progress.simulation is True
    assert in_progress.messaggi == ()
    assert completed.state == "SUCCESS_WITH_WARNINGS"
    assert completed.ordini_generati == 2
    assert len(completed.messaggi) == 1
    assert completed.messaggi[0].tipo == "WARNING"
    assert completed.messaggi[0].messaggio == "lotto LSE-000004 in scadenza"


def test_log_reads_voci_ordered_by_occurred_at(run_environment):
    reader = PostgreSQLRunLetturaReader(_Factory(run_environment))
    result = reader.log(RichiediRunLog(RunId("RUN-000001")))
    assert result.run_id == RunId("RUN-000001")
    assert len(result.voci) == 2
    assert result.voci[0].event_type == "RUN_STARTED"
    assert result.voci[0].context == {}
    assert result.voci[1].event_type == "LOTTO_IN_SCADENZA"
    assert result.voci[1].context == {"lotto": "LSE-000004", "giorni_residui": 3}


def test_log_of_run_without_entries_is_empty(run_environment):
    reader = PostgreSQLRunLetturaReader(_Factory(run_environment))
    result = reader.log(RichiediRunLog(RunId("RUN-000002")))
    assert result.voci == ()


def test_log_raises_when_run_not_found(run_environment):
    reader = PostgreSQLRunLetturaReader(_Factory(run_environment))
    with pytest.raises(RunLetturaRunNotFoundError):
        reader.log(RichiediRunLog(RunId("RUN-999999")))


def test_elenco_empty_when_no_runs(isolated_postgresql):
    cluster = isolated_postgresql.engine
    name = f"tpo_run_lettura_empty_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as connection:
        alembic_command.upgrade(make_config(connection=connection), "head")
    reader = PostgreSQLRunLetturaReader(_Factory(engine))
    assert reader.elenco(RichiediElencoRun()).runs == ()
