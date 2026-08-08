"""Test PostgreSQL reale, disattivato senza configurazione esplicita."""

import os
from urllib.parse import urlparse

from alembic import command
import psycopg
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

from src.tpo_core.infrastructure.postgresql.alembic import make_config
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


def _sqlalchemy_psycopg_url(url: str):
    parsed = make_url(url)
    if parsed.drivername == "postgresql":
        return parsed.set(drivername="postgresql+psycopg")
    if parsed.drivername == "postgresql+psycopg":
        return parsed
    pytest.fail("TPO_TEST_DATABASE_URL usa un dialect PostgreSQL non autorizzato.")


def test_orders_repository_read_only_postgresql_reale():
    database_name = urlparse(DATABASE_URL).path.lstrip("/").split("?", 1)[0]
    if "test" not in database_name.lower():
        pytest.fail("TPO_TEST_DATABASE_URL deve indicare un database dedicato ai test.")

    engine = sa.create_engine(_sqlalchemy_psycopg_url(DATABASE_URL))
    migrated = False
    try:
        with engine.connect() as connection:
            if sa.inspect(connection).has_schema("tpo"):
                pytest.fail("Lo schema tpo esiste già: è richiesto un database di test vuoto.")
            command.upgrade(make_config(connection=connection), "head")
            connection.commit()
            migrated = True

        repository = PostgreSQLOrdineRepository(URLConnectionFactory())
        assert repository.list_scheduled_orders() == ()
        assert repository.has_idempotency_key(
            "__tpo_missing_integration_key__"
        ) is False
    finally:
        if migrated:
            with engine.connect() as connection:
                command.downgrade(make_config(connection=connection), "base")
                connection.commit()
        engine.dispose()
