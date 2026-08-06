"""Double transazionale deterministico; non equivale a PostgreSQL reale."""

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import psycopg
import pytest
from psycopg.types.json import Jsonb

from src.tpo_core.application.committer import (
    CommitExecutionContext,
    CommitExecutionError,
    CommitExistingKeyError,
    CommitPreparationError,
    CommitRequest,
    InvalidCommitRequestError,
)
from src.tpo_core.application.run_tracking import SchedulingRunCompletion
from src.tpo_core.application.scheduling.models import ScheduledOrderRecord
from src.tpo_core.application.scheduling.provenance import OrderLineProvenance
from src.tpo_core.application.write_plan import (
    ValidatedWritePlan,
    WritePlan,
    WritePlanValidationSnapshot,
)
from src.tpo_core.domain.entities.ordine import Ordine, RigaOrdine
from src.tpo_core.domain.identifiers import (
    ActorId, ClienteId, OrdineId, ProgrammaFornituraId, RunId, VarietaId,
)
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import OrdineCreationType, OrdineState, RunState
from src.tpo_core.domain.time_reference import CurrentSystemDate
from src.tpo_core.infrastructure.postgresql.commit_repository import (
    PostgreSQLCommitRepository,
)


TZ = ZoneInfo("Atlantic/Canary")


def instant(hour: int) -> CurrentSystemDate:
    return CurrentSystemDate(datetime(2026, 8, 6, hour, tzinfo=TZ))


def valid_request(*, warning: bool = True, completion: bool = True) -> CommitRequest:
    lines = (
        RigaOrdine(VarietaId("VAR-000001"), Quantity(Decimal("2.5"), UnitOfMeasure.GRAM)),
        RigaOrdine(VarietaId("VAR-000002"), Quantity(3, UnitOfMeasure.SET)),
    )
    provenance = (
        OrderLineProvenance(ProgrammaFornituraId("PF-000001"), 2, 1, 1),
        OrderLineProvenance(ProgrammaFornituraId("PF-000001"), 2, 2, 2),
    )
    record = ScheduledOrderRecord(
        Ordine(OrdineId("ORD-000001"), ClienteId("CLI-000001"), date(2026, 8, 6),
               lines, OrdineState.APERTO, OrdineCreationType.AUTOMATICO,
               ProgrammaFornituraId("PF-000001")),
        date(2026, 8, 7), "key-001", provenance,
    )
    warnings = ("warning",) if warning else ()
    completion_model = SchedulingRunCompletion(
        run_id=RunId("RUN-000001"), started_at=instant(5), completed_at=instant(6),
        simulation=False, expected_version=3,
        final_state=RunState.SUCCESS_WITH_WARNINGS if warning else RunState.SUCCESS,
        programmi_letti=1, righe_valutate=2, occorrenze_valutate=1,
        ordini_generati=1, elementi_saltati=0, warnings=warnings, errors=(),
    ) if completion else None
    plan = WritePlan(RunId("RUN-000001"), instant(6), (record,), 1, 2,
                     ("key-001",), warnings, completion_model)
    snapshot = WritePlanValidationSnapshot(plan.run_id, 1, 2, 0, "ORDINI", "1.0", "ORDINI")
    validated = ValidatedWritePlan(plan, instant(7), (), "ORDINI", "ORDINI", "1.0", snapshot, warnings)
    return CommitRequest(validated, instant(8), CommitExecutionContext(
        ActorId("actor-test"), "test commit", "correlation-001"))


