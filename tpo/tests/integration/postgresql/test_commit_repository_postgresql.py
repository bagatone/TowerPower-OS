"""Integrazione reale, opt-in, del commit atomico PostgreSQL."""

from dataclasses import replace
import os
from threading import Barrier, Lock, Thread
from urllib.parse import urlparse

from alembic import command
import psycopg
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

from src.tpo_core.application.committer import (
    CommitExecutionError,
    CommitExistingKeyError,
    CommitRequest,
)
from src.tpo_core.application.identity import (
    CommissionIdentityRegistration,
    IdentityRegistrationCommissioningService,
)
from src.tpo_core.domain.identifiers import ActorId, OrdineId, RigaOrdineId, RunId
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from src.tpo_core.infrastructure.postgresql.commit_repository import (
    PostgreSQLCommitRepository,
)
from src.tpo_core.infrastructure.postgresql.identity_commissioning import (
    PostgreSQLIdentityRegistrationCommissioningWriter,
)
from tests.infrastructure.postgresql.test_commit_repository import instant, valid_request


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


class FixedClock:
    def now(self):
        return instant(9)


class CoordinatedConnectionFactory:
    """Apre connessioni reali e sincronizza un punto SQL scelto dal test."""

    def __init__(
        self, barrier: Barrier, *, synchronize_order_line_identity: bool
    ) -> None:
        self._barrier = barrier
        self._synchronize_order_line_identity = synchronize_order_line_identity
        self.connections = 0

    def connect(self):
        self.connections += 1
        connection = psycopg.connect(DATABASE_URL)
        if not self._synchronize_order_line_identity:
            self._barrier.wait(timeout=10)
        return _ConnectionProxy(
            connection,
            self._barrier if self._synchronize_order_line_identity else None,
        )


class _ConnectionProxy:
    def __init__(
        self, connection, order_line_identity_barrier: Barrier | None
    ) -> None:
        self._connection = connection
        self._order_line_identity_barrier = order_line_identity_barrier

    def cursor(self):
        return _CursorProxy(
            self._connection.cursor(), self._order_line_identity_barrier
        )

    def __getattr__(self, name):
        return getattr(self._connection, name)


class _CursorProxy:
    def __init__(self, cursor, order_line_identity_barrier: Barrier | None) -> None:
        self._cursor = cursor
        self._order_line_identity_barrier = order_line_identity_barrier

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def execute(self, query, params=None):
        normalized_query = " ".join(query.split())
        if (
            self._order_line_identity_barrier is not None
            and "FROM tpo.id_sequences WHERE sequence_name=%s FOR UPDATE"
            in normalized_query
            and params == (RigaOrdineId.sequence_name,)
        ):
            self._order_line_identity_barrier.wait(timeout=10)
        return self._cursor.execute(query, params)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


def _database_name_without_connecting(url: str) -> str:
    return urlparse(url).path.lstrip("/").split("?", 1)[0]


def _sqlalchemy_psycopg_url(url: str):
    parsed = make_url(url)
    if parsed.drivername == "postgresql":
        return parsed.set(drivername="postgresql+psycopg")
    if parsed.drivername == "postgresql+psycopg":
        return parsed
    pytest.fail("TPO_TEST_DATABASE_URL usa un dialect PostgreSQL non autorizzato.")


def _request_for_run(
    public_id: str,
    *,
    version: int = 3,
    order_id: str = "ORD-000001",
    idempotency_key: str = "key-001",
) -> CommitRequest:
    request = valid_request()
    run_id = RunId(public_id)
    completion = replace(
        request.completion,
        run_id=run_id,
        expected_version=version,
    )
    source_record = request.validated_plan.plan.records[0]
    record = replace(
        source_record,
        ordine=replace(source_record.ordine, id=OrdineId(order_id)),
        chiave_idempotenza=idempotency_key,
    )
    plan = replace(
        request.validated_plan.plan,
        run_id=run_id,
        records=(record,),
        idempotency_keys=(idempotency_key,),
        completion=completion,
    )
    snapshot = replace(request.validated_plan.validation_snapshot, run_id=run_id)
    validated = replace(request.validated_plan, plan=plan, validation_snapshot=snapshot)
    return replace(request, validated_plan=validated)


