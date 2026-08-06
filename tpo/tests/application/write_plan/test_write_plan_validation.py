from dataclasses import FrozenInstanceError
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.scheduling.models import ScheduledOrderRecord
from src.tpo_core.application.scheduling.provenance import OrderLineProvenance
from src.tpo_core.application.write_plan import (
    DuplicateWritePlanKeyError,
    DuplicateWritePlanRecordError,
    ExistingIdempotencyKeyError,
    InvalidWritePlanError,
    InvalidWriteTargetSnapshotError,
    WRITE_SCHEMA_ORDINI,
    WRITE_SCHEMA_VERSION,
    WRITE_TARGET_ORDINI,
    WritePlan,
    WritePlanCountMismatchError,
    WritePlanValidationError,
    WritePlanValidationSnapshot,
    WritePlanValidator,
    WriteSchemaMismatchError,
    WriteTargetMismatchError,
    WriteTargetSnapshot,
)
from src.tpo_core.domain.entities.ordine import Ordine, RigaOrdine
from src.tpo_core.domain.identifiers import (
    ClienteId,
    OrdineId,
    ProgrammaFornituraId,
    RunId,
    VarietaId,
)
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import OrdineCreationType, OrdineState
from src.tpo_core.domain.time_reference import CurrentSystemDate


TZ = ZoneInfo("Atlantic/Canary")


def instant(hour=7):
    return CurrentSystemDate(datetime(2026, 8, 3, hour, tzinfo=TZ))


def line(varieta="VAR-000001"):
    return RigaOrdine(VarietaId(varieta), Quantity(2, UnitOfMeasure.SET))


def record(identifier="ORD-000001", key=None, lines=None):
    order_lines = lines or (line(),)
    return ScheduledOrderRecord(
        Ordine(
            OrdineId(identifier),
            ClienteId("CLI-000001"),
            date(2026, 8, 3),
            order_lines,
            OrdineState.APERTO,
            OrdineCreationType.AUTOMATICO,
            ProgrammaFornituraId("PF-000001"),
        ),
        date(2026, 8, 6),
        key if key is not None else f"key-{identifier}",
        tuple(
            OrderLineProvenance(ProgrammaFornituraId("PF-000001"), 3, position, position)
            for position in range(1, len(order_lines) + 1)
        ),
    )


def plan(records=None, warnings=()):
    records = records or (record(),)
    return WritePlan(
        run_id=RunId("RUN-000001"),
        created_at=instant(6),
        records=records,
        expected_record_count=len(records),
        expected_logical_row_count=sum(len(item.ordine.righe) for item in records),
        idempotency_keys=tuple(item.chiave_idempotenza for item in records),
        warnings=warnings,
    )


def target(**changes):
    values = dict(
        target_name=WRITE_TARGET_ORDINI,
        schema_name=WRITE_SCHEMA_ORDINI,
        schema_version=WRITE_SCHEMA_VERSION,
        existing_idempotency_keys=("existing-a", "existing-b"),
    )
    values.update(changes)
    return WriteTargetSnapshot(**values)


class FakeValidationRepository:
    def __init__(self, snapshot=None, error=None):
        self.snapshot = snapshot or target()
        self.error = error
        self.calls = []

    def get_target_snapshot(self, *, target_name):
        self.calls.append(target_name)
        if self.error is not None:
            raise self.error
        return self.snapshot


def validate(source=None, repository=None, **changes):
    source = source or plan()
    repository = repository or FakeValidationRepository()
    arguments = dict(
        plan=source,
        validated_at=instant(),
        expected_target_name=WRITE_TARGET_ORDINI,
        expected_schema_name=WRITE_SCHEMA_ORDINI,
        expected_schema_version=WRITE_SCHEMA_VERSION,
    )
    arguments.update(changes)
    return WritePlanValidator(repository).validate(**arguments)


def test_write_target_snapshot_valido_e_immutabile() -> None:
    snapshot = target()
    assert snapshot.existing_idempotency_keys == ("existing-a", "existing-b")
    with pytest.raises(FrozenInstanceError):
        snapshot.schema_version = "2.0"


@pytest.mark.parametrize(
    "changes",
    [
        {"target_name": ""},
        {"schema_name": ""},
        {"schema_version": ""},
        {"existing_idempotency_keys": ("",)},
        {"existing_idempotency_keys": ("same", "same")},
    ],
)
def test_snapshot_invalido_rifiutato(changes) -> None:
    with pytest.raises(InvalidWriteTargetSnapshotError):
        target(**changes)


def test_validated_write_plan_valido_immutabile_e_prove_complete() -> None:
    validated = validate()
    assert validated.plan == plan()
    assert validated.target_name == WRITE_TARGET_ORDINI
    assert validated.existing_idempotency_keys_checked == (
        "existing-a", "existing-b"
    )
    assert validated.validation_snapshot == WritePlanValidationSnapshot(
        run_id=RunId("RUN-000001"),
        expected_record_count=1,
        expected_logical_row_count=1,
        checked_existing_key_count=2,
        schema_name=WRITE_SCHEMA_ORDINI,
        schema_version=WRITE_SCHEMA_VERSION,
        target_name=WRITE_TARGET_ORDINI,
    )
    with pytest.raises(FrozenInstanceError):
        validated.target_name = "ALTRO"


