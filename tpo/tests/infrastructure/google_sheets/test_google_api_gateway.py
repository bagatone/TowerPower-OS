from copy import deepcopy
from types import SimpleNamespace

import pytest
from googleapiclient.errors import HttpError

from src.tpo_core.infrastructure.google_sheets.errors import (
    GoogleSheetsRepositoryError,
    InvalidSheetRowError,
    InvalidSheetSchemaError,
)
from src.tpo_core.infrastructure.google_sheets.google_api_gateway import (
    GoogleApiSheetsGateway,
)
from src.tpo_core.infrastructure.google_sheets.mappers import (
    ORDINI_HEADERS,
    PROGRAMMI_HEADERS,
)
from src.tpo_core.infrastructure.google_sheets.ordini_repository import (
    GoogleSheetsOrdineRepository,
)
from src.tpo_core.infrastructure.google_sheets.programmi_repository import (
    GoogleSheetsProgrammaFornituraRepository,
)


def http_error():
    return HttpError(SimpleNamespace(status=500, reason="failure"), b'{"error": {"message": "secret"}}')


class FakeRequest:
    def __init__(self, response=None, error=None):
        self.response = response if response is not None else {}
        self.error = error

    def execute(self):
        if self.error is not None:
            raise self.error
        return self.response


class FakeGoogleService:
    def __init__(self, values=None, get_error=None, append_error=None):
        self.values_response = values if values is not None else []
        self.get_error = get_error
        self.append_error = append_error
        self.get_calls = []
        self.append_calls = []

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return FakeRequest({"values": self.values_response}, self.get_error)

    def append(self, **kwargs):
        self.append_calls.append(kwargs)
        return FakeRequest({}, self.append_error)


class FakeMetadataService:
    def __init__(self, response=None, error=None):
        self.response = response or {"sheets": []}
        self.error = error
        self.calls = []

    def spreadsheets(self):
        return self

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return FakeRequest(self.response, self.error)


def gateway(values=None, **kwargs):
    service = FakeGoogleService(values, **kwargs)
    return GoogleApiSheetsGateway(service), service


def test_legge_intestazioni_e_una_riga() -> None:
    target, service = gateway([["A", "B"], ["1", "2"]])
    result = target.read_rows(spreadsheet_id="spreadsheet", sheet_name="Sheet")
    assert result == ({"A": "1", "B": "2"},)
    assert tuple(result[0]) == ("A", "B")
    assert service.get_calls == [{"spreadsheetId": "spreadsheet", "range": "'Sheet'!A:ZZ"}]


def test_legge_piu_righe_nell_ordine_fisico() -> None:
    target, _ = gateway([["A"], ["first"], ["second"]])
    assert target.read_rows(spreadsheet_id="id", sheet_name="S") == (
        {"A": "first"}, {"A": "second"}
    )


def test_riempie_celle_finali_mancanti() -> None:
    target, _ = gateway([["A", "B", "C"], ["1"]])
    assert target.read_rows(spreadsheet_id="id", sheet_name="S") == (
        {"A": "1", "B": "", "C": ""},
    )


def test_ignora_solo_righe_fisiche_completamente_vuote() -> None:
    target, _ = gateway([["A", "B"], [], ["", ""], [" ", ""]])
    assert target.read_rows(spreadsheet_id="id", sheet_name="S") == (
        {"A": " ", "B": ""},
    )


def test_non_normalizza_intestazioni_o_valori() -> None:
    target, _ = gateway([[" A ", "B"], [" value ", 12]])
    assert target.read_rows(spreadsheet_id="id", sheet_name="S") == (
        {" A ": " value ", "B": "12"},
    )


def test_foglio_vuoto_restituisce_tuple_vuota() -> None:
    target, _ = gateway([])
    assert target.read_rows(spreadsheet_id="id", sheet_name="S") == ()


def test_legge_intestazioni_fisiche() -> None:
    target, _ = gateway([["A", "B"], ["1", "2"]])
    assert target.read_headers(spreadsheet_id="id", sheet_name="S") == ("A", "B")


def test_intestazioni_mancanti_rifiutate_da_read_headers() -> None:
    target, _ = gateway([])
    with pytest.raises(InvalidSheetSchemaError, match="mancante"):
        target.read_headers(spreadsheet_id="id", sheet_name="S")


def test_lista_nomi_fogli_da_metadata() -> None:
    service = FakeMetadataService(
        {"sheets": [{"properties": {"title": "PROGRAMMI_FORNITURA"}}, {"properties": {"title": "ORDINI"}}]}
    )
    target = GoogleApiSheetsGateway(service)
    assert target.list_sheet_names(spreadsheet_id="spreadsheet") == (
        "PROGRAMMI_FORNITURA", "ORDINI"
    )
    assert service.calls == [{
        "spreadsheetId": "spreadsheet",
        "fields": "sheets.properties.title",
    }]


def test_errore_metadata_maschera_spreadsheet_id() -> None:
    service = FakeMetadataService(error=http_error())
    target = GoogleApiSheetsGateway(service)
    with pytest.raises(GoogleSheetsRepositoryError) as raised:
        target.list_sheet_names(spreadsheet_id="secret-spreadsheet-id")
    assert "secret-spreadsheet-id" not in str(raised.value)
    assert "se***id" in str(raised.value)


@pytest.mark.parametrize("values", [[[]], [["", "B"]], [["A", "A"]]])
def test_intestazioni_invalidе_rifiutate(values) -> None:
    target, _ = gateway(values)
    with pytest.raises(InvalidSheetSchemaError):
        target.read_rows(spreadsheet_id="id", sheet_name="S")


