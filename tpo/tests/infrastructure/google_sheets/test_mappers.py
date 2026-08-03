from datetime import date

import pytest

from src.tpo_core.application.scheduling.models import ScheduledOrderRecord
from src.tpo_core.domain.entities.ordine import Ordine, RigaOrdine
from src.tpo_core.domain.identifiers import (
    ClienteId,
    OrdineId,
    ProgrammaFornituraId,
    VarietaId,
)
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import OrdineState, ProgrammaFornituraState
from src.tpo_core.infrastructure.google_sheets.errors import (
    InvalidSheetRowError,
    InvalidSheetSchemaError,
)
from src.tpo_core.infrastructure.google_sheets.mappers import (
    ORDINI_HEADERS,
    PROGRAMMI_HEADERS,
    programmi_from_rows,
    scheduled_orders_from_rows,
    scheduled_orders_to_rows,
)


def programma_row(**overrides):
    values = {
        "PROGRAMMA_FORNITURA_ID": "PF-000001",
        "CLIENTE_ID": "CLI-000001",
        "STATO": "ATTIVO",
        "DATA_INIZIO": "2026/08/03",
        "DATA_FINE": "",
        "ORARIO_GENERAZIONE": "05:00",
        "FINESTRA_OPERATIVA_GIORNI": "3",
        "POSIZIONE_RIGA": "1",
        "VARIETA_ID": "VAR-000001",
        "QUANTITA": "12.5",
        "UNITA_MISURA": "SET",
        "TIPO_RICORRENZA": "SETTIMANALE",
        "INTERVALLO_GIORNI": "",
        "GIORNI_SETTIMANA": "",
    }
    values.update(overrides)
    return {header: values[header] for header in PROGRAMMI_HEADERS}


def ordine_row(**overrides):
    values = {
        "ORDINE_ID": "ORD-000001",
        "CLIENTE_ID": "CLI-000001",
        "DATA_ORDINE": "2026/08/03",
        "STATO": "APERTO",
        "PROGRAMMA_FORNITURA_ID": "PF-000001",
        "DATA_CONSEGNA_PREVISTA": "2026/08/06",
        "CHIAVE_IDEMPOTENZA": "key-001",
        "POSIZIONE_RIGA": "1",
        "VARIETA_ID": "VAR-000001",
        "QUANTITA": "12.5",
        "UNITA_MISURA": "SET",
    }
    values.update(overrides)
    return {header: values[header] for header in ORDINI_HEADERS}


def test_programma_valido_e_formati_ufficiali() -> None:
    item = programmi_from_rows((programma_row(),))[0]
    assert item.id == ProgrammaFornituraId("PF-000001")
    assert item.stato is ProgrammaFornituraState.ATTIVO
    assert item.data_inizio == date(2026, 8, 3)
    assert item.data_fine is None
    assert item.orario_generazione.strftime("%H:%M") == "05:00"
    assert item.righe[0].quantita == Quantity("12.5", UnitOfMeasure.SET)


def test_programma_raggruppa_righe_e_preserva_posizione() -> None:
    rows = (
        programma_row(POSIZIONE_RIGA="2", VARIETA_ID="VAR-000002"),
        programma_row(POSIZIONE_RIGA="1", VARIETA_ID="VAR-000001"),
    )
    item = programmi_from_rows(rows)[0]
    assert tuple(r.varieta_id.value for r in item.righe) == ("VAR-000001", "VAR-000002")


def test_programmi_differenti_preservano_ordine_fisico_dei_gruppi() -> None:
    result = programmi_from_rows((
        programma_row(PROGRAMMA_FORNITURA_ID="PF-000002"),
        programma_row(PROGRAMMA_FORNITURA_ID="PF-000001"),
    ))
    assert tuple(item.id.value for item in result) == ("PF-000002", "PF-000001")


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("PROGRAMMA_FORNITURA_ID", "bad"),
        ("DATA_INIZIO", "2026-08-03"),
        ("ORARIO_GENERAZIONE", "5:00"),
        ("QUANTITA", "12,5"),
        ("UNITA_MISURA", "KG"),
        ("STATO", "ACTIVE"),
        ("TIPO_RICORRENZA", "ANNUALE"),
        ("POSIZIONE_RIGA", "0"),
    ],
)
def test_programma_rifiuta_valori_invalidi(column, value) -> None:
    with pytest.raises(InvalidSheetRowError):
        programmi_from_rows((programma_row(**{column: value}),))


def test_ogni_x_giorni_e_giorni_settimana_validi() -> None:
    result = programmi_from_rows((
        programma_row(TIPO_RICORRENZA="OGNI_X_GIORNI", INTERVALLO_GIORNI="5"),
        programma_row(
            POSIZIONE_RIGA="2", VARIETA_ID="VAR-000002",
            TIPO_RICORRENZA="GIORNI_SETTIMANA", GIORNI_SETTIMANA="1,3,5",
        ),
    ))[0]
    assert result.righe[0].configurazione_temporale.intervallo_giorni == 5
    assert result.righe[1].configurazione_temporale.giorni_settimana == (1, 3, 5)