def operation(sql: str) -> str:
    if sql.startswith("SELECT id, public_id"): return "RUN"
    if sql.startswith("SELECT chiave_idempotenza"): return "IDEMPOTENCY"
    if "FROM tpo.clienti" in sql: return "CLIENTS"
    if "FROM tpo.varieta" in sql: return "VARIETIES"
    if "FROM tpo.programmi_fornitura" in sql and "JOIN" not in sql: return "PROGRAMS"
    if sql.startswith("SELECT rp.id"): return "LOCATOR"
    if sql.startswith("INSERT INTO tpo.ordini"): return "ORDER"
    if sql.startswith("INSERT INTO tpo.righe_ordine"): return "LINE"
    if sql.startswith("INSERT INTO tpo.origini"): return "PROVENANCE"
    if sql.startswith("UPDATE tpo.runs"): return "UPDATE_RUN"
    if sql.startswith("INSERT INTO tpo.run_messaggi"): return "MESSAGE"
    if sql.startswith("INSERT INTO tpo.audit_eventi"): return "AUDIT"
    raise AssertionError(sql)


class Cursor:
    def __init__(self, database):
        self.database = database
        self.rowcount = -1
        self.one = None
        self.many = []
        self.line_number = self.locator_number = self.audit_number = 0
        self.closed = 0

    def execute(self, query, params):
        sql = " ".join(query.split())
        op = operation(sql)
        self.database.queries.append((op, sql, params))
        if self.database.fail_on == op:
            raise self.database.failure
        self.rowcount = 1
        self.one, self.many = None, []
        if op == "RUN":
            self.one = self.database.run
            self.rowcount = self.database.run_rowcount
        elif op == "IDEMPOTENCY": self.many = self.database.collisions
        elif op == "CLIENTS": self.many = self.database.clients
        elif op == "VARIETIES": self.many = self.database.varieties
        elif op == "PROGRAMS": self.many = self.database.programs
        elif op == "LOCATOR":
            values = self.database.locators[self.locator_number]
            self.locator_number += 1
            self.many = values
        elif op == "ORDER": self.one = self.database.order_returning
        elif op == "LINE":
            self.one = self.database.line_returning[self.line_number]
            self.line_number += 1
        elif op == "UPDATE_RUN": self.one = self.database.update_returning
        override = self.database.rowcount_override.get(op)
        if override is not None: self.rowcount = override

    def fetchone(self): return self.one
    def fetchall(self): return self.many
    def close(self):
        self.closed += 1
        if self.database.fail_cursor_close: raise RuntimeError("cursor close secret")


class Connection:
    def __init__(self, database):
        self.database = database
        self.cursor_calls = self.commits = self.rollbacks = self.closes = 0
        self.autocommit = False
        self.cursor_instance = Cursor(database)

    def cursor(self): self.cursor_calls += 1; return self.cursor_instance
    def commit(self):
        self.commits += 1
        if self.database.fail_commit: raise psycopg.DatabaseError("commit password")
        self.database.commit_observed = True
    def rollback(self):
        self.rollbacks += 1
        if self.database.fail_rollback: raise RuntimeError("rollback password")
    def close(self):
        self.closes += 1
        if self.database.fail_close: raise RuntimeError("close password")


class Database:
    def __init__(self):
        self.queries = []; self.connections = []; self.connect_calls = 0
        self.run = (10, "RUN-000001", instant(5).datetime, None, False, None, 3)
        self.run_rowcount = 1; self.collisions = []
        self.clients = [("CLI-000001", 20)]
        self.varieties = [("VAR-000001", 30), ("VAR-000002", 31)]
        self.programs = [("PF-000001", 40, 20)]
        self.locators = [[(50,)], [(51,)]]
        self.order_returning = (60, "ORD-000001")
        self.line_returning = [(70, 1), (71, 2)]
        self.update_returning = ("RUN-000001", 4, instant(6).datetime, "SUCCESS_WITH_WARNINGS")
        self.rowcount_override = {}; self.fail_on = None
        self.failure = psycopg.DatabaseError("driver password")
        self.fail_commit = self.fail_rollback = self.fail_close = self.fail_cursor_close = False
        self.commit_observed = False

    def connect(self):
        self.connect_calls += 1
        connection = Connection(self); self.connections.append(connection); return connection


