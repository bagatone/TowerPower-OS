from __future__ import annotations

import os
from threading import Barrier, Lock, Thread

import psycopg
import pytest

from src.tpo_core.application.identity import IdentifierSequenceConflictError
from src.tpo_core.domain.identifiers import OrdineId
from src.tpo_core.infrastructure.postgresql.identity_repository import (
    PostgreSQLPersistentIdRepository,
)


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


def test_due_cas_concorrenti_su_postgresql_reale() -> None:
    admin = psycopg.connect(DATABASE_URL, autocommit=True)
    schema_created = False
    table_created = False
    try:
        with admin.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            database_name = cursor.fetchone()[0]
            if "test" not in database_name.lower():
                pytest.fail("TPO_TEST_DATABASE_URL deve indicare un database dedicato ai test.")
            cursor.execute("SELECT to_regnamespace('tpo')")
            if cursor.fetchone()[0] is not None:
                pytest.fail("Lo schema tpo esiste già: è richiesto un database di test vuoto.")
            cursor.execute("CREATE SCHEMA tpo")
            schema_created = True
            cursor.execute(
                """
                CREATE TABLE tpo.id_sequences (
                    sequence_name text PRIMARY KEY,
                    identifier_type text NOT NULL UNIQUE,
                    prefix text NOT NULL UNIQUE,
                    next_value bigint NOT NULL CHECK (next_value > 0),
                    version bigint NOT NULL DEFAULT 0 CHECK (version >= 0),
                    updated_at timestamptz NOT NULL,
                    updated_by text NOT NULL
                )
                """
            )
            table_created = True
            cursor.execute(
                """
                INSERT INTO tpo.id_sequences (
                    sequence_name, identifier_type, prefix, next_value,
                    version, updated_at, updated_by
                ) VALUES ('ORDINE_ID', 'OrdineId', 'ORD', 1, 0, CURRENT_TIMESTAMP, 'test-setup')
                """
            )

        repositories = [
            PostgreSQLPersistentIdRepository(URLConnectionFactory(), updated_by="integration-test"),
            PostgreSQLPersistentIdRepository(URLConnectionFactory(), updated_by="integration-test"),
        ]
        snapshots = [repository.get_sequence(OrdineId) for repository in repositories]
        assert snapshots[0] == snapshots[1]

        barrier = Barrier(2)
        outcome_lock = Lock()
        outcomes = []
        thread_errors = []

        def advance(repository, snapshot):
            barrier.wait()
            try:
                repository.compare_and_set(
                    identifier_type=OrdineId,
                    expected_version=snapshot.version,
                    expected_next_value=snapshot.next_value,
                    new_next_value=snapshot.next_value + 1,
                )
                result = ("success", f"{snapshot.prefix}-{snapshot.next_value:06d}")
            except IdentifierSequenceConflictError:
                result = ("conflict", None)
            except BaseException as exc:
                with outcome_lock:
                    thread_errors.append(exc)
                return
            with outcome_lock:
                outcomes.append(result)

        threads = [
            Thread(target=advance, args=(repository, snapshot))
            for repository, snapshot in zip(repositories, snapshots)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert all(not thread.is_alive() for thread in threads), "Un thread CAS non è terminato."
        assert not thread_errors, f"Errori inattesi nei thread CAS: {thread_errors!r}"
        assert sorted(result for result, _ in outcomes) == ["conflict", "success"]
        successful_ids = [identifier for result, identifier in outcomes if result == "success"]
        assert successful_ids == ["ORD-000001"]
        assert len(set(successful_ids)) == 1

        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT next_value, version FROM tpo.id_sequences WHERE identifier_type = 'OrdineId'"
            )
            assert cursor.fetchone() == (2, 1)
    finally:
        if schema_created:
            with admin.cursor() as cursor:
                if table_created:
                    cursor.execute("DROP TABLE tpo.id_sequences")
                cursor.execute("DROP SCHEMA tpo")
        admin.close()
