"""End-to-end reale, opt-in, del commit operativo dello Scheduling."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import os
from pathlib import Path
from threading import Barrier, Lock, Thread
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo

from alembic import command
import psycopg
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url

from src.tpo_core.application.committer import (
    CommitExecutionContext,
    CommitExecutionError,
    CommitStatus,
)
from src.tpo_core.application.operational_scheduling import (
    ExecuteSchedulingCommitInput,
    ExecuteSchedulingCommitResult,
)
from src.tpo_core.application.run_tracking import OpenSchedulingRun
from src.tpo_core.application.write_plan import InvalidWritePlanError
from src.tpo_core.bootstrap.factory import build_application
from src.tpo_core.domain.identifiers import ActorId, RunId
from src.tpo_core.domain.states import RunState
from src.tpo_core.domain.time_reference import CurrentSystemDate
from src.tpo_core.infrastructure.postgresql.alembic import make_config


DATABASE_URL = os.environ.get("TPO_TEST_DATABASE_URL")
TZ = ZoneInfo("Atlantic/Canary")

class NoNetworkGoogleService:
    def __init__(self) -> None:
        self.calls = 0

    def spreadsheets(self):
        self.calls += 1
        raise AssertionError("Il percorso operativo non deve usare Google Sheets.")


class LegacyIdGenerator:
    def next_id(self, identifier_type):
        raise AssertionError("Il grafo operativo deve usare PostgreSQL Identity.")


def instant(day: int, hour: int) -> CurrentSystemDate:
    return CurrentSystemDate(datetime(2026, 8, day, hour, tzinfo=TZ))


def _validated_database_url() -> str:
    """Valida il solo DSN test prima che qualsiasi driver possa connettersi."""

    assert DATABASE_URL is not None
    parsed = urlparse(DATABASE_URL)
    database_name = unquote(parsed.path.lstrip("/").split("?", 1)[0])
    if not database_name or "test" not in database_name.lower():
        pytest.fail(
            "TPO_TEST_DATABASE_URL deve indicare un database dedicato contenente 'test'."
        )
    return DATABASE_URL


def _sqlalchemy_psycopg_url(url: str) -> URL:
    """Seleziona esplicitamente Psycopg 3 preservando ogni componente URL."""

    parsed = make_url(url)
    if parsed.drivername == "postgresql":
        return parsed.set(drivername="postgresql+psycopg")
    if parsed.drivername == "postgresql+psycopg":
        return parsed
    raise ValueError("TPO_TEST_DATABASE_URL usa un dialect PostgreSQL non autorizzato.")


def test_sqlalchemy_url_postgresql_seleziona_psycopg3() -> None:
    converted = _sqlalchemy_psycopg_url(
        "postgresql://user:secret@db.invalid:5432/tower_test"
    )
    assert converted.drivername == "postgresql+psycopg"


def test_sqlalchemy_url_psycopg3_resta_invariata() -> None:
    source = make_url(
        "postgresql+psycopg://user:secret@db.invalid:5432/tower_test"
    )
    assert _sqlalchemy_psycopg_url(source.render_as_string(hide_password=False)) == source


def test_sqlalchemy_url_preserva_database_e_query() -> None:
    converted = _sqlalchemy_psycopg_url(
        "postgresql://user:secret@db.invalid:5433/tower_test"
        "?sslmode=require&connect_timeout=7"
    )
    assert converted.database == "tower_test"
    assert converted.port == 5433
    assert dict(converted.query) == {"sslmode": "require", "connect_timeout": "7"}


def test_sqlalchemy_url_non_stampa_password(capsys) -> None:
    secret = "password-not-to-print"
    converted = _sqlalchemy_psycopg_url(
        f"postgresql://user:{secret}@db.invalid:5432/tower_test"
    )
    assert converted.password == secret
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


@pytest.mark.parametrize(
    "url",
    (
        "postgresql+psycopg2://user:secret@db.invalid/tower_test",
        "mysql://user:secret@db.invalid/tower_test",
    ),
)
def test_sqlalchemy_url_rifiuta_dialect_non_autorizzato(url: str) -> None:
    with pytest.raises(ValueError, match="non autorizzato"):
        _sqlalchemy_psycopg_url(url)


def _postgresql_environment(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if parsed.hostname is None or parsed.username is None or parsed.password is None:
        pytest.fail("TPO_TEST_DATABASE_URL non contiene credenziali PostgreSQL complete.")
    sslmode = query.get("sslmode", ["require"])[0]
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        pytest.fail("Il database test deve usare una modalità SSL supportata dal runtime.")
    timeout = query.get("connect_timeout", ["5"])[0]
    return {
        "TPO_DATABASE_HOST": parsed.hostname,
        "TPO_DATABASE_PORT": str(parsed.port or 5432),
        "TPO_DATABASE_NAME": unquote(parsed.path.lstrip("/")),
        "TPO_DATABASE_USER": unquote(parsed.username),
        "TPO_DATABASE_PASSWORD": unquote(parsed.password),
        "TPO_DATABASE_SSLMODE": sslmode,
        "TPO_DATABASE_CONNECT_TIMEOUT": timeout,
    }


def _settings_file(tmp_path: Path) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(
        """google_sheets:
  spreadsheet_id: integration-test
  credentials_file: unused.json
  scopes: [https://www.googleapis.com/auth/spreadsheets]
  sheets: [PROGRAMMI_FORNITURA, ORDINI]
""",
        encoding="utf-8",
    )
    return path


def _seed(connection) -> None:
    """Inserisce esclusivamente il minimo dataset test parametrizzato."""

    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO tpo.clienti
               (public_id, denominazione, created_at, created_by, updated_at,
                updated_by, version)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            ("CLI-900001", "Cliente E2E test", instant(8, 4).datetime,
             "e2e-test", instant(8, 4).datetime, "e2e-test", 0),
        )
        for public_id, name in (
            ("VAR-900001", "Varietà E2E 1"),
            ("VAR-900002", "Varietà E2E 2"),
        ):
            cursor.execute(
                """INSERT INTO tpo.varieta
                   (public_id, denominazione, stato, created_at, created_by,
                    updated_at, updated_by, version)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (public_id, name, "ATTIVA", instant(8, 4).datetime,
                 "e2e-test", instant(8, 4).datetime, "e2e-test", 0),
            )
        cursor.execute(
            """INSERT INTO tpo.programmi_fornitura
               (public_id, cliente_id, created_by)
               SELECT %s, id, %s FROM tpo.clienti WHERE public_id = %s
               RETURNING id""",
            ("PF-900001", "e2e-test", "CLI-900001"),
        )
        program_id = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO tpo.programmi_fornitura_versioni
               (programma_fornitura_id, cliente_id, numero_versione, stato,
                data_inizio, data_fine, orario_generazione,
                finestra_operativa_giorni, valida_dal, valida_al, created_by)
               SELECT %s, id, %s, %s, %s, NULL, %s, %s, %s, %s, %s
               FROM tpo.clienti WHERE public_id = %s RETURNING id""",
            (program_id, 1, "SOSPESO", date(2026, 8, 1), "04:00:00", 0,
             instant(8, 1).datetime, instant(8, 7).datetime, "e2e-test", "CLI-900001"),
        )
        historical_version_id = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO tpo.righe_programma_fornitura
               (programma_versione_id, posizione, varieta_id, quantita,
                unita_misura, tipo_ricorrenza, intervallo_giorni)
               SELECT %s, %s, id, %s, %s, %s, %s FROM tpo.varieta
               WHERE public_id = %s""",
            (historical_version_id, 9, 99, "UNIT", "OGNI_X_GIORNI", 30,
             "VAR-900001"),
        )
        cursor.execute(
            """INSERT INTO tpo.programmi_fornitura_versioni
               (programma_fornitura_id, cliente_id, numero_versione, stato,
                data_inizio, data_fine, orario_generazione,
                finestra_operativa_giorni, valida_dal, valida_al, created_by)
               SELECT %s, id, %s, %s, %s, NULL, %s, %s, %s, NULL, %s
               FROM tpo.clienti WHERE public_id = %s RETURNING id""",
            (program_id, 2, "ATTIVO", date(2026, 8, 8), "05:00:00", 0,
             instant(8, 7).datetime, "e2e-test", "CLI-900001"),
        )
        current_version_id = cursor.fetchone()[0]
        for position, variety, quantity, unit, recurrence, interval in (
            (1, "VAR-900001", 2.5, "GRAM", "OGNI_X_GIORNI", 1),
            (2, "VAR-900002", 3, "SET", "GIORNI_SETTIMANA", None),
        ):
            cursor.execute(
                """INSERT INTO tpo.righe_programma_fornitura
                   (programma_versione_id, posizione, varieta_id, quantita,
                    unita_misura, tipo_ricorrenza, intervallo_giorni)
                   SELECT %s, %s, id, %s, %s, %s, %s FROM tpo.varieta
                   WHERE public_id = %s RETURNING id""",
                (current_version_id, position, quantity, unit, recurrence,
                 interval, variety),
            )
            line_id = cursor.fetchone()[0]
            if recurrence == "GIORNI_SETTIMANA":
                cursor.execute(
                    """INSERT INTO tpo.righe_programma_giorni
                       (riga_programma_id, giorno_iso) VALUES (%s, %s)""",
                    (line_id, 6),
                )
        cursor.execute(
            """INSERT INTO tpo.id_sequences
               (sequence_name, identifier_type, prefix, next_value, version,
                updated_at, updated_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            ("ORDINE_ID", "OrdineId", "ORD", 900001, 0,
             instant(8, 4).datetime, "e2e-test"),
        )
        for public_id, version in (
            ("RUN-900001", 0),
            ("RUN-900002", 0),
            ("RUN-900003", 1),
        ):
            cursor.execute(
                """INSERT INTO tpo.runs
                   (public_id, started_at, completed_at, simulation, state,
                    programmi_letti, righe_valutate, occorrenze_valutate,
                    ordini_generati, elementi_saltati, version, created_by)
                   VALUES (%s, %s, NULL, false, NULL, 0, 0, 0, 0, 0, %s, %s)""",
                (public_id, instant(8, 5).datetime, version, "e2e-test"),
            )
    connection.commit()


def _input(run_id: str, *, day: int = 8, expected_version: int = 0):
    return ExecuteSchedulingCommitInput(
        open_run=OpenSchedulingRun(
            RunId(run_id), instant(8, 5), False, expected_version
        ),
        current_system_date=instant(day, 6),
        completion_at=instant(day, 7),
        requested_at=instant(day, 8),
        commit_completed_at=instant(day, 9),
        execution_context=CommitExecutionContext(
            ActorId("e2e-scheduler"), "postgresql e2e validation", "e2e-2.19"
        ),
    )


@pytest.mark.postgresql_integration
@pytest.mark.skipif(
    not DATABASE_URL,
    reason="TPO_TEST_DATABASE_URL non configurata: PostgreSQL reale non eseguito.",
)
def test_operational_scheduling_postgresql_end_to_end(tmp_path: Path) -> None:
    url = _validated_database_url()
    engine = sa.create_engine(_sqlalchemy_psycopg_url(url))
    migrated = False
    google = NoNetworkGoogleService()
    try:
        with engine.connect() as connection:
            if sa.inspect(connection).has_schema("tpo"):
                pytest.fail("Lo schema tpo esiste già: è richiesto un database test vuoto.")
            command.upgrade(make_config(connection=connection), "head")
            connection.commit()
            migrated = True

        admin = psycopg.connect(url)
        try:
            _seed(admin)
            container = build_application(
                _settings_file(tmp_path),
                google_service=google,
                id_generator=LegacyIdGenerator(),
                postgresql_environment=_postgresql_environment(url),
            )
            assert container.execute_scheduling_commit is not None
            assert container.application_committer is not None
            assert container.postgresql_commit_repository is not None
            assert (
                container.application_committer._repository
                is container.postgresql_commit_repository
            )
            program_repository = (
                container.execute_scheduling_commit
                ._run_scheduling
                ._programmi_repository
            )
            programs = program_repository.list_versioned_for_scheduling()
            assert len(programs) == 1
            versioned = programs[0]
            assert versioned.programma.id.value == "PF-900001"
            assert versioned.programma.cliente_id.value == "CLI-900001"
            assert versioned.version == 2
            assert versioned.programma.stato.value == "ATTIVO"
            assert versioned.programma.data_inizio == date(2026, 8, 8)
            assert versioned.programma.data_fine is None
            assert versioned.programma.orario_generazione.isoformat() == "05:00:00"
            assert versioned.programma.finestra_operativa_giorni == 0
            assert tuple(line.position for line in versioned.lines) == (1, 2)
            assert tuple(line.line.varieta_id.value for line in versioned.lines) == (
                "VAR-900001", "VAR-900002"
            )
            assert tuple(line.line.quantita.value for line in versioned.lines) == (
                Decimal("2.5"), Decimal("3")
            )
            assert tuple(line.line.quantita.unit.value for line in versioned.lines) == (
                "GRAM", "SET"
            )
            assert versioned.lines[1].line.configurazione_temporale.giorni_settimana == (6,)

            captured_requests = []
            original_commit = container.application_committer.commit

            def capture_commit(request, completed_at):
                captured_requests.append(request)
                with admin.cursor() as cursor:
                    cursor.execute(
                        """SELECT completed_at, state, version FROM tpo.runs
                           WHERE public_id = %s""",
                        (request.validated_plan.plan.run_id.value,),
                    )
                    physical_run = cursor.fetchone()
                assert physical_run[0] is None and physical_run[1] is None
                return original_commit(request, completed_at)

            container.application_committer.commit = capture_commit
            output = container.execute_scheduling_commit.execute(
                _input("RUN-900001")
            )

            assert isinstance(output, ExecuteSchedulingCommitResult)
            assert output.scheduling_result.esito is RunState.SUCCESS
            assert output.commit_result.status is CommitStatus.COMMITTED
            assert output.completed_run.run_id == RunId("RUN-900001")
            assert output.completed_run.version == 1
            assert output.completed_run.completed_at == instant(8, 7)
            assert output.commit_result.commit_completed_at == instant(8, 9)
            assert output.commit_result.expected_operations == 2
            assert output.commit_result.committed_operations == 2
            assert len(captured_requests) == 1
            plan = captured_requests[0].validated_plan.plan
            assert plan.expected_record_count == 1
            assert plan.expected_logical_row_count == 2
            assert output.commit_result.reconciled_idempotency_keys == plan.idempotency_keys
            assert plan.records[0].ordine.id.value == "ORD-900001"
            assert tuple(item.programma_version for item in plan.records[0].provenance) == (2, 2)
            assert tuple(item.programma_line_position for item in plan.records[0].provenance) == (1, 2)

            with admin.cursor() as cursor:
                cursor.execute(
                    """SELECT completed_at, state, programmi_letti, righe_valutate,
                              occorrenze_valutate, ordini_generati,
                              elementi_saltati, version
                       FROM tpo.runs WHERE public_id = %s""",
                    ("RUN-900001",),
                )
                assert cursor.fetchone() == (
                    instant(8, 7).datetime, "SUCCESS", 1, 2, 1, 1, 0, 1
                )
                cursor.execute(
                    """SELECT o.public_id, c.public_id, p.public_id, r.public_id,
                              o.data_ordine, o.data_consegna_prevista, o.tipo_creazione,
                              o.created_at, o.created_by, o.chiave_idempotenza
                       FROM tpo.ordini o JOIN tpo.clienti c ON c.id=o.cliente_id
                       JOIN tpo.programmi_fornitura p ON p.id=o.programma_fornitura_id
                       JOIN tpo.runs r ON r.id=o.run_id"""
                )
                order = cursor.fetchone()
                assert order[:9] == (
                    "ORD-900001", "CLI-900001", "PF-900001", "RUN-900001",
                    date(2026, 8, 8), date(2026, 8, 8), "AUTOMATICO",
                    instant(8, 8).datetime, "e2e-scheduler",
                )
                idempotency_key = order[9]
                assert isinstance(idempotency_key, str) and idempotency_key
                cursor.execute(
                    """SELECT ro.posizione, v.public_id, ro.quantita, ro.unita_misura
                       FROM tpo.righe_ordine ro JOIN tpo.varieta v ON v.id=ro.varieta_id
                       ORDER BY ro.posizione"""
                )
                assert cursor.fetchall() == [
                    (1, "VAR-900001", 2.5, "GRAM"),
                    (2, "VAR-900002", 3, "SET"),
                ]
                cursor.execute(
                    """SELECT ro.posizione, pv.numero_versione, rp.posizione
                       FROM tpo.origini_righe_ordine oro
                       JOIN tpo.righe_ordine ro ON ro.id=oro.riga_ordine_id
                       JOIN tpo.righe_programma_fornitura rp ON rp.id=oro.riga_programma_id
                       JOIN tpo.programmi_fornitura_versioni pv
                         ON pv.id=rp.programma_versione_id ORDER BY ro.posizione"""
                )
                assert cursor.fetchall() == [(1, 2, 1), (2, 2, 2)]
                cursor.execute("SELECT tipo, posizione, messaggio FROM tpo.run_messaggi")
                assert cursor.fetchall() == []
                cursor.execute(
                    """SELECT entity_type, entity_public_id, operation, actor, reason,
                              correlation_id, before_data, after_data
                       FROM tpo.audit_eventi ORDER BY id"""
                )
                audits = cursor.fetchall()
                assert [row[:3] for row in audits] == [
                    ("ORDINE", "ORD-900001", "INSERT"),
                    ("RUN", "RUN-900001", "STATE_TRANSITION"),
                ]
                assert all(row[3:6] == (
                    "e2e-scheduler", "postgresql e2e validation", "e2e-2.19"
                ) for row in audits)
                assert audits[0][6] is None
                assert set(audits[0][7]) == {
                    "public_id", "cliente_id", "programma_fornitura_id", "run_id",
                    "data_ordine", "data_consegna_prevista", "stato",
                    "tipo_creazione", "chiave_idempotenza", "righe_count",
                    "origini_count",
                }
                assert set(audits[1][6]) == {
                    "public_id", "state", "version", "completed_at"
                }
                assert set(audits[1][7]) == {
                    "public_id", "state", "version", "completed_at", "simulation",
                    "programmi_letti", "righe_valutate", "occorrenze_valutate",
                    "ordini_generati", "elementi_saltati",
                }
                cursor.execute(
                    """SELECT next_value, version FROM tpo.id_sequences
                       WHERE identifier_type = %s""",
                    ("OrdineId",),
                )
                assert cursor.fetchone() == (900002, 1)

            validation_repository = (
                container.execute_scheduling_commit._write_plan_validator._repository
            )
            snapshot = validation_repository.get_target_snapshot(target_name="ORDINI")
            assert idempotency_key in snapshot.existing_idempotency_keys

            with pytest.raises(InvalidWritePlanError):
                container.execute_scheduling_commit.execute(_input("RUN-900002"))
            assert len(captured_requests) == 1

            with pytest.raises(CommitExecutionError, match="Versione"):
                container.execute_scheduling_commit.execute(
                    _input("RUN-900003", day=9, expected_version=0)
                )
            assert len(captured_requests) == 2

            with pytest.raises(CommitExecutionError, match="già conclusa"):
                container.postgresql_commit_repository.execute_commit(
                    captured_requests[0], instant(8, 9)
                )

            with admin.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM tpo.ordini")
                assert cursor.fetchone() == (1,)
                cursor.execute("SELECT count(*) FROM tpo.righe_ordine")
                assert cursor.fetchone() == (2,)
                cursor.execute("SELECT count(*) FROM tpo.origini_righe_ordine")
                assert cursor.fetchone() == (2,)
                cursor.execute("SELECT count(*) FROM tpo.audit_eventi")
                assert cursor.fetchone() == (2,)
                cursor.execute(
                    """SELECT public_id, completed_at, state, version
                       FROM tpo.runs ORDER BY public_id"""
                )
                assert cursor.fetchall() == [
                    ("RUN-900001", instant(8, 7).datetime, "SUCCESS", 1),
                    ("RUN-900002", None, None, 0),
                    ("RUN-900003", None, None, 1),
                ]
            assert google.calls == 0
        finally:
            admin.close()
    finally:
        if migrated:
            with engine.connect() as connection:
                command.downgrade(make_config(connection=connection), "base")
                connection.commit()
        engine.dispose()


@pytest.mark.postgresql_integration
@pytest.mark.skipif(
    not DATABASE_URL,
    reason="TPO_TEST_DATABASE_URL non configurata: PostgreSQL reale non eseguito.",
)
def test_operational_commit_concurrency_postgresql(tmp_path: Path) -> None:
    url = _validated_database_url()
    engine = sa.create_engine(_sqlalchemy_psycopg_url(url))
    migrated = False
    try:
        with engine.connect() as connection:
            if sa.inspect(connection).has_schema("tpo"):
                pytest.fail("Lo schema tpo esiste già: è richiesto un database test vuoto.")
            command.upgrade(make_config(connection=connection), "head")
            connection.commit()
            migrated = True

        admin = psycopg.connect(url)
        try:
            _seed(admin)
            container = build_application(
                _settings_file(tmp_path),
                google_service=NoNetworkGoogleService(),
                id_generator=LegacyIdGenerator(),
                postgresql_environment=_postgresql_environment(url),
            )
            assert container.execute_scheduling_commit is not None
            assert container.application_committer is not None
            assert container.postgresql_commit_repository is not None

            allocator = (
                container.execute_scheduling_commit._run_scheduling._id_generator
            )
            original_next_id = allocator.next_id
            allocation_lock = Lock()

            def synchronized_next_id(identifier_type):
                with allocation_lock:
                    return original_next_id(identifier_type)

            allocator.next_id = synchronized_next_id

            commit_connections = _CountingFactory(
                container.postgresql_connection_factory
            )
            container.postgresql_commit_repository._connection_factory = (
                commit_connections
            )

            commit_barrier = Barrier(2)
            original_commit = container.application_committer.commit

            def synchronized_commit(request, completed_at):
                commit_barrier.wait(timeout=10)
                return original_commit(request, completed_at)

            container.application_committer.commit = synchronized_commit

            outcomes: list[str] = []
            unexpected: list[BaseException] = []
            outcome_lock = Lock()

            def execute() -> None:
                try:
                    result = container.execute_scheduling_commit.execute(
                        _input("RUN-900001")
                    )
                    assert result.commit_result.status is CommitStatus.COMMITTED
                    outcome = "committed"
                except CommitExecutionError:
                    outcome = "run_conflict"
                except BaseException as exc:
                    with outcome_lock:
                        unexpected.append(exc)
                    return
                with outcome_lock:
                    outcomes.append(outcome)

            threads = [Thread(target=execute), Thread(target=execute)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=20)

            assert all(not thread.is_alive() for thread in threads)
            assert not unexpected, f"Errori orchestratore inattesi: {unexpected!r}"
            assert sorted(outcomes) == ["committed", "run_conflict"]
            assert commit_connections.connections == 2

            with admin.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM tpo.ordini")
                assert cursor.fetchone() == (1,)
                cursor.execute("SELECT count(*) FROM tpo.righe_ordine")
                assert cursor.fetchone() == (2,)
                cursor.execute("SELECT count(*) FROM tpo.origini_righe_ordine")
                assert cursor.fetchone() == (2,)
                cursor.execute("SELECT count(*) FROM tpo.audit_eventi")
                assert cursor.fetchone() == (2,)
                cursor.execute(
                    """SELECT completed_at, state, version FROM tpo.runs
                       WHERE public_id = %s""",
                    ("RUN-900001",),
                )
                completed_at, state, version = cursor.fetchone()
                assert completed_at == instant(8, 7).datetime
                assert state == "SUCCESS"
                assert version == 1
                cursor.execute(
                    """SELECT next_value, version FROM tpo.id_sequences
                       WHERE identifier_type = %s""",
                    ("OrdineId",),
                )
                assert cursor.fetchone() == (900003, 2)
        finally:
            admin.close()
    finally:
        if migrated:
            with engine.connect() as connection:
                command.downgrade(make_config(connection=connection), "base")
                connection.commit()
        engine.dispose()


class _CountingFactory:
    def __init__(self, delegate) -> None:
        self._delegate = delegate
        self.connections = 0
        self._lock = Lock()

    def connect(self):
        with self._lock:
            self.connections += 1
        return self._delegate.connect()