@pytest.fixture
def database(): return Database()


@pytest.fixture
def repository(database): return PostgreSQLCommitRepository(database)


def test_costruttore_e_prepare_valido_non_aprono_connessione(repository, database):
    repository.prepare_commit(valid_request())
    assert database.connect_calls == 0


@pytest.mark.parametrize("candidate", [None, object(), "request"])
def test_request_invalida_prima_della_connessione(repository, database, candidate):
    with pytest.raises(InvalidCommitRequestError): repository.prepare_commit(candidate)
    assert database.connect_calls == 0


def test_completion_obbligatoria_prima_della_connessione(repository, database):
    with pytest.raises(CommitPreparationError): repository.prepare_commit(valid_request(completion=False))
    assert database.connect_calls == 0


def test_target_errato_prima_della_connessione(repository, database):
    request = valid_request(); validated = replace(request.validated_plan, target_name="ALTRO",
        validation_snapshot=replace(request.validated_plan.validation_snapshot, target_name="ALTRO"))
    with pytest.raises(CommitPreparationError): repository.prepare_commit(replace(request, validated_plan=validated))
    assert database.connect_calls == 0


@pytest.mark.parametrize("completed", [None, datetime(2026, 8, 6, 9, tzinfo=TZ)])
def test_completed_at_tipo_errato_prima_della_connessione(repository, database, completed):
    with pytest.raises(InvalidCommitRequestError): repository.execute_commit(valid_request(), completed)
    assert database.connect_calls == 0


def test_completed_at_precedente_prima_della_connessione(repository, database):
    with pytest.raises(InvalidCommitRequestError): repository.execute_commit(valid_request(), instant(7))
    assert database.connect_calls == 0


def test_transazione_completa_receipt_query_e_parametri(repository, database):
    completed = instant(9); request = valid_request()
    receipt = repository.execute_commit(request, completed)
    connection = database.connections[0]
    assert (database.connect_calls, connection.cursor_calls, connection.commits,
            connection.rollbacks, connection.closes) == (1, 1, 1, 0, 1)
    assert connection.cursor_instance.closed == 1 and connection.autocommit is False
    assert [q[0] for q in database.queries] == [
        "RUN", "IDEMPOTENCY", "CLIENTS", "VARIETIES", "PROGRAMS",
        "LOCATOR", "LOCATOR", "ORDER", "LINE", "LINE", "PROVENANCE",
        "PROVENANCE", "AUDIT", "UPDATE_RUN", "MESSAGE", "AUDIT",
    ]
    assert "FOR UPDATE" in database.queries[0][1]
    assert database.queries[1][2] == (["key-001"],)
    order_params = next(q[2] for q in database.queries if q[0] == "ORDER")
    assert order_params == ("ORD-000001", 20, 40, 10, date(2026, 8, 6),
        date(2026, 8, 7), "APERTO", "AUTOMATICO", "key-001",
        instant(8).datetime, "actor-test")
    line_params = [q[2] for q in database.queries if q[0] == "LINE"]
    assert line_params == [(60, 1, 30, Decimal("2.5"), "GRAM"), (60, 2, 31, Decimal("3"), "SET")]
    assert receipt.appended_physical_row_count == 2
    assert receipt.reconciled_idempotency_keys == ("key-001",)
    assert receipt.commit_completed_at == completed and receipt.reconciliation_complete
    assert database.commit_observed


