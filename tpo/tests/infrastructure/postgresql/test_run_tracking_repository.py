from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
import pytest

from src.tpo_core.application.run_tracking import (
    CompletedSchedulingRun,
    InvalidSchedulingRunError,
    OpenSchedulingRun,
    SchedulingRunAlreadyExistsError,
    SchedulingRunConflictError,
    SchedulingRunNotFoundError,
)
from src.tpo_core.domain.identifiers import RunId
from src.tpo_core.domain.states import RunState
from src.tpo_core.domain.time_reference import CurrentSystemDate
from src.tpo_core.infrastructure.postgresql.errors import PostgreSQLError
from src.tpo_core.infrastructure.postgresql.run_tracking_repository import (
    PostgreSQLSchedulingRunRepository,
)


TZ = ZoneInfo("Atlantic/Canary")


def instant(hour=5):
    return CurrentSystemDate(datetime(2026, 8, 5, hour, tzinfo=TZ))


def opened(version=0):
    return OpenSchedulingRun(RunId("RUN-000001"), instant(), False, version)


def completed(*, state=RunState.SUCCESS, warnings=(), errors=(), version=1):
    return CompletedSchedulingRun(
        run_id=RunId("RUN-000001"),
        started_at=instant(),
        completed_at=instant(6),
        simulation=False,
        state=state,
        programmi_letti=3,
        righe_valutate=4,
        occorrenze_valutate=5,
        ordini_generati=2,
        elementi_saltati=1,
        warnings=warnings,
        errors=errors,
        version=version,
    )


class PostgreSQLRunProtocolDouble:
    """Double transazionale unitario; non simula PostgreSQL reale."""

    def __init__(self):
        self.run = None
        self.messages = []
        self.connections = []
        self.fail_on = None
        self.fail_commit = False
        self.fail_rollback = False
        self.fail_close = False
        self.returning_override = None
        self.force_rowcount = None

    def connect(self):
        connection = Connection(self)
        self.connections.append(connection)
        return connection


class Factory:
    def __init__(self, database):
        self.database = database
        self.calls = 0

    def connect(self):
        self.calls += 1
        return self.database.connect()


class Connection:
    def __init__(self, database):
        self.database = database
        self.queries = []
        self.pending_run = None
        self.pending_messages = []
        self.commits = 0
        self.rollbacks = 0
        self.close_calls = 0

    def cursor(self):
        return Cursor(self)

    def commit(self):
        if self.database.fail_commit:
            raise psycopg.DatabaseError("commit password")
        if self.pending_run is not None:
            self.database.run = self.pending_run
        self.database.messages.extend(self.pending_messages)
        self.commits += 1

    def rollback(self):
        self.pending_run = None
        self.pending_messages = []
        self.rollbacks += 1
        if self.database.fail_rollback:
            raise RuntimeError("rollback secret")

    def close(self):
        self.close_calls += 1
        if self.database.fail_close:
            raise RuntimeError("close secret")


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.result = None
        self.rowcount = -1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params):
        sql = " ".join(query.split())
        self.connection.queries.append((sql, params))
        operation = _operation(sql)
        database = self.connection.database
        if database.fail_on == operation:
            if operation == "OPEN" and database.run is not None:
                raise psycopg.errors.UniqueViolation("duplicate password")
            raise psycopg.DatabaseError("driver password")
        if operation == "OPEN":
            if database.run is not None:
                raise psycopg.errors.UniqueViolation("duplicate password")
            public_id, started_at, simulation, version, _ = params
            row = (public_id, started_at, None, simulation, None, 0, 0, 0, 0, 0, version)
            self.connection.pending_run = (1,) + row
            self.result = database.returning_override or row
            self.rowcount = database.force_rowcount if database.force_rowcount is not None else 1
        elif operation == "GET":
            self.result = _get_row(database, params[0])
            self.rowcount = int(self.result is not None)
        elif operation == "COMPLETE":
            current = database.run
            matches = (
                current is not None
                and current[1] == params[7]
                and current[11] == params[8]
                and current[3] is None
                and current[5] is None
            )
            self.rowcount = database.force_rowcount if database.force_rowcount is not None else int(matches)
            if matches and self.rowcount > 0:
                row = (
                    current[0], current[1], current[2], params[0], current[4], params[1],
                    params[2], params[3], params[4], params[5], params[6], current[11] + 1,
                )
                self.result = database.returning_override or row
                if self.rowcount == 1:
                    self.connection.pending_run = row
            else:
                self.result = None
        else:
            warning_id, warnings, error_id, errors = params
            self.connection.pending_messages = (
                [(warning_id, "WARNING", position, message) for position, message in enumerate(warnings, 1)]
                + [(error_id, "ERROR", position, message) for position, message in enumerate(errors, 1)]
            )
            self.rowcount = len(warnings) + len(errors)

    def fetchone(self):
        return self.result