def test_json_deterministico_e_semantico() -> None:
    first = validate()
    second = validate()
    assert first.to_json() == second.to_json()
    payload = first.to_dict()
    assert payload["run_id"] == "RUN-000001"
    assert payload["validated_at"] == "2026-08-03T07:00:00+01:00"
    assert payload["target_name"] == "ORDINI"
    assert payload["schema_name"] == "ORDINI"
    assert payload["schema_version"] == "1.0"
    assert payload["record_count"] == 1
    assert payload["logical_row_count"] == 1
    assert payload["existing_key_count_checked"] == 2


def test_piano_valido_preserva_ordine_record_chiavi_e_data_validazione() -> None:
    records = (
        record("ORD-000002", "z", (line("VAR-000002"), line())),
        record("ORD-000001", "a"),
    )
    source = plan(records, warnings=("warning",))
    validated_at = instant(9)
    validated = validate(source, validated_at=validated_at)
    assert validated.plan is source
    assert validated.plan.records == records
    assert validated.plan.idempotency_keys == ("z", "a")
    assert validated.plan.records[0].ordine.righe == (
        line("VAR-000002"), line()
    )
    assert validated.warnings == ("warning",)
    assert validated.validated_at is validated_at


def test_righe_prodotto_duplicate_legittime_preservate() -> None:
    repeated = line()
    source = plan((record(lines=(repeated, repeated)),))
    validated = validate(source)
    assert validated.plan.records[0].ordine.righe == (repeated, repeated)
    assert validated.plan.expected_logical_row_count == 2


def test_target_mismatch() -> None:
    repository = FakeValidationRepository(target(target_name="ALTRO"))
    with pytest.raises(WriteTargetMismatchError):
        validate(repository=repository)


def test_schema_name_mismatch() -> None:
    repository = FakeValidationRepository(target(schema_name="ALTRO"))
    with pytest.raises(WriteSchemaMismatchError, match="nome"):
        validate(repository=repository)


def test_schema_version_mismatch() -> None:
    repository = FakeValidationRepository(target(schema_version="2.0"))
    with pytest.raises(WriteSchemaMismatchError, match="versione"):
        validate(repository=repository)


def test_expected_record_count_incoerente() -> None:
    source = plan()
    object.__setattr__(source, "expected_record_count", 2)
    with pytest.raises(WritePlanCountMismatchError):
        validate(source)


def test_expected_logical_row_count_incoerente() -> None:
    source = plan()
    object.__setattr__(source, "expected_logical_row_count", 2)
    with pytest.raises(WritePlanCountMismatchError):
        validate(source)


def test_chiavi_dichiarate_incoerenti() -> None:
    source = plan()
    object.__setattr__(source, "idempotency_keys", ("different",))
    with pytest.raises(InvalidWritePlanError, match="non coincidono"):
        validate(source)


@pytest.mark.parametrize("key", ["", "   "])
def test_chiave_vuota_nel_record(key) -> None:
    source = plan()
    object.__setattr__(source.records[0], "chiave_idempotenza", key)
    with pytest.raises(InvalidWritePlanError, match="vuota"):
        validate(source)


def test_chiave_duplicata_nel_piano() -> None:
    records = (record("ORD-000001", "same"), record("ORD-000002", "other"))
    source = plan(records)
    object.__setattr__(source.records[1], "chiave_idempotenza", "same")
    object.__setattr__(source, "idempotency_keys", ("same", "same"))
    with pytest.raises(DuplicateWritePlanKeyError):
        validate(source)


def test_record_duplicato_per_stesso_ordine_logico() -> None:
    records = (record("ORD-000001", "a"), record("ORD-000002", "b"))
    source = plan(records)
    object.__setattr__(source.records[1].ordine, "id", OrdineId("ORD-000001"))
    with pytest.raises(DuplicateWritePlanRecordError):
        validate(source)


def test_chiave_gia_esistente_blocca_intero_piano() -> None:
    repository = FakeValidationRepository(
        target(existing_idempotency_keys=("key-ORD-000001",))
    )
    with pytest.raises(ExistingIdempotencyKeyError):
        validate(repository=repository)


def test_write_plan_non_modificato_e_repository_chiamato_una_volta() -> None:
    source = plan()
    before = source
    repository = FakeValidationRepository()
    validate(source, repository)
    assert source == before
    assert repository.calls == [WRITE_TARGET_ORDINI]


def test_errore_repository_propagato_senza_retry() -> None:
    expected = RuntimeError("repository")
    repository = FakeValidationRepository(error=expected)
    with pytest.raises(RuntimeError, match="repository"):
        validate(repository=repository)
    assert repository.calls == [WRITE_TARGET_ORDINI]


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("expected_target_name", ""),
        ("expected_schema_name", ""),
        ("expected_schema_version", ""),
        ("validated_at", None),
    ],
)
def test_argomenti_non_validi(argument, value) -> None:
    with pytest.raises(WritePlanValidationError):
        validate(**{argument: value})


def test_architettura_priva_di_infrastruttura_e_dati_fisici() -> None:
    directory = Path("src/tpo_core/application/write_plan")
    source = "\n".join(path.read_text() for path in directory.glob("*.py"))
    forbidden = (
        "tpo_core.infrastructure",
        "googleapiclient",
        "spreadsheet_id",
        "credentials",
        "yaml",
        "A1",
        "%Y/%m/%d",
        "ORDINI_HEADERS",
        "PROGRAMMI_HEADERS",
        "validated=True",
        "validated: bool",
        "datetime.now",
        "date.today",
    )
    assert all(value not in source for value in forbidden)
