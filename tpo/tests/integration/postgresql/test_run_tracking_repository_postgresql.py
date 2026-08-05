from __future__ import annotations

from datetime import datetime
import os
from threading import Barrier, Lock, Thread
from zoneinfo import ZoneInfo

import psycopg
import pytest

from src.tpo_core.application.run_tracking import (
    CompletedSchedulingRun,
    OpenSchedulingRun,
    SchedulingRunConflictError,
)
from src.tpo_core.domain.identifiers import RunId
from src.tpo_core.domain.states import RunState
from src.tpo_core.domain.time_reference import CurrentSystemDate
from src.tpo_core.infrastructure.postgresql.run_tracking_repository import (
    PostgreSQLSchedulingRunRepository,
)


DATABASE_URL = os.environ.get("TPO_TEST_DATABASE_URL")
TZ = ZoneInfo("Atlantic/Canary")

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


def test_ciclo_run_e_due_completamenti_concorrenti_postgresql_reale() -> None:
    admin = psycopg.connect(DATABASE_URL, autocommit=True)
    schema_created = False
    objects_created = False
    try:
        with admin.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            if "test" not in cursor.fetchone()[0].lower():
                pytest.fail("TPO_TEST_DATABASE_URL deve indicare un database dedicato ai test.")
            cursor.execute("SELECT to_regnamespace('tpo')")
            if cursor.fetchone()[0] is not None:
                pytest.fail("Lo schema tpo esiste già: è richiesto un database di test vuoto.")
            cursor.execute("CREATE SCHEMA tpo")
            schema_created = True
            cursor.execute("CREATE TYPE tpo.run_state AS ENUM ('SUCCESS', 'SUCCESS_WITH_WARNINGS', 'FAILED')")
            cursor.execute("CREATE TYPE tpo.run_message_type AS ENUM ('WARNING', 'ERROR')")
            cursor.execute(
                """
                CREATE TABLE tpo.runs (
                    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    public_id text NOT NULL UNIQUE,
                    started_at timestamptz NOT NULL,
                    completed_at timestamptz,
                    simulation boolean NOT NULL,
                    state tpo.run_state,
                    programmi_letti bigint NOT NULL DEFAULT 0,
                    righe_valutate bigint NOT NULL DEFAULT 0,
                    occorrenze_valutate bigint NOT NULL DEFAULT 0,
                    ordini_generati bigint NOT NULL DEFAULT 0,
                    elementi_saltati bigint NOT NULL DEFAULT 0,
                    version bigint NOT NULL DEFAULT 0,
                    created_by text NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE tpo.run_messaggi (
                    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    run_id bigint NOT NULL REFERENCES tpo.runs(id),
                    tipo tpo.run_message_type NOT NULL,
                    posizione integer NOT NULL,
                    messaggio text NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (run_id, tipo, posizione)
                )
                """
            )
            objects_created = True

        repository = PostgreSQLSchedulingRunRepository(
            URLConnectionFactory(), created_by="integration-test"
        )
        started = CurrentSystemDate(datetime(2026, 8, 5, 5, tzinfo=TZ))
        completed_at = CurrentSystemDate(datetime(2026, 8, 5, 6, tzinfo=TZ))
        run_id = RunId("RUN-000001")
        opened = OpenSchedulingRun(run_id, started, False, 0)
        repository.add_open_run(opened)
        assert repository.get(run_id) == opened

        target = CompletedSchedulingRun(
            run_id=run_id,
            started_at=started,
            completed_at=completed_at,
            simulation=False,
            state=RunState.SUCCESS_WITH_WARNINGS,
            programmi_letti=3,
            righe_valutate=4,
            occorrenze_valutate=5,
            ordini_generati=2,
            elementi_saltati=1,
            warnings=("warning",),
            errors=(),
            version=1,
        )
        repositories = [
            PostgreSQLSchedulingRunRepository(URLConnectionFactory()),
            PostgreSQLSchedulingRunRepository(URLConnectionFactory()),
        ]
        barrier = Barrier(2)
        outcome_lock = Lock()
        outcomes = []
        thread_errors = []

        def finish(target_repository):
            barrier.wait()
            try:
                target_repository.complete(
                    run_id=run_id, expected_version=0, completed_run=target
                )
                outcome = "success"
            except SchedulingRunConflictError:
                outcome = "conflict"
            except BaseException as exc:
                with outcome_lock:
                    thread_errors.append(exc)
                return
            with outcome_lock:
                outcomes.append(outcome)

        threads = [Thread(target=finish, args=(item,)) for item in repositories]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert all(not thread.is_alive() for thread in threads)
        assert not thread_errors, f"Errori inattesi nei thread: {thread_errors!r}"
        assert sorted(outcomes) == ["conflict", "success"]
        assert repository.get(run_id) == target
        with admin.cursor() as cursor:
            cursor.execute("SELECT version, state, completed_at FROM tpo.runs")
            version, state, stored_completed_at = cursor.fetchone()
            assert (version, state, stored_completed_at) == (
                1,
                "SUCCESS_WITH_WARNINGS",
                completed_at.datetime,
            )
            cursor.execute("SELECT tipo, posizione, messaggio FROM tpo.run_messaggi")
            assert cursor.fetchall() == [("WARNING", 1, "warning")]
    finally:
        if objects_created:
            with admin.cursor() as cursor:
                cursor.execute("DROP TABLE tpo.run_messaggi")
                cursor.execute("DROP TABLE tpo.runs")
                cursor.execute("DROP TYPE tpo.run_message_type")
                cursor.execute("DROP TYPE tpo.run_state")
        if schema_created:
            with admin.cursor() as cursor:
                cursor.execute("DROP SCHEMA tpo")
        admin.close()