def _operation(sql):
    if sql.startswith("INSERT INTO tpo.runs"):
        return "OPEN"
    if sql.startswith("SELECT r.public_id"):
        return "GET"
    if sql.startswith("UPDATE tpo.runs"):
        return "COMPLETE"
    return "MESSAGES"


def _get_row(database, public_id):
    row = database.run
    if row is None or row[1] != public_id:
        return None
    warnings = [item[3] for item in database.messages if item[1] == "WARNING"]
    errors = [item[3] for item in database.messages if item[1] == "ERROR"]
    return row[1:] + (warnings, errors)


@pytest.fixture
def database():
    return PostgreSQLRunProtocolDouble()


@pytest.fixture
def factory(database):
    return Factory(database)


@pytest.fixture
def repository(factory):
    return PostgreSQLSchedulingRunRepository(factory, created_by=" test-suite ")


def test_apertura_una_insert_returning_commit_close(repository, database, factory):
    repository.add_open_run(opened())
    connection = database.connections[0]
    assert factory.calls == 1
    assert len(connection.queries) == 1
    query, params = connection.queries[0]
    assert query.startswith("INSERT INTO tpo.runs") and "RETURNING" in query
    assert params[-1] == "test-suite"
    assert connection.commits == 1 and connection.rollbacks == 0
    assert connection.close_calls == 1


def test_apertura_returning_incoerente_rollback(repository, database):
    database.returning_override = ("RUN-999999", instant().datetime, None, False, None, 0, 0, 0, 0, 0, 0)
    with pytest.raises(PostgreSQLError, match="non è coerente"):
        repository.add_open_run(opened())
    assert database.connections[0].rollbacks == 1


def test_public_id_duplicato_applicativo_con_causa(repository, database, factory):
    repository.add_open_run(opened())
    with pytest.raises(SchedulingRunAlreadyExistsError) as captured:
        repository.add_open_run(opened())
    assert isinstance(captured.value.__cause__, psycopg.errors.UniqueViolation)
    assert factory.calls == 2


def test_lettura_aperta_una_select_read_only_e_mapping(repository, database):
    repository.add_open_run(opened())
    result = repository.get(RunId("RUN-000001"))
    connection = database.connections[1]
    assert result == opened()
    assert len(connection.queries) == 1
    assert connection.queries[0][0].startswith("SELECT")
    assert "UPDATE" not in connection.queries[0][0] and "FOR UPDATE" not in connection.queries[0][0]
    assert connection.commits == 0 and connection.rollbacks == 1
    assert connection.close_calls == 1


def test_lettura_not_found(repository):
    with pytest.raises(SchedulingRunNotFoundError):
        repository.get(RunId("RUN-000001"))


