"""Test PostgreSQL reale, disattivato senza configurazione esplicita."""

import os

import psycopg
import pytest

from src.tpo_core.infrastructure.postgresql.orders_repository import PostgreSQLOrdineRepository


DATABASE_URL = os.environ.get("TPO_TEST_DATABASE_URL")


pytestmark = [
    pytest.mark.postgresql_integration,
    pytest.mark.skipif(
        not DATABASE_URL,
        reason="TPO_TEST_DATABASE_URL non configurata: PostgreSQL reale non eseguito.",
    ),
]


class URLConnectionFactory:
    def connect(self):
        return psycopg.connect(DATABASE_URL)


def test_orders_repository_read_only_postgresql_reale():
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            assert "test" in cursor.fetchone()[0].lower()
    repository = PostgreSQLOrdineRepository(URLConnectionFactory())
    assert isinstance(repository.list_scheduled_orders(), tuple)
    assert repository.has_idempotency_key("__tpo_missing_integration_key__") is False
