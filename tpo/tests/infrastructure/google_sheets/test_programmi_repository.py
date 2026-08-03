from src.tpo_core.infrastructure.google_sheets.mappers import PROGRAMMI_HEADERS
from src.tpo_core.infrastructure.google_sheets.programmi_repository import (
    GoogleSheetsProgrammaFornituraRepository,
)


class FakeGateway:
    def __init__(self, rows=(), error=None):
        self.rows = rows
        self.error = error
        self.reads = []
        self.writes = []

    def read_rows(self, **kwargs):
        self.reads.append(kwargs)
        if self.error:
            raise self.error
        return self.rows

    def append_rows(self, **kwargs):
        self.writes.append(kwargs)


def row(state="ATTIVO"):
    values = (
        "PF-000001", "CLI-000001", state, "2026/08/03", "", "05:00",
        "3", "1", "VAR-000001", "10", "SET", "SETTIMANALE", "", "",
    )
    return dict(zip(PROGRAMMI_HEADERS, values))


def test_repository_legge_una_volta_e_inoltra_configurazione() -> None:
    gateway = FakeGateway((row(),))
    repository = GoogleSheetsProgrammaFornituraRepository("spreadsheet", gateway)
    result = repository.list_for_scheduling()
    assert isinstance(result, tuple)
    assert gateway.reads == [{"spreadsheet_id": "spreadsheet", "sheet_name": "PROGRAMMI_FORNITURA"}]
    assert gateway.writes == []


def test_repository_non_filtra_stati() -> None:
    gateway = FakeGateway((row("ATTIVO"), {**row("SOSPESO"), "PROGRAMMA_FORNITURA_ID": "PF-000002"}))
    result = GoogleSheetsProgrammaFornituraRepository("id", gateway).list_for_scheduling()
    assert tuple(item.stato.value for item in result) == ("ATTIVO", "SOSPESO")


def test_nome_foglio_personalizzato_inoltrato() -> None:
    gateway = FakeGateway()
    GoogleSheetsProgrammaFornituraRepository("id", gateway, "CUSTOM").list_for_scheduling()
    assert gateway.reads[0]["sheet_name"] == "CUSTOM"


def test_errore_gateway_propagato() -> None:
    error = RuntimeError("gateway")
    gateway = FakeGateway(error=error)
    try:
        GoogleSheetsProgrammaFornituraRepository("id", gateway).list_for_scheduling()
    except RuntimeError as raised:
        assert raised is error
    else:
        raise AssertionError("Errore Gateway non propagato")


def test_repository_non_espone_logica_di_dominio() -> None:
    repository = GoogleSheetsProgrammaFornituraRepository("id", FakeGateway())
    assert not hasattr(repository, "_ricorre")
    assert not hasattr(repository, "next_id")