@pytest.mark.parametrize(
    "overrides",
    [
        {"TIPO_RICORRENZA": "SETTIMANALE", "INTERVALLO_GIORNI": "5"},
        {"TIPO_RICORRENZA": "OGNI_X_GIORNI", "INTERVALLO_GIORNI": ""},
        {"TIPO_RICORRENZA": "SETTIMANALE", "GIORNI_SETTIMANA": "1,3"},
        {"TIPO_RICORRENZA": "GIORNI_SETTIMANA", "GIORNI_SETTIMANA": "1,8"},
    ],
)
def test_configurazione_temporale_incoerente_rifiutata(overrides) -> None:
    with pytest.raises(InvalidSheetRowError):
        programmi_from_rows((programma_row(**overrides),))


def test_conflitto_testata_programma_rifiutato() -> None:
    with pytest.raises(InvalidSheetRowError, match="incoerenti"):
        programmi_from_rows((programma_row(), programma_row(POSIZIONE_RIGA="2", CLIENTE_ID="CLI-000002")))


def test_schema_programma_mancante_rifiutato() -> None:
    row = programma_row()
    del row["QUANTITA"]
    with pytest.raises(InvalidSheetSchemaError, match="QUANTITA"):
        programmi_from_rows((row,))


def test_ordine_colonne_schema_rifiutato() -> None:
    source = ordine_row()
    reordered = {key: source[key] for key in reversed(tuple(source))}
    with pytest.raises(InvalidSheetSchemaError, match="ordine atteso"):
        scheduled_orders_from_rows((reordered,))


@pytest.mark.parametrize("value", ["", "NULL", "N/A", "-"])
def test_valori_obbligatori_e_marker_opzionali(value) -> None:
    if value == "":
        with pytest.raises(InvalidSheetRowError):
            programmi_from_rows((programma_row(QUANTITA=value),))
    else:
        with pytest.raises(InvalidSheetRowError):
            programmi_from_rows((programma_row(DATA_FINE=value),))


def test_ordine_valido_con_piu_righe_e_duplicati_preservati() -> None:
    same = ordine_row(POSIZIONE_RIGA="2")
    record = scheduled_orders_from_rows((same, ordine_row(POSIZIONE_RIGA="1")))[0]
    assert record.ordine.id == OrdineId("ORD-000001")
    assert len(record.ordine.righe) == 2
    assert record.ordine.righe[0] == record.ordine.righe[1]
    assert record.chiave_idempotenza == "key-001"
    assert record.data_consegna_prevista == date(2026, 8, 6)


def test_ordini_differenti_preservano_ordine() -> None:
    records = scheduled_orders_from_rows((
        ordine_row(ORDINE_ID="ORD-000002", CHIAVE_IDEMPOTENZA="key-2"),
        ordine_row(ORDINE_ID="ORD-000001", CHIAVE_IDEMPOTENZA="key-1"),
    ))
    assert tuple(record.ordine.id.value for record in records) == ("ORD-000002", "ORD-000001")


def test_conflitto_testata_ordine_rifiutato() -> None:
    with pytest.raises(InvalidSheetRowError, match="incoerenti"):
        scheduled_orders_from_rows((ordine_row(), ordine_row(POSIZIONE_RIGA="2", STATO="EVASO")))


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("ORDINE_ID", "bad"),
        ("DATA_ORDINE", "03/08/2026"),
        ("STATO", "NUOVO"),
        ("VARIETA_ID", "bad"),
        ("QUANTITA", "x"),
        ("QUANTITA", "-1"),
        ("UNITA_MISURA", "KG"),
        ("CHIAVE_IDEMPOTENZA", ""),
    ],
)
def test_ordine_rifiuta_valori_invalidi(column, value) -> None:
    with pytest.raises(InvalidSheetRowError):
        scheduled_orders_from_rows((ordine_row(**{column: value}),))


def test_serializzazione_ordine_preserva_ordine_chiave_e_formati() -> None:
    ordine = Ordine(
        OrdineId("ORD-000001"), ClienteId("CLI-000001"), date(2026, 8, 3),
        (
            RigaOrdine(VarietaId("VAR-000002"), Quantity("12.50", UnitOfMeasure.GRAM)),
            RigaOrdine(VarietaId("VAR-000001"), Quantity("2", UnitOfMeasure.UNIT)),
        ),
        OrdineState.APERTO, ProgrammaFornituraId("PF-000001"),
    )
    record = ScheduledOrderRecord(ordine, date(2026, 8, 6), "original-key")
    rows = scheduled_orders_to_rows((record,))
    assert tuple(row["POSIZIONE_RIGA"] for row in rows) == ("1", "2")
    assert tuple(row["VARIETA_ID"] for row in rows) == ("VAR-000002", "VAR-000001")
    assert rows[0]["QUANTITA"] == "12.5"
    assert rows[0]["DATA_ORDINE"] == "2026/08/03"
    assert rows[0]["CHIAVE_IDEMPOTENZA"] == "original-key"
