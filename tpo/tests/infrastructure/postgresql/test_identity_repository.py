from __future__ import annotations

from dataclasses import dataclass
from threading import Barrier, Lock, Thread

import psycopg
import pytest

from src.tpo_core.application.identity import (
    IdentifierSequenceConflictError,
    IdentifierSequenceNotFoundError,
    InvalidIdentifierSequenceError,
    PersistentIdAllocator,
)
from src.tpo_core.domain.identifiers import OrdineId, PermanentId, RunId
from src.tpo_core.infrastructure.postgresql.errors import PostgreSQLError
from src.tpo_core.infrastructure.postgresql.identity_repository import (
    PostgreSQLPersistentIdRepository,
)


@dataclass
class Row:
    identifier_type: str
    prefix: str
    next_value: int
    version: int


class PostgreSQLProtocolDouble:
    """Double unitario del protocollo, non simula PostgreSQL reale."""

    def __init__(self) -> None:
        self.rows = {
            "OrdineId": Row("OrdineId", "ORD", 1, 0),
            "RunId": Row("RunId", "RUN", 1, 0),
        }
        self.lock = Lock()
        self.connections = []
        self.fail_on = None
        self.force_rowcount = None
        self.returning_override = None
        self.fail_commit = False
        self.fail_rollback = False
        self.fail_close = False

    def connect(self):
        connection = Connection(self)
        self.connections.append(connection)
        return connection


class Factory:
    def __init__(self, database: PostgreSQLProtocolDouble) -> None:
        self.database = database
        self.calls = 0

    def connect(self):
        self.calls += 1
        return self.database.connect()


class Connection:
    def __init__(self, database: PostgreSQLProtocolDouble) -> None:
        self.database = database
        self.queries = []
        self.pending = None
        self.commits = 0
        self.rollbacks = 0
        self.close_calls = 0
        self.closed = False
        self._locked = False

    def cursor(self):
        return Cursor(self)

    def commit(self):
        if self.database.fail_commit:
            raise psycopg.DatabaseError("commit password")
        if self.pending is not None:
            name, value, version = self.pending
            row = self.database.rows[name]
            row.next_value = value
            row.version = version
        self.pending = None
        self.commits += 1
        self._unlock()

    def rollback(self):
        self.pending = None
        self.rollbacks += 1
        self._unlock()
        if self.database.fail_rollback:
            raise RuntimeError("cleanup secret")

    def close(self):
        self.close_calls += 1
        self.closed = True
        self._unlock()
        if self.database.fail_close:
            raise RuntimeError("cleanup secret")

    def _unlock(self):
        if self._locked:
            self._locked = False
            self.database.lock.release()


class Cursor:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self.result = None
        self.rowcount = -1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params):
        normalized = " ".join(query.split())
        self.connection.queries.append((normalized, params))
        database = self.connection.database
        operation = "UPDATE" if normalized.startswith("UPDATE") else "SELECT"
        if database.fail_on == operation:
            raise psycopg.DatabaseError("driver password")
        if operation == "SELECT":
            row = database.rows.get(params[0])
            self.result = _row_tuple(row)
            return

        database.lock.acquire()
        self.connection._locked = True
        new_value, _, name, prefix, version, next_value = params
        row = database.rows.get(name)
        matches = (
            row is not None
            and row.prefix == prefix
            and row.version == version
            and row.next_value == next_value
        )
        self.rowcount = database.force_rowcount if database.force_rowcount is not None else int(matches)
        self.result = None
        if matches and self.rowcount > 0:
            self.result = database.returning_override or (
                name,
                prefix,
                new_value,
                version + 1,
            )
            if self.rowcount == 1:
                self.connection.pending = (name, new_value, version + 1)

    def fetchone(self):
        return self.result


def _row_tuple(row):
    if row is None:
        return None
    return row.identifier_type, row.prefix, row.next_value, row.version


@pytest.fixture
def database():
    return PostgreSQLProtocolDouble()


@pytest.fixture
def factory(database):
    return Factory(database)


@pytest.fixture
def repository(factory):
    return PostgreSQLPersistentIdRepository(factory, updated_by="test-suite")


