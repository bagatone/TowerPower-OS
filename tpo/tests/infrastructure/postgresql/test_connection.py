from __future__ import annotations

import pytest
import psycopg

from src.tpo_core.infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from src.tpo_core.infrastructure.postgresql.errors import PostgreSQLConnectionError
from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings


def settings() -> PostgreSQLSettings:
    return PostgreSQLSettings("db", 5432, "towerpower", "app", "secret", "require", 3)


def test_costruttore_non_connette_e_connect_usa_parametri_corretti() -> None:
    calls = []
    connections = [object(), object()]

    def connector(**kwargs):
        calls.append(kwargs)
        return connections[len(calls) - 1]

    factory = PostgreSQLConnectionFactory(settings(), connector=connector)
    assert calls == []
    assert factory.connect() is connections[0]
    assert factory.connect() is connections[1]
    assert calls == [
        {
            "host": "db",
            "port": 5432,
            "dbname": "towerpower",
            "user": "app",
            "password": "secret",
            "sslmode": "require",
            "connect_timeout": 3,
        },
        {
            "host": "db",
            "port": 5432,
            "dbname": "towerpower",
            "user": "app",
            "password": "secret",
            "sslmode": "require",
            "connect_timeout": 3,
        },
    ]
    assert all("autocommit" not in call for call in calls)


def test_errore_convertito_senza_retry_con_causa() -> None:
    cause = psycopg.OperationalError("driver details")
    calls = 0

    def connector(**kwargs):
        nonlocal calls
        calls += 1
        raise cause

    factory = PostgreSQLConnectionFactory(settings(), connector=connector)
    with pytest.raises(PostgreSQLConnectionError) as captured:
        factory.connect()
    assert calls == 1
    assert captured.value.__cause__ is cause
    assert "secret" not in str(captured.value)


def test_errore_non_psycopg_non_viene_mascherato() -> None:
    calls = 0

    def connector(**kwargs):
        nonlocal calls
        calls += 1
        raise TypeError("programming error")

    factory = PostgreSQLConnectionFactory(settings(), connector=connector)
    with pytest.raises(TypeError, match="programming error"):
        factory.connect()
    assert calls == 1
