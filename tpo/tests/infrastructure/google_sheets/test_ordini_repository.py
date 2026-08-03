from datetime import date

from src.tpo_core.application.scheduling.models import ScheduledOrderRecord
from src.tpo_core.domain.entities.ordine import Ordine, RigaOrdine
from src.tpo_core.domain.identifiers import ClienteId, OrdineId, ProgrammaFornituraId, VarietaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import OrdineState
from src.tpo_core.infrastructure.google_sheets.mappers import ORDINI_HEADERS
from src.tpo_core.infrastructure.google_sheets.ordini_repository import GoogleSheetsOrdineRepository


class FakeGateway:
    def __init__(self, rows=(), read_error=None, write_error=None):
        self.rows = rows
        self.read_error = read_error
        self.write_error = write_error
        self.reads = []
        self.writes = []

    def read_rows(self, **kwargs):
        self.reads.append(kwargs)
        if self.read_error:
            raise self.read_error
        return self.rows

    def append_rows(self, **kwargs):
        self.writes.append(kwargs)
        if self.write_error:
            raise self.write_error


def row():
    return dict(zip(ORDINI_HEADERS, (
        "ORD-000001", "CLI-000001", "2026/08/03", "APERTO", "PF-000001",
        "2026/08/06", "saved-key", "1", "VAR-000001", "10", "SET",
    )))


def record(identifier="ORD-000001", key="original-key", varieta="VAR-000001"):
    ordine = Ordine(
        OrdineId(identifier), ClienteId("CLI-000001"), date(2026, 8, 3),
        (RigaOrdine(VarietaId(varieta), Quantity(10, UnitOfMeasure.SET)),),
        OrdineState.APERTO, ProgrammaFornituraId("PF-000001"),
    )
    return ScheduledOrderRecord(ordine, date(2026, 8, 6), key)


def test_legge_record_esistenti_una_volta() -> None:
    gateway = FakeGateway((row(),))
    result = GoogleSheetsOrdineRepository("spreadsheet", gateway).list_scheduled_orders()
    assert result[0].chiave_idempotenza == "saved-key"
    assert gateway.reads == [{"spreadsheet_id": "spreadsheet", "sheet_name": "ORDINI"}]


def test_append_preserva_ordine_record_righe_e_chiavi() -> None:
    gateway = FakeGateway()
    records = (record("ORD-000002", "key-2", "VAR-000002"), record("ORD-000001", "key-1"))
    before = records
    GoogleSheetsOrdineRepository("spreadsheet", gateway).add_scheduled_orders(records)
    appended = gateway.writes[0]["rows"]
    assert tuple(item["ORDINE_ID"] for item in appended) == ("ORD-000002", "ORD-000001")
    assert tuple(item["CHIAVE_IDEMPOTENZA"] for item in appended) == ("key-2", "key-1")
    assert records == before


def test_tuple_vuota_non_scrive() -> None:
    gateway = FakeGateway()
    GoogleSheetsOrdineRepository("id", gateway).add_scheduled_orders(())
    assert gateway.writes == []


def test_configurazione_append_inoltrata() -> None:
    gateway = FakeGateway()
    GoogleSheetsOrdineRepository("sheet-id", gateway, "CUSTOM").add_scheduled_orders((record(),))
    assert gateway.writes[0]["spreadsheet_id"] == "sheet-id"
    assert gateway.writes[0]["sheet_name"] == "CUSTOM"


def test_errori_gateway_propagati() -> None:
    read_error = RuntimeError("read")
    write_error = RuntimeError("write")
    try:
        GoogleSheetsOrdineRepository("id", FakeGateway(read_error=read_error)).list_scheduled_orders()
    except RuntimeError as raised:
        assert raised is read_error
    else:
        raise AssertionError("Errore lettura non propagato")
    try:
        GoogleSheetsOrdineRepository("id", FakeGateway(write_error=write_error)).add_scheduled_orders((record(),))
    except RuntimeError as raised:
        assert raised is write_error
    else:
        raise AssertionError("Errore scrittura non propagato")


def test_nessuna_generazione_id_o_ricalcolo_chiave() -> None:
    repository = GoogleSheetsOrdineRepository("id", FakeGateway())
    assert not hasattr(repository, "next_id")
    assert not hasattr(repository, "_chiave_idempotenza")