def test_get_sequence_una_select_senza_update_for_update_o_commit(repository, database):
    sequence = repository.get_sequence(OrdineId)
    assert (sequence.next_value, sequence.version) == (1, 0)
    connection = database.connections[0]
    assert len(connection.queries) == 1
    assert connection.queries[0][0].startswith("SELECT")
    assert "UPDATE" not in connection.queries[0][0]
    assert "FOR UPDATE" not in connection.queries[0][0]
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed
    assert connection.close_calls == 1


def test_get_sequence_assente_propaga_not_found_e_rollback(repository, database):
    class MissingId(OrdineId):
        prefix = "MIS"

    with pytest.raises(IdentifierSequenceNotFoundError):
        repository.get_sequence(MissingId)
    assert database.connections[0].rollbacks == 1


def test_compare_and_set_una_update_returning_senza_select_e_commit(repository, database):
    assert repository.compare_and_set(
        identifier_type=OrdineId,
        expected_version=0,
        expected_next_value=1,
        new_next_value=2,
    )
    connection = database.connections[0]
    assert len(connection.queries) == 1
    query, params = connection.queries[0]
    assert query.startswith("UPDATE tpo.id_sequences")
    assert "SELECT" not in query
    assert "FOR UPDATE" not in query
    assert "RETURNING identifier_type, prefix, next_value, version" in query
    assert all(field in query for field in ("identifier_type", "prefix", "version", "next_value"))
    assert params == (2, "test-suite", "OrdineId", "ORD", 0, 1)
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closed
    assert connection.close_calls == 1


@pytest.mark.parametrize(
    "returned",
    (
        ("RunId", "ORD", 2, 1),
        ("OrdineId", "BAD", 2, 1),
        ("OrdineId", "ORD", 3, 1),
        ("OrdineId", "ORD", 2, 2),
    ),
)
def test_returning_incoerente_rollback_senza_commit_o_seconda_query(
    repository, database, returned
):
    database.returning_override = returned
    with pytest.raises(PostgreSQLError, match="non è coerente"):
        repository.compare_and_set(
            identifier_type=OrdineId,
            expected_version=0,
            expected_next_value=1,
            new_next_value=2,
        )
    connection = database.connections[0]
    assert len(connection.queries) == 1
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.close_calls == 1


@pytest.mark.parametrize(
    "values",
    (
        {"expected_version": -1},
        {"expected_version": True},
        {"expected_next_value": 0},
        {"expected_next_value": True},
        {"new_next_value": 3},
        {"identifier_type": PermanentId},
        {"identifier_type": object},
    ),
)
def test_input_cas_non_valido_non_apre_connessioni(repository, factory, values):
    arguments = {
        "identifier_type": OrdineId,
        "expected_version": 0,
        "expected_next_value": 1,
        "new_next_value": 2,
    }
    arguments.update(values)
    with pytest.raises(InvalidIdentifierSequenceError):
        repository.compare_and_set(**arguments)
    assert factory.calls == 0


@pytest.mark.parametrize(
    ("expected_version", "expected_next_value", "new_next_value"),
    ((99, 1, 2), (0, 99, 100)),
)
def test_cas_errato_solleva_conflitto_e_rollback(
    repository, database, expected_version, expected_next_value, new_next_value
):
    with pytest.raises(IdentifierSequenceConflictError):
        repository.compare_and_set(
            identifier_type=OrdineId,
            expected_version=expected_version,
            expected_next_value=expected_next_value,
            new_next_value=new_next_value,
        )
    connection = database.connections[0]
    assert len(connection.queries) == 1
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_zero_righe_e_conflitto_senza_secondo_tentativo(repository, database, factory):
    database.force_rowcount = 0
    with pytest.raises(IdentifierSequenceConflictError):
        repository.compare_and_set(
            identifier_type=OrdineId,
            expected_version=0,
            expected_next_value=1,
            new_next_value=2,
        )
    assert factory.calls == 1
    assert len(database.connections[0].queries) == 1


