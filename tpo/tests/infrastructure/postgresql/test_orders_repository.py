from datetime import date
from decimal import Decimal

import psycopg
import pytest

from src.tpo_core.application.scheduling.models import ScheduledOrderRecord
from src.tpo_core.domain.entities.ordine import Ordine, RigaOrdine
from src.tpo_core.domain.identifiers import (
    ClienteId,
    OrdineId,
    ProgrammaFornituraId,
    VarietaId,
)
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import OrdineState
from src.tpo_core.infrastructure.postgresql.errors import PostgreSQLError
from src.tpo_core.infrastructure.postgresql.orders_repository import PostgreSQLOrdineRepository


def record(identifier="ORD-000001", key="key-1"):
    return ScheduledOrderRecord(
        ordine=Ordine(
            id=OrdineId(identifier),
            cliente_id=ClienteId("CLI-000001"),
            data_ordine=date(2026, 8, 5),
            righe=(RigaOrdine(VarietaId("VAR-000001"), Quantity(Decimal("2.5"), UnitOfMeasure.GRAM)),),
            stato=OrdineState.APERTO,
            programma_fornitura_id=ProgrammaFornituraId("PF-000001"),
        ),
        data_consegna_prevista=date(2026, 8, 6),
        chiave_idempotenza=key,
    )


class Factory:
    def __init__(self):
        self.connections = []
        self.rows = []
        self.fail = None

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
        self.result = None
        self.results = []
        self.rowcount = -1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        sql = " ".join(query.split())
        self.connection.queries.append((sql, params))
        factory = self.connection.factory
        if factory.fail:
            raise factory.fail
        if sql.startswith("SELECT EXISTS"):
            self.result = (any(row[6] == params[0] for row in factory.rows),)
        elif sql.startswith("SELECT o.public_id"):
            self.results = factory.rows
            if "WHERE o.public_id" in sql:
                self.results = [row for row in self.results if row[0] == params[0]]
        elif sql.startswith("INSERT INTO tpo.ordini"):
            self.result = (1, params[0], params[1], params[2], params[3], params[4])
            self.rowcount = 1
        else:
            self.result = (params[1], params[2], params[3])
            self.rowcount = 1

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.results


@pytest.fixture
def factory():
    return Factory()


@pytest.fixture
def repository(factory):
    return PostgreSQLOrdineRepository(factory)


def test_lettura_una_select_read_only_mapping(repository, factory):
    item = record()
    factory.rows = [("ORD-000001", "CLI-000001", date(2026, 8, 5), "APERTO", "PF-000001", date(2026, 8, 6), "key-1", 1, "VAR-000001", Decimal("2.5"), "GRAM")]
    assert repository.list_scheduled_orders() == (item,)
    connection = factory.connections[0]
    assert len(connection.queries) == 1
    assert connection.queries[0][0].startswith("SELECT")
    assert "UPDATE" not in connection.queries[0][0] and "FOR UPDATE" not in connection.queries[0][0]
    assert connection.rollbacks == 1 and connection.commits == 0 and connection.closes == 1


def test_lookup_public_id_not_found(repository):
    assert repository.get_by_public_id(OrdineId("ORD-000001")) is None


def test_verifica_chiave_idempotente_una_select(repository, factory):
    assert repository.has_idempotency_key("key") is False
    assert len(factory.connections[0].queries) == 1


def test_errore_psycopg_convertito_senza_retry(repository, factory):
    factory.fail = psycopg.DatabaseError("password")
    with pytest.raises(PostgreSQLError) as captured:
        repository.list_scheduled_orders()
    assert isinstance(captured.value.__cause__, psycopg.DatabaseError)
    assert "password" not in str(captured.value)
    assert len(factory.connections) == 1


def test_repository_postgresql_non_espone_writer(repository):
    assert not hasattr(repository, "add_scheduled_orders")


def test_tutte_le_query_sono_read_only(repository, factory):
    repository.list_scheduled_orders()
    repository.get_by_public_id(OrdineId("ORD-000001"))
    repository.has_idempotency_key("key")
    queries = [query for connection in factory.connections for query, _ in connection.queries]
    assert queries
    assert all(query.startswith("SELECT") for query in queries)
    assert all(connection.commits == 0 for connection in factory.connections)
    assert all(connection.rollbacks == 1 for connection in factory.connections)