def test_audit_payload_e_run_message_esatti(repository, database):
    repository.execute_commit(valid_request(), instant(9))
    audits = [q for q in database.queries if q[0] == "AUDIT"]
    assert len(audits) == 2 and database.queries[-1][0] == "AUDIT"
    order = audits[0][2]
    assert order[:7] == (instant(9).datetime, "actor-test", 10, "ORDINE", "ORD-000001", "INSERT", "test commit")
    assert order[7] is None and isinstance(order[8], Jsonb) and order[9] == "correlation-001"
    assert set(order[8].obj) == {"public_id", "cliente_id", "programma_fornitura_id", "run_id", "data_ordine", "data_consegna_prevista", "stato", "tipo_creazione", "chiave_idempotenza", "righe_count", "origini_count"}
    assert next(q[2] for q in database.queries if q[0] == "MESSAGE") == (10, "WARNING", 1, "warning")
    run = audits[1][2]
    assert run[3:6] == ("RUN", "RUN-000001", "STATE_TRANSITION")
    assert set(run[7].obj) == {"public_id", "state", "version", "completed_at"}
    assert set(run[8].obj) == {"public_id", "state", "version", "completed_at", "simulation", "programmi_letti", "righe_valutate", "occorrenze_valutate", "ordini_generati", "elementi_saltati"}


@pytest.mark.parametrize("mutation, message", [
    (lambda d: setattr(d, "run", None), "assente"),
    (lambda d: setattr(d, "run_rowcount", 2), "incoerente"),
    (lambda d: setattr(d, "run", (10,"RUN-999999",instant(5).datetime,None,False,None,3)), "incoerente"),
    (lambda d: setattr(d, "run", (10,"RUN-000001",instant(5).datetime,instant(6).datetime,False,"SUCCESS",3)), "conclusa"),
    (lambda d: setattr(d, "run", (10,"RUN-000001",instant(4).datetime,None,False,None,3)), "Contesto"),
    (lambda d: setattr(d, "run", (10,"RUN-000001",instant(5).datetime,None,True,None,3)), "Contesto"),
    (lambda d: setattr(d, "run", (10,"RUN-000001",instant(5).datetime,None,False,None,2)), "Versione"),
])
def test_conflitti_run_rollback_senza_scritture(repository, database, mutation, message):
    mutation(database)
    with pytest.raises(CommitExecutionError, match=message): repository.execute_commit(valid_request(), instant(9))
    assert all(not op.startswith("INSERT") for op, _, _ in database.queries)
    connection = database.connections[0]
    assert connection.rollbacks == 1 and connection.commits == 0 and connection.closes == 1


def test_idempotenza_pre_esistente_rollback(repository, database):
    database.collisions = [("key-001",)]
    with pytest.raises(CommitExistingKeyError): repository.execute_commit(valid_request(), instant(9))
    assert [q[0] for q in database.queries] == ["RUN", "IDEMPOTENCY"]
    assert database.connections[0].rollbacks == 1


@pytest.mark.parametrize("attribute,value", [
    ("clients", []), ("clients", [("CLI-000001",20),("CLI-000001",21)]),
    ("clients", [("CLI-000001",0)]), ("varieties", []),
    ("varieties", [("VAR-000001",30)]), ("programs", []),
    ("programs", [("PF-000001",40,99)]),
])
def test_lookup_incoerente_rollback(repository, database, attribute, value):
    setattr(database, attribute, value)
    with pytest.raises(CommitExecutionError): repository.execute_commit(valid_request(), instant(9))
    assert database.connections[0].rollbacks == 1


@pytest.mark.parametrize("locators", [[], [[(0,)], [(51,)]], [[(50,), (52,)], [(51,)]]])
def test_locator_incoerente_rollback(repository, database, locators):
    database.locators = locators or [[]]
    with pytest.raises(CommitExecutionError): repository.execute_commit(valid_request(), instant(9))
    assert database.connections[0].rollbacks == 1


@pytest.mark.parametrize("returning", [None, (0,"ORD-000001"), (60,"ORD-999999")])
def test_returning_ordine_incoerente(repository, database, returning):
    database.order_returning = returning
    with pytest.raises(CommitExecutionError): repository.execute_commit(valid_request(), instant(9))
    assert database.connections[0].rollbacks == 1