def _insert_fixtures(connection, run_ids=("RUN-000001",)) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO tpo.clienti
               (public_id, denominazione, created_at, created_by, updated_at,
                updated_by, version)
               VALUES ('CLI-000001','Cliente test',%s,'test',%s,'test',0)""",
            (instant(5).datetime, instant(5).datetime),
        )
        cursor.execute(
            """INSERT INTO tpo.varieta
               (public_id, denominazione, stato, created_at, created_by,
                updated_at, updated_by, version)
               VALUES ('VAR-000001','Varietà 1','ATTIVA',%s,'test',%s,'test',0),
                      ('VAR-000002','Varietà 2','ATTIVA',%s,'test',%s,'test',0)""",
            (instant(5).datetime, instant(5).datetime,
             instant(5).datetime, instant(5).datetime),
        )
        cursor.execute(
            """INSERT INTO tpo.programmi_fornitura
               (public_id, cliente_id, created_by)
               SELECT 'PF-000001', id, 'test' FROM tpo.clienti
               WHERE public_id='CLI-000001' RETURNING id"""
        )
        program_id = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO tpo.programmi_fornitura_versioni
               (programma_fornitura_id, cliente_id, numero_versione, stato,
                data_inizio, data_fine, orario_generazione,
                finestra_operativa_giorni, valida_dal, valida_al, created_by)
               SELECT %s,id,2,'ATTIVO','2026-08-01',NULL,'05:00:00',7,%s,NULL,'test'
               FROM tpo.clienti WHERE public_id='CLI-000001' RETURNING id""",
            (program_id, instant(5).datetime),
        )
        version_id = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO tpo.righe_programma_fornitura
               (programma_versione_id,posizione,varieta_id,quantita,unita_misura,
                tipo_ricorrenza,intervallo_giorni)
               SELECT %s,1,id,2.5,'GRAM','OGNI_X_GIORNI',1 FROM tpo.varieta
               WHERE public_id='VAR-000001'""",
            (version_id,),
        )
        cursor.execute(
            """INSERT INTO tpo.righe_programma_fornitura
               (programma_versione_id,posizione,varieta_id,quantita,unita_misura,
                tipo_ricorrenza,intervallo_giorni)
               SELECT %s,2,id,3,'SET','OGNI_X_GIORNI',1 FROM tpo.varieta
               WHERE public_id='VAR-000002'""",
            (version_id,),
        )
        for public_id in run_ids:
            cursor.execute(
                """INSERT INTO tpo.runs
                   (public_id,started_at,completed_at,simulation,state,
                    programmi_letti,righe_valutate,occorrenze_valutate,
                    ordini_generati,elementi_saltati,version,created_by)
                   VALUES (%s,%s,NULL,false,NULL,0,0,0,0,0,3,'test')""",
                (public_id, instant(5).datetime),
            )
    connection.commit()


def _commission_order_line_identity() -> None:
    service = IdentityRegistrationCommissioningService(
        PostgreSQLIdentityRegistrationCommissioningWriter(URLConnectionFactory())
    )
    service.commission(
        CommissionIdentityRegistration(
            RigaOrdineId.sequence_name,
            RigaOrdineId,
            RigaOrdineId.prefix,
            ActorId("tpo.identity-commissioner"),
        )
    )


def test_commit_atomico_postgresql_reale() -> None:
    database_name = _database_name_without_connecting(DATABASE_URL)
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

        _commission_order_line_identity()
        admin = psycopg.connect(DATABASE_URL)
        try:
            _insert_fixtures(admin, ("RUN-000001", "RUN-000002", "RUN-000003"))
            repository = PostgreSQLCommitRepository(URLConnectionFactory(), FixedClock())
            request = _request_for_run("RUN-000001")
            receipt = repository.execute_commit(request)

            assert receipt.run_id == RunId("RUN-000001")
            assert receipt.expected_record_count == 1
            assert receipt.expected_logical_row_count == 2
            assert receipt.appended_physical_row_count == 2
            assert receipt.reconciled_idempotency_keys == ("key-001",)
            assert receipt.commit_completed_at == instant(9)
            assert receipt.reconciliation_complete is True

            with admin.cursor() as cursor:
                cursor.execute("SELECT completed_at,state,version FROM tpo.runs WHERE public_id='RUN-000001'")
                assert cursor.fetchone() == (instant(6).datetime, "SUCCESS_WITH_WARNINGS", 4)
                cursor.execute("SELECT public_id,created_at,created_by,tipo_creazione FROM tpo.ordini")
                assert cursor.fetchone() == ("ORD-000001", instant(8).datetime, "actor-test", "AUTOMATICO")
                cursor.execute("SELECT posizione,quantita,unita_misura FROM tpo.righe_ordine ORDER BY posizione")
                assert cursor.fetchall() == [(1, 2.5, "GRAM"), (2, 3, "SET")]
                cursor.execute("SELECT count(*) FROM tpo.origini_righe_ordine")
                assert cursor.fetchone() == (2,)
                cursor.execute("SELECT tipo,posizione,messaggio FROM tpo.run_messaggi")
                assert cursor.fetchall() == [("WARNING", 1, "warning")]
                cursor.execute("SELECT entity_type,operation,before_data,after_data FROM tpo.audit_eventi ORDER BY id")
                audits = cursor.fetchall()
                assert [row[:2] for row in audits] == [("ORDINE", "INSERT"), ("RUN", "STATE_TRANSITION")]
                assert audits[0][2] is None and len(audits[0][3]) == 11
                assert len(audits[1][2]) == 4 and len(audits[1][3]) == 10

            duplicate = _request_for_run("RUN-000002")
            with pytest.raises(CommitExistingKeyError):
                repository.execute_commit(duplicate)
            wrong_version = _request_for_run("RUN-000003", version=2)
            with pytest.raises(CommitExecutionError):
                repository.execute_commit(wrong_version)
            with pytest.raises(CommitExecutionError):
                repository.execute_commit(request)

            with admin.cursor() as cursor:
                cursor.execute("SELECT public_id,completed_at,version FROM tpo.runs ORDER BY public_id")
                runs = cursor.fetchall()
                assert runs[1:] == [("RUN-000002", None, 3), ("RUN-000003", None, 3)]
                cursor.execute("SELECT count(*) FROM tpo.ordini")
                assert cursor.fetchone() == (1,)
                cursor.execute("SELECT count(*) FROM tpo.audit_eventi")
                assert cursor.fetchone() == (2,)
        finally:
            admin.close()
    finally:
        if migrated:
            with engine.connect() as connection:
                command.downgrade(make_config(connection=connection), "base")
                connection.commit()
        engine.dispose()


def test_commit_concorrente_postgresql_reale() -> None:
    database_name = _database_name_without_connecting(DATABASE_URL)
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

        _commission_order_line_identity()
        admin = psycopg.connect(DATABASE_URL)
        try:
            _insert_fixtures(
                admin,
                ("RUN-100001", "RUN-100002", "RUN-100003"),
            )

            same_run_barrier = Barrier(2)
            same_run_factory = CoordinatedConnectionFactory(
                same_run_barrier, synchronize_order_line_identity=False
            )
            same_run_repository = PostgreSQLCommitRepository(
                same_run_factory, FixedClock()
            )
            same_run_request = _request_for_run(
                "RUN-100001", order_id="ORD-100001", idempotency_key="lock-race"
            )
            same_run_outcomes = _concurrent_commits(
                same_run_repository,
                (same_run_request, same_run_request),
            )
            assert sorted(same_run_outcomes) == ["committed", "run_conflict"]
            assert same_run_factory.connections == 2

            order_line_identity_barrier = Barrier(2)
            idempotency_factory = CoordinatedConnectionFactory(
                order_line_identity_barrier,
                synchronize_order_line_identity=True,
            )
            idempotency_repository = PostgreSQLCommitRepository(
                idempotency_factory, FixedClock()
            )
            idempotency_outcomes = _concurrent_commits(
                idempotency_repository,
                (
                    _request_for_run(
                        "RUN-100002",
                        order_id="ORD-100002",
                        idempotency_key="idempotency-race",
                    ),
                    _request_for_run(
                        "RUN-100003",
                        order_id="ORD-100003",
                        idempotency_key="idempotency-race",
                    ),
                ),
            )
            assert sorted(idempotency_outcomes) == ["committed", "existing_key"]
            assert idempotency_factory.connections == 2

            with admin.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM tpo.ordini")
                assert cursor.fetchone() == (2,)
                cursor.execute("SELECT count(*) FROM tpo.righe_ordine")
                assert cursor.fetchone() == (4,)
                cursor.execute("SELECT count(*) FROM tpo.origini_righe_ordine")
                assert cursor.fetchone() == (4,)
                cursor.execute("SELECT count(*) FROM tpo.audit_eventi")
                assert cursor.fetchone() == (4,)
                cursor.execute(
                    """SELECT count(*) FROM tpo.runs
                       WHERE completed_at IS NOT NULL AND version = 4"""
                )
                assert cursor.fetchone() == (2,)
        finally:
            admin.close()
    finally:
        if migrated:
            with engine.connect() as connection:
                command.downgrade(make_config(connection=connection), "base")
                connection.commit()
        engine.dispose()


def _concurrent_commits(
    repository: PostgreSQLCommitRepository,
    requests: tuple[CommitRequest, CommitRequest],
) -> list[str]:
    outcomes: list[str] = []
    unexpected: list[BaseException] = []
    outcome_lock = Lock()

    def execute(request: CommitRequest) -> None:
        try:
            repository.execute_commit(request)
            outcome = "committed"
        except CommitExistingKeyError:
            outcome = "existing_key"
        except CommitExecutionError:
            outcome = "run_conflict"
        except BaseException as exc:
            with outcome_lock:
                unexpected.append(exc)
            return
        with outcome_lock:
            outcomes.append(outcome)

    threads = [Thread(target=execute, args=(request,)) for request in requests]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads)
    assert not unexpected, f"Errori concorrenti inattesi: {unexpected!r}"
    return outcomes
