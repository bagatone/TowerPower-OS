import psycopg
import pytest

from src.tpo_core.application.write_plan import WRITE_TARGET_ORDINI, WriteTargetMismatchError
from src.tpo_core.infrastructure.postgresql.errors import PostgreSQLError
from src.tpo_core.infrastructure.postgresql.write_plan_validation_repository import (
    PostgreSQLWritePlanValidationRepository,
)


class Factory:
    def __init__(self, rows=(), error=None):
        self.rows = list(rows)
        self.error = error
        self.connections = []

    def connect(self):
        connection = Connection(self)
        self.connections.append(connection)
        return connection


class Connection:
    def __init__(self, factory):
        self.factory = factory
        self.queries = []
        self.commits = self.rollbacks = self.closes = 0

    def cursor(self):
        return Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


class Cursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        self.connection.queries.append((" ".join(query.split()), params))
        if self.connection.factory.error:
            raise self.connection.factory.error

    def fetchall(self):
        return self.connection.factory.rows


def test_snapshot_read_only_completo_e_lazy() -> None:
    factory = Factory((("a",), ("b",)))
    repository = PostgreSQLWritePlanValidationRepository(factory)
    assert factory.connections == []
    snapshot = repository.get_target_snapshot(target_name=WRITE_TARGET_ORDINI)
    assert snapshot.target_name == "ORDINI"
    assert snapshot.schema_name == "ORDINI"
    assert snapshot.schema_version == "1.0"
    assert snapshot.existing_idempotency_keys == ("a", "b")
    connection = factory.connections[0]
    assert connection.queries[0][0].startswith("SELECT")
    assert connection.queries[0][1] == ()
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closes == 1


def test_target_diverso_rifiutato_senza_connessione() -> None:
    factory = Factory()
    repository = PostgreSQLWritePlanValidationRepository(factory)
    with pytest.raises(WriteTargetMismatchError):
        repository.get_target_snapshot(target_name="ALTRO")
    assert factory.connections == []


def test_errore_database_convertito_senza_retry() -> None:
    factory = Factory(error=psycopg.DatabaseError("secret"))
    repository = PostgreSQLWritePlanValidationRepository(factory)
    with pytest.raises(PostgreSQLError) as captured:
        repository.get_target_snapshot(target_name=WRITE_TARGET_ORDINI)
    assert "secret" not in str(captured.value)
    assert len(factory.connections) == 1