def test_riga_con_piu_celle_delle_intestazioni_rifiutata() -> None:
    target, _ = gateway([["A"], ["1", "2"]])
    with pytest.raises(InvalidSheetRowError, match="più celle"):
        target.read_rows(spreadsheet_id="id", sheet_name="S")


def test_nome_foglio_con_spazi_e_apostrofo_quotato_in_a1() -> None:
    target, service = gateway([["A"], ["1"]])
    target.read_rows(spreadsheet_id="id", sheet_name="Client's Orders")
    assert service.get_calls[0]["range"] == "'Client''s Orders'!A:ZZ"


def test_append_tuple_vuota_non_chiama_google() -> None:
    target, service = gateway([["A"]])
    target.append_rows(spreadsheet_id="id", sheet_name="S", rows=())
    assert service.get_calls == []
    assert service.append_calls == []


def test_append_una_riga_raw_nell_ordine_intestazioni() -> None:
    target, service = gateway([["A", "B"]])
    target.append_rows(
        spreadsheet_id="id", sheet_name="S", rows=({"A": "1", "B": "2"},)
    )
    assert len(service.append_calls) == 1
    call = service.append_calls[0]
    assert call["valueInputOption"] == "RAW"
    assert call["insertDataOption"] == "INSERT_ROWS"
    assert call["body"] == {"values": [["1", "2"]]}
    assert call["range"] == "'S'!A:ZZ"


def test_append_piu_righe_una_sola_chiamata_e_ordine_preservato() -> None:
    target, service = gateway([["A", "B"]])
    rows = ({"A": "first", "B": "1"}, {"A": "second", "B": "2"})
    before = deepcopy(rows)
    target.append_rows(spreadsheet_id="id", sheet_name="S", rows=rows)
    assert service.append_calls[0]["body"]["values"] == [["first", "1"], ["second", "2"]]
    assert rows == before


@pytest.mark.parametrize(
    "row",
    [
        {"A": "1"},
        {"A": "1", "B": "2", "C": "3"},
        {"B": "2", "A": "1"},
    ],
)
def test_append_schema_mancante_inatteso_o_disordinato_rifiutato(row) -> None:
    target, service = gateway([["A", "B"]])
    with pytest.raises(InvalidSheetSchemaError):
        target.append_rows(spreadsheet_id="id", sheet_name="S", rows=(row,))
    assert service.append_calls == []


def test_append_valore_non_stringa_rifiutato() -> None:
    target, _ = gateway([["A"]])
    with pytest.raises(InvalidSheetRowError, match="stringhe"):
        target.append_rows(spreadsheet_id="id", sheet_name="S", rows=({"A": 1},))


def test_append_foglio_senza_schema_rifiutato() -> None:
    target, service = gateway([])
    with pytest.raises(InvalidSheetSchemaError, match="foglio vuoto"):
        target.append_rows(spreadsheet_id="id", sheet_name="S", rows=({"A": "1"},))
    assert service.append_calls == []


def test_errore_google_lettura_contestualizzato_e_id_mascherato() -> None:
    target, _ = gateway(get_error=http_error())
    with pytest.raises(GoogleSheetsRepositoryError) as raised:
        target.read_rows(spreadsheet_id="secret-spreadsheet-id", sheet_name="ORDINI")
    message = str(raised.value)
    assert "lettura" in message
    assert "ORDINI" in message
    assert "secret-spreadsheet-id" not in message
    assert "se***id" in message
    assert "secret" not in message


def test_errore_google_append_propagato_con_contesto() -> None:
    target, _ = gateway([["A"]], append_error=http_error())
    with pytest.raises(GoogleSheetsRepositoryError, match="append"):
        target.append_rows(spreadsheet_id="spreadsheet", sheet_name="S", rows=({"A": "1"},))


def programma_values():
    return [
        list(PROGRAMMI_HEADERS),
        [
            "PF-000001", "CLI-000001", "ATTIVO", "2026/08/03", "",
            "05:00", "3", "1", "VAR-000001", "10", "SET",
            "SETTIMANALE", "", "",
        ],
    ]


def test_integrazione_locale_programmi_repository() -> None:
    target, _ = gateway(programma_values())
    repository = GoogleSheetsProgrammaFornituraRepository("id", target)
    assert repository.list_for_scheduling()[0].id.value == "PF-000001"


def test_integrazione_locale_ordini_repository_lettura_e_append() -> None:
    order_values = [
        list(ORDINI_HEADERS),
        [
            "ORD-000001", "CLI-000001", "2026/08/03", "APERTO",
            "PF-000001", "2026/08/06", "key", "1", "VAR-000001", "10", "SET",
        ],
    ]
    target, service = gateway(order_values)
    repository = GoogleSheetsOrdineRepository("id", target)
    records = repository.list_scheduled_orders()
    repository.add_scheduled_orders(records)
    assert service.append_calls[0]["body"]["values"][0][6] == "key"


def test_gateway_non_conosce_domain_engine_clock_o_schema_congelato() -> None:
    import src.tpo_core.infrastructure.google_sheets.google_api_gateway as module

    names = set(module.__dict__)
    for forbidden in (
        "Ordine", "ProgrammaFornitura", "SchedulingEngine", "datetime",
        "PROGRAMMI_HEADERS", "ORDINI_HEADERS", "PROGRAMMI_FORNITURA", "ORDINI",
    ):
        assert forbidden not in names
    target, _ = gateway([])
    assert not hasattr(target, "clock")
    assert not hasattr(target, "repository")
