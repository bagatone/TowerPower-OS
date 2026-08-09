from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.committer import (
    ApplicationCommitter,
    CommitExecutionContext,
    CommitExistingKeyError,
    CommitExecutionError,
    CommitRequest,
    CommitSchemaChangedError,
    CommitStatus,
)
from src.tpo_core.application.scheduling.models import ScheduledOrderRecord
from src.tpo_core.application.write_plan import (
    ValidatedWritePlan,
    WritePlan,
    WritePlanValidationSnapshot,
)
from src.tpo_core.domain.entities.ordine import Ordine, RigaOrdine
from src.tpo_core.domain.identifiers import (
    ActorId,
    ClienteId,
    OrdineId,
    ProgrammaFornituraId,
    RunId,
    VarietaId,
)
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import OrdineCreationType, OrdineState
from src.tpo_core.domain.time_reference import CurrentSystemDate
from src.tpo_core.infrastructure.google_sheets.commit_repository import (
    GoogleSheetsCommitRepository,
)
from src.tpo_core.infrastructure.google_sheets.errors import (
    GoogleSheetsRepositoryError,
)
from src.tpo_core.infrastructure.google_sheets.mappers import (
    ORDINI_HEADERS,
    scheduled_orders_to_rows,
)


TZ = ZoneInfo("Atlantic/Canary")


def instant(hour: int) -> CurrentSystemDate:
    return CurrentSystemDate(datetime(2026, 8, 3, hour, tzinfo=TZ))


class FakeClock:
    def now(self) -> CurrentSystemDate:
        return instant(9)


def record(number: int, key: str, *, two_lines: bool = False):
    righe = (
        RigaOrdine(
            VarietaId("VAR-000001"),
            Quantity(2, UnitOfMeasure.SET),
        ),
    )
    if two_lines:
        righe += (
            RigaOrdine(
                VarietaId("VAR-000002"),
                Quantity("1.5", UnitOfMeasure.GRAM),
            ),
        )
    return ScheduledOrderRecord(
        Ordine(
            OrdineId(f"ORD-{number:06d}"),
            ClienteId("CLI-000001"),
            date(2026, 8, 3),
            righe,
            OrdineState.APERTO,
            OrdineCreationType.AUTOMATICO,
            ProgrammaFornituraId("PF-000001"),
        ),
        date(2026, 8, 6),
        key,
    )


def request_for(*records: ScheduledOrderRecord) -> CommitRequest:
    logical_rows = sum(len(item.ordine.righe) for item in records)
    write_plan = WritePlan(
        run_id=RunId("RUN-000001"),
        created_at=instant(6),
        records=tuple(records),
        expected_record_count=len(records),
        expected_logical_row_count=logical_rows,
        idempotency_keys=tuple(item.chiave_idempotenza for item in records),
    )
    snapshot = WritePlanValidationSnapshot(
        run_id=write_plan.run_id,
        expected_record_count=len(records),
        expected_logical_row_count=logical_rows,
        checked_existing_key_count=0,
        schema_name="ORDINI",
        schema_version="1.0",
        target_name="ORDINI",
    )
    validated = ValidatedWritePlan(
        plan=write_plan,
        validated_at=instant(7),
        existing_idempotency_keys_checked=(),
        target_name="ORDINI",
        expected_schema_name="ORDINI",
        expected_schema_version="1.0",
        validation_snapshot=snapshot,
    )
    return CommitRequest(
        validated,
        instant(8),
        CommitExecutionContext(
            actor=ActorId("actor-test"),
            reason="test commit",
            correlation_id="correlation-test-001",
        ),
    )


class FakeGateway:
    def __init__(self, rows=(), headers=ORDINI_HEADERS):
        self.headers = headers
        self.rows = list(rows)
        self.header_calls = []
        self.read_calls = []
        self.append_calls = []
        self.append_error = None
        self.reconciliation_mode = "normal"

    def read_headers(self, **kwargs):
        self.header_calls.append(kwargs)
        return self.headers

    def read_rows(self, **kwargs):
        self.read_calls.append(kwargs)
        return tuple(self.rows)

    def append_rows(self, *, rows, **kwargs):
        self.append_calls.append({**kwargs, "rows": rows})
        if self.append_error is not None:
            raise self.append_error
        if self.reconciliation_mode == "missing":
            return
        self.rows.extend(rows)
        if self.reconciliation_mode == "duplicate":
            duplicate = tuple(dict(row) for row in rows)
            for row in duplicate:
                row["ORDINE_ID"] = "ORD-999999"
            self.rows.extend(duplicate)