@pytest.mark.parametrize(
    ("state", "warnings", "errors"),
    (
        (RunState.SUCCESS, (), ()),
        (RunState.SUCCESS_WITH_WARNINGS, ("w1", "w1"), ()),
        (RunState.FAILED, ("w",), ("e1", "e2")),
    ),
)
def test_completamento_stati_messaggi_ordinati_e_mapping(
    repository, database, state, warnings, errors
):
    repository.add_open_run(opened())
    target = completed(state=state, warnings=warnings, errors=errors)
    assert repository.complete(run_id=target.run_id, expected_version=0, completed_run=target)
    connection = database.connections[1]
    assert connection.queries[0][0].startswith("UPDATE tpo.runs")
    assert "version = %s" in connection.queries[0][0]
    assert "completed_at IS NULL" in connection.queries[0][0]
    assert "state IS NULL" in connection.queries[0][0]
    assert "RETURNING" in connection.queries[0][0]
    assert sum(query.startswith("UPDATE") for query, _ in connection.queries) == 1
    assert connection.commits == 1 and connection.rollbacks == 0
    expected_messages = (
        [(1, "WARNING", position, message) for position, message in enumerate(warnings, 1)]
        + [(1, "ERROR", position, message) for position, message in enumerate(errors, 1)]
    )
    assert database.messages == expected_messages
    assert repository.get(target.run_id) == target


def test_completamento_conflitto_zero_righe_senza_seconda_update(repository, database):
    repository.add_open_run(opened())
    database.force_rowcount = 0
    with pytest.raises(SchedulingRunConflictError):
        repository.complete(run_id=RunId("RUN-000001"), expected_version=0, completed_run=completed())
    connection = database.connections[1]
    assert len(connection.queries) == 1
    assert connection.rollbacks == 1 and connection.commits == 0


def test_completamento_returning_incoerente_rollback(repository, database):
    repository.add_open_run(opened())
    database.returning_override = (1, "RUN-000001", instant().datetime, instant(6).datetime, False, "SUCCESS", 3, 4, 5, 2, 1, 99)
    with pytest.raises(PostgreSQLError, match="non è coerente"):
        repository.complete(run_id=RunId("RUN-000001"), expected_version=0, completed_run=completed())
    assert database.connections[1].rollbacks == 1
    assert database.messages == []


@pytest.mark.parametrize(
    "arguments",
    (
        {"run_id": "RUN-000001"},
        {"expected_version": -1},
        {"expected_version": True},
        {"completed_run": opened()},
        {"completed_run": completed(version=2)},
    ),
)
def test_input_completamento_invalido_prima_connessione(repository, factory, arguments):
    values = {"run_id": RunId("RUN-000001"), "expected_version": 0, "completed_run": completed()}
    values.update(arguments)
    with pytest.raises(InvalidSchedulingRunError):
        repository.complete(**values)
    assert factory.calls == 0


@pytest.mark.parametrize("operation", ("OPEN", "GET", "COMPLETE", "MESSAGES"))
def test_errori_psycopg_convertiti_causa_nessun_retry_password(
    repository, database, factory, operation
):
    if operation in ("GET", "COMPLETE", "MESSAGES"):
        repository.add_open_run(opened())
    database.fail_on = operation
    if operation == "OPEN":
        action = lambda: repository.add_open_run(opened())
    elif operation == "GET":
        action = lambda: repository.get(RunId("RUN-000001"))
    else:
        target = completed(state=RunState.FAILED, errors=("e",)) if operation == "MESSAGES" else completed()
        action = lambda: repository.complete(
            run_id=RunId("RUN-000001"), expected_version=0, completed_run=target
        )
    calls_before = factory.calls
    with pytest.raises(PostgreSQLError) as captured:
        action()
    assert isinstance(captured.value.__cause__, psycopg.DatabaseError)
    assert "password" not in str(captured.value)
    assert factory.calls == calls_before + 1


def test_cleanup_commit_fallito_tenta_rollback_e_close(repository, database):
    database.fail_commit = True
    with pytest.raises(PostgreSQLError) as captured:
        repository.add_open_run(opened())
    connection = database.connections[0]
    assert isinstance(captured.value.__cause__, psycopg.DatabaseError)
    assert connection.rollbacks == 1 and connection.close_calls == 1


def test_cleanup_rollback_fallito_non_impedisce_close(repository, database):
    database.fail_on = "GET"
    database.fail_rollback = True
    database.fail_close = True
    with pytest.raises(PostgreSQLError):
        repository.get(RunId("RUN-000001"))
    assert database.connections[0].close_calls == 1