@pytest.mark.parametrize("returning", [None, (0,1), (70,2)])
def test_returning_riga_incoerente(repository, database, returning):
    database.line_returning[0] = returning
    with pytest.raises(CommitExecutionError): repository.execute_commit(valid_request(), instant(9))
    assert database.connections[0].rollbacks == 1


@pytest.mark.parametrize("returning", [None, ("RUN-999999",4,instant(6).datetime,"SUCCESS_WITH_WARNINGS"), ("RUN-000001",5,instant(6).datetime,"SUCCESS_WITH_WARNINGS"), ("RUN-000001",4,instant(7).datetime,"SUCCESS_WITH_WARNINGS")])
def test_update_run_incoerente(repository, database, returning):
    database.update_returning = returning
    with pytest.raises(CommitExecutionError): repository.execute_commit(valid_request(), instant(9))
    assert database.connections[0].rollbacks == 1


@pytest.mark.parametrize("op", ["PROVENANCE", "AUDIT", "MESSAGE"])
def test_rowcount_scrittura_incoerente(repository, database, op):
    database.rowcount_override[op] = 0
    with pytest.raises(CommitExecutionError): repository.execute_commit(valid_request(), instant(9))
    assert database.connections[0].rollbacks == 1


def test_success_senza_warning_non_inserisce_messaggi(repository, database):
    database.update_returning = ("RUN-000001",4,instant(6).datetime,"SUCCESS")
    repository.execute_commit(valid_request(warning=False), instant(9))
    assert "MESSAGE" not in [q[0] for q in database.queries]


@pytest.mark.parametrize("op", ["RUN", "CLIENTS", "ORDER"])
def test_psycopg_convertito_con_causa_e_un_solo_tentativo(repository, database, op):
    database.fail_on = op
    with pytest.raises(CommitExecutionError) as captured: repository.execute_commit(valid_request(), instant(9))
    assert captured.value.__cause__ is database.failure
    assert "password" not in str(captured.value) and database.connect_calls == 1
    assert database.connections[0].rollbacks == 1


class NamedUnique(psycopg.errors.UniqueViolation):
    def __init__(self, name): super().__init__("duplicate password"); self._name = name
    @property
    def diag(self): return SimpleNamespace(constraint_name=self._name)


@pytest.mark.parametrize("name, expected", [("ordini_chiave_idempotenza_key", CommitExistingKeyError), ("ordini_public_id_key", CommitExecutionError)])
def test_unique_violation_classificata_per_constraint(repository, database, name, expected):
    database.fail_on = "ORDER"; database.failure = NamedUnique(name)
    with pytest.raises(expected) as captured: repository.execute_commit(valid_request(), instant(9))
    assert captured.value.__cause__ is database.failure
    assert database.connections[0].rollbacks == 1 and database.connect_calls == 1


@pytest.mark.parametrize("failure", [TypeError("bug"), AttributeError("bug"), AssertionError("bug")])
def test_errori_programmazione_non_mascherati(repository, database, failure):
    database.fail_on = "ORDER"; database.failure = failure
    with pytest.raises(type(failure), match="bug"): repository.execute_commit(valid_request(), instant(9))
    assert database.connections[0].rollbacks == 1


def test_commit_in_certo_non_restituisce_receipt_e_cleanup(repository, database):
    database.fail_commit = database.fail_rollback = database.fail_close = database.fail_cursor_close = True
    with pytest.raises(CommitExecutionError) as captured: repository.execute_commit(valid_request(), instant(9))
    connection = database.connections[0]
    assert isinstance(captured.value.__cause__, psycopg.DatabaseError)
    assert (connection.commits, connection.rollbacks, connection.closes) == (1,1,1)
    assert connection.cursor_instance.closed == 1


def test_lookup_table_whitelist(database):
    cursor = Cursor(database)
    with pytest.raises(ValueError, match="non autorizzata"):
        PostgreSQLCommitRepository._lookup(cursor, "ordini", {"x"})
    assert database.queries == []