def test_piu_di_una_riga_e_errore_infrastrutturale(repository, database):
    database.force_rowcount = 2
    with pytest.raises(PostgreSQLError, match="numero inatteso"):
        repository.compare_and_set(
            identifier_type=OrdineId,
            expected_version=0,
            expected_next_value=1,
            new_next_value=2,
        )
    assert database.connections[0].rollbacks == 1


@pytest.mark.parametrize("operation", ("SELECT", "UPDATE"))
def test_errore_postgresql_convertito_con_causa_senza_retry_o_password(
    repository, database, factory, operation
):
    database.fail_on = operation
    if operation == "SELECT":
        action = lambda: repository.get_sequence(OrdineId)
    else:
        action = lambda: repository.compare_and_set(
            identifier_type=OrdineId,
            expected_version=0,
            expected_next_value=1,
            new_next_value=2,
        )
    with pytest.raises(PostgreSQLError) as captured:
        action()
    assert isinstance(captured.value.__cause__, psycopg.DatabaseError)
    assert "password" not in str(captured.value)
    assert factory.calls == 1


def test_errore_non_postgresql_propagato_invariato(repository, database):
    database.rows["OrdineId"].next_value = "invalid"
    with pytest.raises(InvalidIdentifierSequenceError) as captured:
        repository.get_sequence(OrdineId)
    assert captured.value.__cause__ is None


def test_cleanup_non_sostituisce_errore_principale(repository, database):
    database.fail_on = "UPDATE"
    database.fail_rollback = True
    database.fail_close = True
    with pytest.raises(PostgreSQLError) as captured:
        repository.compare_and_set(
            identifier_type=OrdineId,
            expected_version=0,
            expected_next_value=1,
            new_next_value=2,
        )
    assert isinstance(captured.value.__cause__, psycopg.DatabaseError)
    assert database.connections[0].closed


def test_rollback_fallisce_ma_close_avviene(repository, database):
    database.force_rowcount = 0
    database.fail_rollback = True
    with pytest.raises(IdentifierSequenceConflictError):
        repository.compare_and_set(
            identifier_type=OrdineId,
            expected_version=0,
            expected_next_value=1,
            new_next_value=2,
        )
    assert database.connections[0].close_calls == 1


def test_commit_fallisce_rollback_e_close_preservando_causa(repository, database):
    database.fail_commit = True
    with pytest.raises(PostgreSQLError) as captured:
        repository.compare_and_set(
            identifier_type=OrdineId,
            expected_version=0,
            expected_next_value=1,
            new_next_value=2,
        )
    connection = database.connections[0]
    assert isinstance(captured.value.__cause__, psycopg.DatabaseError)
    assert "password" not in str(captured.value)
    assert connection.rollbacks == 1
    assert connection.close_calls == 1


def test_id_non_riutilizzati_e_sequenze_indipendenti(repository):
    allocator = PersistentIdAllocator(repository)
    assert allocator.next_id(OrdineId) == OrdineId("ORD-000001")
    assert allocator.next_id(OrdineId) == OrdineId("ORD-000002")
    assert allocator.next_id(RunId) == RunId("RUN-000001")


def test_protocollo_optimistic_simulato_un_successo_e_un_conflitto(database):
    first = PostgreSQLPersistentIdRepository(Factory(database))
    second = PostgreSQLPersistentIdRepository(Factory(database))
    snapshots = [first.get_sequence(OrdineId), second.get_sequence(OrdineId)]
    barrier = Barrier(2)
    outcomes = []

    def advance(repository, snapshot):
        barrier.wait()
        try:
            repository.compare_and_set(
                identifier_type=OrdineId,
                expected_version=snapshot.version,
                expected_next_value=snapshot.next_value,
                new_next_value=snapshot.next_value + 1,
            )
            outcomes.append("success")
        except IdentifierSequenceConflictError:
            outcomes.append("conflict")

    threads = [Thread(target=advance, args=pair) for pair in zip((first, second), snapshots)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    assert sorted(outcomes) == ["conflict", "success"]
    assert (database.rows["OrdineId"].next_value, database.rows["OrdineId"].version) == (2, 1)
