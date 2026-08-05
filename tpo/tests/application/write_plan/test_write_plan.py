from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.run_tracking.models import CompletedSchedulingRun
from src.tpo_core.application.scheduling.models import ScheduledOrderRecord, SchedulingResult
from src.tpo_core.application.scheduling.provenance import OrderLineProvenance
from src.tpo_core.application.write_plan import (
    DuplicateIdempotencyKeyError,
    InvalidWritePlanError,
    WritePlanBuilder,
    WritePlanConsistencyError,
    WritePlanRunMismatchError,
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
from src.tpo_core.domain.states import OrdineState, RunState
from src.tpo_core.domain.time_reference import CurrentSystemDate


TZ = ZoneInfo("Atlantic/Canary")


def current(hour=6):
    return CurrentSystemDate(datetime(2026, 8, 3, hour, tzinfo=TZ))


def line(varieta="VAR-000001", quantity=2, unit=UnitOfMeasure.SET):
    return RigaOrdine(VarietaId(varieta), Quantity(quantity, unit))


def record(identifier="ORD-000001", *, key=None, lines=None):
    order_lines = lines or (line(),)
    return ScheduledOrderRecord(
        ordine=Ordine(
            id=OrdineId(identifier),
            cliente_id=ClienteId("CLI-000001"),
            data_ordine=date(2026, 8, 3),
            righe=order_lines,
            stato=OrdineState.APERTO,
            programma_fornitura_id=ProgrammaFornituraId("PF-000001"),
        ),
        data_consegna_prevista=date(2026, 8, 6),
        chiave_idempotenza=key if key is not None else f"key-{identifier}",
        provenance=tuple(
            OrderLineProvenance(ProgrammaFornituraId("PF-000001"), 3, position, position)
            for position in range(1, len(order_lines) + 1)
        ),
    )


def scheduling(records=None, *, warnings=(), state=None, simulation=False):
    records = (record(),) if records is None else records
    state = state or (RunState.SUCCESS_WITH_WARNINGS if warnings else RunState.SUCCESS)
    return SchedulingResult(
        run_id=RunId("RUN-000001"),
        ordini_generati=records,
        anteprime=(),
        programmi_letti=1,
        righe_valutate=sum(len(item.ordine.righe) for item in records),
        occorrenze_valutate=len(records),
        occorrenze_generate=len(records),
        occorrenze_saltate_per_idempotenza=0,
        avvisi=warnings,
        simulation=simulation,
        esito=state,
    )


def completed(result=None, **changes):
    result = result or scheduling()
    values = dict(
        run_id=result.run_id,
        started_at=current(5),
        completed_at=current(6),
        simulation=result.simulation,
        state=result.esito,
        programmi_letti=result.programmi_letti,
        righe_valutate=result.righe_valutate,
        occorrenze_valutate=result.occorrenze_valutate,
        ordini_generati=result.occorrenze_generate,
        elementi_saltati=result.occorrenze_saltate_per_idempotenza,
        warnings=result.avvisi,
        errors=(),
        version=1,
    )
    values.update(changes)
    return CompletedSchedulingRun(**values)


def build(result=None, run=None):
    result = result or scheduling()
    return WritePlanBuilder().build(
        scheduling_result=result,
        completed_run=run or completed(result),
    )


def test_piano_valido_preserva_dati_applicativi() -> None:
    result = scheduling()
    plan = build(result)
    assert plan.run_id == result.run_id
    assert plan.created_at == current(6)
    assert plan.records is result.ordini_generati
    assert plan.expected_record_count == 1
    assert plan.expected_logical_row_count == 1
    assert plan.idempotency_keys == ("key-ORD-000001",)


def test_piano_immutabile() -> None:
    plan = build()
    with pytest.raises(FrozenInstanceError):
        plan.expected_record_count = 2


def test_record_e_righe_duplicate_legittime_preservate() -> None:
    repeated = line()
    records = (record(lines=(repeated, repeated)),)
    plan = build(scheduling(records))
    assert plan.records == records
    assert plan.records[0].ordine.righe == (repeated, repeated)
    assert plan.expected_logical_row_count == 2


def test_ordine_record_e_righe_preservato() -> None:
    first_line = line("VAR-000002", 3, UnitOfMeasure.GRAM)
    second_line = line("VAR-000001")
    records = (
        record("ORD-000002", lines=(first_line, second_line)),
        record("ORD-000001"),
    )
    plan = build(scheduling(records))
    assert plan.records == records
    assert plan.records[0].ordine.righe == (first_line, second_line)
    assert plan.expected_record_count == 2
    assert plan.expected_logical_row_count == 3


def test_chiavi_idempotenti_preservate_senza_ricalcolo() -> None:
    records = (
        record("ORD-000001", key="opaque-z"),
        record("ORD-000002", key="opaque-a"),
    )
    assert build(scheduling(records)).idempotency_keys == ("opaque-z", "opaque-a")


@pytest.mark.parametrize("key", ["", "   "])
def test_chiave_vuota_rifiutata(key) -> None:
    with pytest.raises(InvalidWritePlanError, match="chiave idempotente"):
        build(scheduling((record(key=key),)))


def test_chiavi_duplicate_rifiutate() -> None:
    records = (
        record("ORD-000001", key="duplicate"),
        record("ORD-000002", key="duplicate"),
    )
    with pytest.raises(DuplicateIdempotencyKeyError):
        build(scheduling(records))


def test_mismatch_run_id_rifiutato() -> None:
    result = scheduling()
    run = completed(result, run_id=RunId("RUN-000002"))
    with pytest.raises(WritePlanRunMismatchError):
        build(result, run)


def test_mismatch_simulation_rifiutato() -> None:
    result = scheduling()
    run = completed(result, simulation=True)
    with pytest.raises(WritePlanRunMismatchError):
        build(result, run)


def test_run_failed_rifiutata() -> None:
    result = scheduling(state=RunState.SUCCESS)
    run = completed(result, state=RunState.FAILED, errors=("failed",))
    with pytest.raises(InvalidWritePlanError, match="RUN FAILED"):
        build(result, run)


def test_scheduling_result_failed_rifiutato() -> None:
    result = scheduling(state=RunState.FAILED)
    run = completed(result, state=RunState.SUCCESS)
    with pytest.raises(InvalidWritePlanError, match="SchedulingResult FAILED"):
        build(result, run)


def test_risultato_in_simulazione_rifiutato() -> None:
    result = scheduling(simulation=True)
    with pytest.raises(InvalidWritePlanError, match="simulazione"):
        build(result)


def test_mismatch_esito_rifiutato() -> None:
    result = scheduling(warnings=("warning",))
    run = completed(result, state=RunState.SUCCESS, warnings=())
    with pytest.raises(WritePlanConsistencyError, match="esito"):
        build(result, run)


def test_mismatch_warning_rifiutato() -> None:
    result = scheduling(warnings=("warning result",))
    run = completed(result, warnings=("warning run",))
    with pytest.raises(WritePlanConsistencyError, match="warning"):
        build(result, run)


@pytest.mark.parametrize(
    "field",
    [
        "programmi_letti",
        "righe_valutate",
        "occorrenze_valutate",
        "ordini_generati",
        "elementi_saltati",
    ],
)
def test_mismatch_contatori_rifiutato(field) -> None:
    result = scheduling()
    run = completed(result, **{field: getattr(completed(result), field) + 1})
    with pytest.raises(WritePlanConsistencyError, match="contatori"):
        build(result, run)


def test_zero_record_rifiutato() -> None:
    result = scheduling(())
    with pytest.raises(InvalidWritePlanError, match="non contiene record"):
        build(result)


def test_numero_record_incoerente_rifiutato() -> None:
    result = replace(scheduling(), occorrenze_generate=2)
    run = completed(result)
    with pytest.raises(WritePlanConsistencyError, match="numero di record"):
        build(result, run)


def test_json_deterministico_e_semantico() -> None:
    plan = build()
    assert plan.to_json() == build().to_json()
    payload = plan.to_dict()
    item = payload["records"][0]
    assert item == {
        "chiave_idempotenza": "key-ORD-000001",
        "cliente_id": "CLI-000001",
        "data_consegna_prevista": "2026-08-06",
        "data_ordine": "2026-08-03",
        "ordine_id": "ORD-000001",
        "programma_fornitura_id": "PF-000001",
        "provenance": [{
            "order_line_position": 1,
            "programma_fornitura_id": "PF-000001",
            "programma_line_position": 1,
            "programma_version": 3,
        }],
        "righe": [
            {"quantita": "2", "unita": "SET", "varieta_id": "VAR-000001"}
        ],
    }


def test_nessuna_conoscenza_della_persistenza_fisica() -> None:
    directory = Path("src/tpo_core/application/write_plan")
    source = "\n".join(path.read_text() for path in directory.glob("*.py"))
    forbidden = (
        "ORDINI_SHEET_NAME",
        "%Y/%m/%d",
        "PROGRAMMI_HEADERS",
        "ORDINI_HEADERS",
        "Google Sheets",
        "infrastructure",
        "sheet_name",
        "row_index",
    )
    assert all(value not in source for value in forbidden)
