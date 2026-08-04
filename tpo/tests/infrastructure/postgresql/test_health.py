from __future__ import annotations

import psycopg

from src.tpo_core.infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from src.tpo_core.infrastructure.postgresql.health import PostgreSQLHealthCheck
from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings


class FakeCursor:
    def __init__(self, *, fail: bool = False, fail_close: bool = False) -> None:
        self.queries = []
        self.closed = False
        self.fail = fail
        self.fail_close = fail_close

    def execute(self, query: str) -> None:
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("secret must not escape")

    def fetchone(self):
        return (1,)

    def close(self) -> None:
        self.closed = True
        if self.fail_close:
            raise RuntimeError("sensitive cursor cleanup detail")


class FakeConnection:
    class Info:
        server_version = 170002

    info = Info()

    def __init__(
        self,
        *,
        fail: bool = False,
        fail_cursor_close: bool = False,
        fail_rollback: bool = False,
        fail_close: bool = False,
    ) -> None:
        self.fake_cursor = FakeCursor(fail=fail, fail_close=fail_cursor_close)
        self.rolled_back = False
        self.closed = False
        self.fail_rollback = fail_rollback
        self.fail_close = fail_close

    def cursor(self):
        return self.fake_cursor

    def rollback(self) -> None:
        self.rolled_back = True
        if self.fail_rollback:
            raise RuntimeError("sensitive rollback detail")

    def close(self) -> None:
        self.closed = True
        if self.fail_close:
            raise RuntimeError("sensitive connection cleanup detail")


def factory(connection=None, connector=None):
    config = PostgreSQLSettings("db", 5432, "towerpower", "app", "secret", "require", 3)
    return PostgreSQLConnectionFactory(
        config,
        connector=connector or (lambda **kwargs: connection),
    )


def test_select_one_risultato_e_chiusura() -> None:
    connection = FakeConnection()
    result = PostgreSQLHealthCheck(factory(connection)).check()
    assert result.ok is True
    assert result.database_name == "towerpower"
    assert result.server_version == "170002"
    assert connection.fake_cursor.queries == ["SELECT 1"]
    assert connection.fake_cursor.closed is True
    assert connection.rolled_back is True
    assert connection.closed is True


def test_errore_health_classificato_sanitizzato_e_chiusura() -> None:
    connection = FakeConnection(fail=True)
    result = PostgreSQLHealthCheck(factory(connection)).check()
    assert result.ok is False
    assert result.error_code == "health_check_error"
    assert "secret" not in result.error_message
    assert connection.fake_cursor.queries == ["SELECT 1"]
    assert connection.fake_cursor.closed is True
    assert connection.rolled_back is True
    assert connection.closed is True


def test_errore_connessione_classificato_senza_retry() -> None:
    calls = 0

    def connector(**kwargs):
        nonlocal calls
        calls += 1
        raise psycopg.OperationalError("secret driver detail")

    result = PostgreSQLHealthCheck(factory(connector=connector)).check()
    assert result.ok is False
    assert result.error_code == "connection_error"
    assert "secret" not in result.error_message
    assert calls == 1


def test_rollback_fallisce_ma_close_viene_eseguito_e_risultato_resta_ok() -> None:
    connection = FakeConnection(fail_rollback=True)
    result = PostgreSQLHealthCheck(factory(connection)).check()
    assert result.ok is True
    assert connection.rolled_back is True
    assert connection.closed is True


def test_cursor_close_fallisce_senza_alterare_risultato_positivo() -> None:
    connection = FakeConnection(fail_cursor_close=True)
    result = PostgreSQLHealthCheck(factory(connection)).check()
    assert result.ok is True
    assert connection.fake_cursor.closed is True
    assert connection.rolled_back is True
    assert connection.closed is True


def test_connection_close_fallisce_senza_alterare_risultato_positivo() -> None:
    connection = FakeConnection(fail_close=True)
    result = PostgreSQLHealthCheck(factory(connection)).check()
    assert result.ok is True
    assert connection.closed is True


def test_cleanup_fallisce_senza_alterare_errore_originale_o_esporre_dettagli() -> None:
    connection = FakeConnection(
        fail=True,
        fail_cursor_close=True,
        fail_rollback=True,
        fail_close=True,
    )
    result = PostgreSQLHealthCheck(factory(connection)).check()
    assert result.ok is False
    assert result.error_code == "health_check_error"
    assert result.error_message == "Health check PostgreSQL fallito."
    assert "secret" not in result.error_message
    assert "sensitive" not in result.error_message
    assert connection.fake_cursor.closed is True
    assert connection.rolled_back is True
    assert connection.closed is True
