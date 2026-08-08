from datetime import date, time
from decimal import Decimal

import psycopg
import pytest

from src.tpo_core.domain.entities.programma_fornitura import TipoRicorrenza
from src.tpo_core.domain.quantities import UnitOfMeasure
from src.tpo_core.domain.states import ProgrammaFornituraState
from src.tpo_core.infrastructure.postgresql.errors import PostgreSQLError
from src.tpo_core.infrastructure.postgresql.programmi_repository import (
    PostgreSQLVersionedProgrammaFornituraRepository,
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


def row(position=1, recurrence="SETTIMANALE", interval=None, days=()):
    return (
        "PF-000001", "CLI-000001", 3, "ATTIVO", date(2026, 8, 1), None,
        time(5), 14, position, f"VAR-{position:06d}", Decimal("2.5"), "SET",
        recurrence, interval, list(days),
    )


def test_mapping_versione_righe_posizioni_e_giorni_read_only() -> None:
    factory = Factory((row(), row(2, "GIORNI_SETTIMANA", days=(1, 5))))
    repository = PostgreSQLVersionedProgrammaFornituraRepository(factory)
    assert factory.connections == []
    programs = repository.list_versioned_for_scheduling()
    assert len(programs) == 1
    snapshot = programs[0]
    assert snapshot.version == 3
    assert snapshot.programma.stato is ProgrammaFornituraState.ATTIVO
    assert tuple(item.position for item in snapshot.lines) == (1, 2)
    assert snapshot.lines[0].line.quantita.unit is UnitOfMeasure.SET
    assert snapshot.lines[0].line.configurazione_temporale.tipo is TipoRicorrenza.SETTIMANALE
    assert snapshot.lines[1].line.configurazione_temporale.giorni_settimana == (1, 5)
    connection = factory.connections[0]
    query, params = connection.queries[0]
    assert query.startswith("SELECT") and "WHERE pv.valida_al IS NULL" in query
    assert params == ()
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closes == 1


def test_nessun_programma_restituisce_tuple_vuota() -> None:
    repository = PostgreSQLVersionedProgrammaFornituraRepository(Factory())
    assert repository.list_versioned_for_scheduling() == ()


def test_errore_database_convertito_senza_retry() -> None:
    factory = Factory(error=psycopg.DatabaseError("secret"))
    repository = PostgreSQLVersionedProgrammaFornituraRepository(factory)
    with pytest.raises(PostgreSQLError) as captured:
        repository.list_versioned_for_scheduling()
    assert "secret" not in str(captured.value)
    assert len(factory.connections) == 1