def repository(gateway: FakeGateway) -> GoogleSheetsCommitRepository:
    return GoogleSheetsCommitRepository(gateway, "sandbox-spreadsheet", FakeClock())


def test_prepare_non_esegue_accessi_ne_append() -> None:
    gateway = FakeGateway()
    repository(gateway).prepare_commit(request_for(record(1, "key-001")))
    assert gateway.header_calls == []
    assert gateway.read_calls == []
    assert gateway.append_calls == []


def test_execute_fa_un_solo_append_e_riconcilia() -> None:
    gateway = FakeGateway()
    request = request_for(record(1, "key-001", two_lines=True))
    receipt = repository(gateway).execute_commit(request)
    assert len(gateway.append_calls) == 1
    assert len(gateway.read_calls) == 2
    assert gateway.append_calls[0]["spreadsheet_id"] == "sandbox-spreadsheet"
    assert gateway.append_calls[0]["sheet_name"] == "ORDINI"
    assert tuple(gateway.append_calls[0]["rows"][0]) == ORDINI_HEADERS
    assert all(
        set(row) == set(ORDINI_HEADERS)
        and "actor" not in row
        and "reason" not in row
        and "correlation_id" not in row
        for row in gateway.append_calls[0]["rows"]
    )
    assert receipt.appended_physical_row_count == 2
    assert receipt.expected_record_count == 1
    assert receipt.expected_logical_row_count == 2
    assert len(gateway.append_calls[0]["rows"]) == 2
    assert receipt.reconciled_idempotency_keys == ("key-001",)
    assert receipt.reconciliation_complete is True


def test_application_committer_restituisce_committed_dopo_riconciliazione() -> None:
    gateway = FakeGateway()
    request = request_for(record(1, "key-001"))
    result = ApplicationCommitter(repository(gateway)).commit(request)
    assert result.status is CommitStatus.COMMITTED
    assert result.committed_operations == 1


def test_schema_cambiato_blocca_prima_di_read_e_append() -> None:
    gateway = FakeGateway(headers=ORDINI_HEADERS[:-1])
    with pytest.raises(CommitSchemaChangedError):
        repository(gateway).execute_commit(
            request_for(record(1, "key-001"))
        )
    assert gateway.read_calls == []
    assert gateway.append_calls == []


def test_chiave_esistente_blocca_senza_append() -> None:
    existing = scheduled_orders_to_rows((record(9, "key-001"),))
    gateway = FakeGateway(rows=existing)
    with pytest.raises(CommitExistingKeyError):
        repository(gateway).execute_commit(
            request_for(record(1, "key-001"))
        )
    assert gateway.append_calls == []


@pytest.mark.parametrize("mode", ["missing", "duplicate"])
def test_riconciliazione_incompleta_non_esegue_secondo_append(mode) -> None:
    gateway = FakeGateway()
    gateway.reconciliation_mode = mode
    request = request_for(record(1, "key-001"))
    result = ApplicationCommitter(repository(gateway)).commit(request)
    assert result.status is CommitStatus.RECONCILIATION_REQUIRED
    assert len(gateway.append_calls) == 1


def test_errore_append_propagato_con_causa_e_senza_retry() -> None:
    gateway = FakeGateway()
    cause = GoogleSheetsRepositoryError("transport")
    gateway.append_error = cause
    with pytest.raises(CommitExecutionError) as captured:
        repository(gateway).execute_commit(
            request_for(record(1, "key-001"))
        )
    assert captured.value.__cause__ is cause
    assert len(gateway.append_calls) == 1


def test_ordine_record_righe_e_chiavi_preservati() -> None:
    first = record(2, "key-002", two_lines=True)
    second = record(1, "key-001")
    gateway = FakeGateway()
    repository(gateway).execute_commit(request_for(first, second))
    appended = gateway.append_calls[0]["rows"]
    assert [row["ORDINE_ID"] for row in appended] == [
        "ORD-000002",
        "ORD-000002",
        "ORD-000001",
    ]
    assert [row["POSIZIONE_RIGA"] for row in appended] == ["1", "2", "1"]
    assert [row["CHIAVE_IDEMPOTENZA"] for row in appended] == [
        "key-002",
        "key-002",
        "key-001",
    ]


def test_adapter_non_autentica_e_non_costruisce_servizi_google() -> None:
    source = __import__(
        "src.tpo_core.infrastructure.google_sheets.commit_repository",
        fromlist=["dummy"],
    )
    text = open(source.__file__, encoding="utf-8").read()
    assert "googleapiclient" not in text
    assert "build_google_sheets_service" not in text
    assert "service_account" not in text
