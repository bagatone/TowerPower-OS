"""Mapper deterministici per il Physical Schema Freeze v1.0."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Callable, TypeVar

from ...application.scheduling.models import ScheduledOrderRecord
from ...domain.entities.ordine import Ordine, RigaOrdine
from ...domain.entities.programma_fornitura import (
    ConfigurazioneTemporale,
    ProgrammaFornitura,
    RigaProgrammaFornitura,
    TipoRicorrenza,
)
from ...domain.errors import DomainError
from ...domain.identifiers import (
    ClienteId,
    OrdineId,
    ProgrammaFornituraId,
    VarietaId,
)
from ...domain.quantities import Quantity, UnitOfMeasure
from ...domain.states import OrdineCreationType, OrdineState, ProgrammaFornituraState
from .errors import InvalidSheetRowError, InvalidSheetSchemaError


PROGRAMMI_SHEET_NAME = "PROGRAMMI_FORNITURA"
ORDINI_SHEET_NAME = "ORDINI"

PROGRAMMI_HEADERS = (
    "PROGRAMMA_FORNITURA_ID", "CLIENTE_ID", "STATO", "DATA_INIZIO",
    "DATA_FINE", "ORARIO_GENERAZIONE", "FINESTRA_OPERATIVA_GIORNI",
    "POSIZIONE_RIGA", "VARIETA_ID", "QUANTITA", "UNITA_MISURA",
    "TIPO_RICORRENZA", "INTERVALLO_GIORNI", "GIORNI_SETTIMANA",
)
ORDINI_HEADERS = (
    "ORDINE_ID", "CLIENTE_ID", "DATA_ORDINE", "STATO",
    "PROGRAMMA_FORNITURA_ID", "DATA_CONSEGNA_PREVISTA",
    "CHIAVE_IDEMPOTENZA", "POSIZIONE_RIGA", "VARIETA_ID", "QUANTITA",
    "UNITA_MISURA",
)

T = TypeVar("T")
_FORBIDDEN_OPTIONAL = {"NULL", "N/A", "-"}


def _location(sheet: str, row: int, column: str, value: object) -> str:
    return f"{sheet} riga {row}, colonna {column}, valore {value!r}"


def _validate_schema(row: dict[str, str], headers: tuple[str, ...], sheet: str, number: int) -> None:
    actual = tuple(row.keys())
    missing = [header for header in headers if header not in row]
    unexpected = [header for header in actual if header not in headers]
    if missing or unexpected or actual != headers:
        raise InvalidSheetSchemaError(
            f"{sheet} riga {number}: schema non valido; "
            f"colonne mancanti={missing}, colonne inattese={unexpected}, "
            f"ordine atteso={list(headers)}, ordine trovato={list(actual)}."
        )


def _required(row: dict[str, str], column: str, sheet: str, number: int) -> str:
    value = row[column]
    if not isinstance(value, str) or not value.strip():
        raise InvalidSheetRowError(f"Campo obbligatorio vuoto: {_location(sheet, number, column, value)}.")
    return value.strip()


def _optional(row: dict[str, str], column: str, sheet: str, number: int) -> str:
    value = row[column]
    if not isinstance(value, str):
        raise InvalidSheetRowError(f"Valore non testuale: {_location(sheet, number, column, value)}.")
    stripped = value.strip()
    if stripped.upper() in _FORBIDDEN_OPTIONAL:
        raise InvalidSheetRowError(f"Marcatore opzionale vietato: {_location(sheet, number, column, value)}.")
    return stripped


def _parse(factory: Callable[[str], T], value: str, sheet: str, row: int, column: str) -> T:
    try:
        return factory(value)
    except (DomainError, ValueError, TypeError) as exc:
        raise InvalidSheetRowError(f"Valore non valido: {_location(sheet, row, column, value)}.") from exc


def _parse_date(value: str, sheet: str, row: int, column: str) -> date:
    try:
        parsed = datetime.strptime(value, "%Y/%m/%d").date()
    except ValueError as exc:
        raise InvalidSheetRowError(f"Data non valida: {_location(sheet, row, column, value)}.") from exc
    if parsed.strftime("%Y/%m/%d") != value:
        raise InvalidSheetRowError(f"Formato data non canonico: {_location(sheet, row, column, value)}.")
    return parsed


def _parse_time(value: str, sheet: str, row: int, column: str) -> time:
    try:
        parsed = datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise InvalidSheetRowError(f"Orario non valido: {_location(sheet, row, column, value)}.") from exc
    if parsed.strftime("%H:%M") != value:
        raise InvalidSheetRowError(f"Formato orario non canonico: {_location(sheet, row, column, value)}.")
    return parsed


def _parse_int(value: str, sheet: str, row: int, column: str, *, minimum: int) -> int:
    if not value.isdigit():
        raise InvalidSheetRowError(f"Intero non valido: {_location(sheet, row, column, value)}.")
    parsed = int(value)
    if parsed < minimum:
        raise InvalidSheetRowError(f"Intero fuori intervallo: {_location(sheet, row, column, value)}.")
    return parsed


def _parse_decimal(value: str, sheet: str, row: int) -> Decimal:
    if "," in value:
        raise InvalidSheetRowError(f"Separatore decimale non valido: {_location(sheet, row, 'QUANTITA', value)}.")
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise InvalidSheetRowError(f"Decimal non valido: {_location(sheet, row, 'QUANTITA', value)}.") from exc
    if not parsed.is_finite():
        raise InvalidSheetRowError(f"Decimal non finito: {_location(sheet, row, 'QUANTITA', value)}.")
    return parsed


def _enum(enum_type, value: str, sheet: str, row: int, column: str):
    try:
        return enum_type(value)
    except ValueError as exc:
        raise InvalidSheetRowError(f"Enum non valido: {_location(sheet, row, column, value)}.") from exc


def _consistent(group: list[tuple[int, dict[str, str]]], columns: tuple[str, ...], sheet: str) -> None:
    first_number, first = group[0]
    for number, row in group[1:]:
        for column in columns:
            if row[column] != first[column]:
                raise InvalidSheetRowError(
                    f"Dati di testata incoerenti tra righe {first_number} e {number}: "
                    f"{_location(sheet, number, column, row[column])}."
                )


def _ordered_group(group: list[tuple[int, dict[str, str]]], sheet: str) -> list[tuple[int, dict[str, str]]]:
    positioned = [
        (_parse_int(_required(row, "POSIZIONE_RIGA", sheet, number), sheet, number, "POSIZIONE_RIGA", minimum=1), number, row)
        for number, row in group
    ]
    positions = [item[0] for item in positioned]
    if len(set(positions)) != len(positions):
        raise InvalidSheetRowError(f"{sheet}: POSIZIONE_RIGA duplicata nello stesso aggregato.")
    return [(number, row) for _, number, row in sorted(positioned, key=lambda item: item[0])]


def programmi_from_rows(rows: tuple[dict[str, str], ...]) -> tuple[ProgrammaFornitura, ...]:
    groups: OrderedDict[str, list[tuple[int, dict[str, str]]]] = OrderedDict()
    for number, row in enumerate(rows, start=2):
        _validate_schema(row, PROGRAMMI_HEADERS, PROGRAMMI_SHEET_NAME, number)
        identifier = _required(row, "PROGRAMMA_FORNITURA_ID", PROGRAMMI_SHEET_NAME, number)
        groups.setdefault(identifier, []).append((number, row))

    result = []
    header_columns = (
        "CLIENTE_ID", "STATO", "DATA_INIZIO", "DATA_FINE",
        "ORARIO_GENERAZIONE", "FINESTRA_OPERATIVA_GIORNI",
    )
    for identifier, group in groups.items():
        _consistent(group, header_columns, PROGRAMMI_SHEET_NAME)
        ordered = _ordered_group(group, PROGRAMMI_SHEET_NAME)
        first_number, first = ordered[0]
        righe = []
        for number, row in ordered:
            tipo = _enum(TipoRicorrenza, _required(row, "TIPO_RICORRENZA", PROGRAMMI_SHEET_NAME, number), PROGRAMMI_SHEET_NAME, number, "TIPO_RICORRENZA")
            interval_text = _optional(row, "INTERVALLO_GIORNI", PROGRAMMI_SHEET_NAME, number)
            days_text = _optional(row, "GIORNI_SETTIMANA", PROGRAMMI_SHEET_NAME, number)
            interval = _parse_int(interval_text, PROGRAMMI_SHEET_NAME, number, "INTERVALLO_GIORNI", minimum=1) if interval_text else None
            if days_text:
                parts = days_text.split(",")
                if any(not part.isdigit() for part in parts):
                    raise InvalidSheetRowError(f"GIORNI_SETTIMANA non valido: {_location(PROGRAMMI_SHEET_NAME, number, 'GIORNI_SETTIMANA', days_text)}.")
                days = tuple(int(part) for part in parts)
            else:
                days = ()
            try:
                configuration = ConfigurazioneTemporale(tipo, interval, days)
                righe.append(RigaProgrammaFornitura(
                    _parse(VarietaId, _required(row, "VARIETA_ID", PROGRAMMI_SHEET_NAME, number), PROGRAMMI_SHEET_NAME, number, "VARIETA_ID"),
                    Quantity(
                        _parse_decimal(_required(row, "QUANTITA", PROGRAMMI_SHEET_NAME, number), PROGRAMMI_SHEET_NAME, number),
                        _enum(UnitOfMeasure, _required(row, "UNITA_MISURA", PROGRAMMI_SHEET_NAME, number), PROGRAMMI_SHEET_NAME, number, "UNITA_MISURA"),
                    ),
                    configuration,
                ))
            except (DomainError, ValueError) as exc:
                raise InvalidSheetRowError(f"Riga programma non valida: {PROGRAMMI_SHEET_NAME} riga {number}.") from exc
        data_fine_text = _optional(first, "DATA_FINE", PROGRAMMI_SHEET_NAME, first_number)
        try:
            result.append(ProgrammaFornitura(
                id=_parse(ProgrammaFornituraId, identifier, PROGRAMMI_SHEET_NAME, first_number, "PROGRAMMA_FORNITURA_ID"),
                cliente_id=_parse(ClienteId, _required(first, "CLIENTE_ID", PROGRAMMI_SHEET_NAME, first_number), PROGRAMMI_SHEET_NAME, first_number, "CLIENTE_ID"),
                righe=tuple(righe),
                data_inizio=_parse_date(_required(first, "DATA_INIZIO", PROGRAMMI_SHEET_NAME, first_number), PROGRAMMI_SHEET_NAME, first_number, "DATA_INIZIO"),
                data_fine=_parse_date(data_fine_text, PROGRAMMI_SHEET_NAME, first_number, "DATA_FINE") if data_fine_text else None,
                stato=_enum(ProgrammaFornituraState, _required(first, "STATO", PROGRAMMI_SHEET_NAME, first_number), PROGRAMMI_SHEET_NAME, first_number, "STATO"),
                finestra_operativa_giorni=_parse_int(_required(first, "FINESTRA_OPERATIVA_GIORNI", PROGRAMMI_SHEET_NAME, first_number), PROGRAMMI_SHEET_NAME, first_number, "FINESTRA_OPERATIVA_GIORNI", minimum=0),
                orario_generazione=_parse_time(_required(first, "ORARIO_GENERAZIONE", PROGRAMMI_SHEET_NAME, first_number), PROGRAMMI_SHEET_NAME, first_number, "ORARIO_GENERAZIONE"),
            ))
        except (DomainError, ValueError) as exc:
            raise InvalidSheetRowError(f"PROGRAMMA_FORNITURA non valido: {identifier!r}.") from exc
    return tuple(result)


def scheduled_orders_from_rows(rows: tuple[dict[str, str], ...]) -> tuple[ScheduledOrderRecord, ...]:
    groups: OrderedDict[str, list[tuple[int, dict[str, str]]]] = OrderedDict()
    for number, row in enumerate(rows, start=2):
        _validate_schema(row, ORDINI_HEADERS, ORDINI_SHEET_NAME, number)
        identifier = _required(row, "ORDINE_ID", ORDINI_SHEET_NAME, number)
        groups.setdefault(identifier, []).append((number, row))
    result = []
    header_columns = (
        "CLIENTE_ID", "DATA_ORDINE", "STATO", "PROGRAMMA_FORNITURA_ID",
        "DATA_CONSEGNA_PREVISTA", "CHIAVE_IDEMPOTENZA",
    )
    for identifier, group in groups.items():
        _consistent(group, header_columns, ORDINI_SHEET_NAME)
        ordered = _ordered_group(group, ORDINI_SHEET_NAME)
        first_number, first = ordered[0]
        try:
            righe = tuple(
                RigaOrdine(
                    _parse(VarietaId, _required(row, "VARIETA_ID", ORDINI_SHEET_NAME, number), ORDINI_SHEET_NAME, number, "VARIETA_ID"),
                    Quantity(
                        _parse_decimal(_required(row, "QUANTITA", ORDINI_SHEET_NAME, number), ORDINI_SHEET_NAME, number),
                        _enum(UnitOfMeasure, _required(row, "UNITA_MISURA", ORDINI_SHEET_NAME, number), ORDINI_SHEET_NAME, number, "UNITA_MISURA"),
                    ),
                )
                for number, row in ordered
            )
        except DomainError as exc:
            raise InvalidSheetRowError(f"Righe ORDINE non valide: {identifier!r}.") from exc
        programma_text = _optional(first, "PROGRAMMA_FORNITURA_ID", ORDINI_SHEET_NAME, first_number)
        try:
            ordine = Ordine(
                id=_parse(OrdineId, identifier, ORDINI_SHEET_NAME, first_number, "ORDINE_ID"),
                cliente_id=_parse(ClienteId, _required(first, "CLIENTE_ID", ORDINI_SHEET_NAME, first_number), ORDINI_SHEET_NAME, first_number, "CLIENTE_ID"),
                data_ordine=_parse_date(_required(first, "DATA_ORDINE", ORDINI_SHEET_NAME, first_number), ORDINI_SHEET_NAME, first_number, "DATA_ORDINE"),
                righe=righe,
                stato=_enum(OrdineState, _required(first, "STATO", ORDINI_SHEET_NAME, first_number), ORDINI_SHEET_NAME, first_number, "STATO"),
                tipo_creazione=OrdineCreationType.AUTOMATICO,
                programma_fornitura_id=_parse(ProgrammaFornituraId, programma_text, ORDINI_SHEET_NAME, first_number, "PROGRAMMA_FORNITURA_ID") if programma_text else None,
            )
        except DomainError as exc:
            raise InvalidSheetRowError(f"ORDINE non valido: {identifier!r}.") from exc
        result.append(ScheduledOrderRecord(
            ordine=ordine,
            data_consegna_prevista=_parse_date(_required(first, "DATA_CONSEGNA_PREVISTA", ORDINI_SHEET_NAME, first_number), ORDINI_SHEET_NAME, first_number, "DATA_CONSEGNA_PREVISTA"),
            chiave_idempotenza=_required(first, "CHIAVE_IDEMPOTENZA", ORDINI_SHEET_NAME, first_number),
        ))
    return tuple(result)


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def scheduled_orders_to_rows(records: tuple[ScheduledOrderRecord, ...]) -> tuple[dict[str, str], ...]:
    rows = []
    for record in records:
        ordine = record.ordine
        for position, riga in enumerate(ordine.righe, start=1):
            rows.append(dict(zip(ORDINI_HEADERS, (
                ordine.id.value,
                ordine.cliente_id.value,
                ordine.data_ordine.strftime("%Y/%m/%d"),
                ordine.stato.value,
                ordine.programma_fornitura_id.value if ordine.programma_fornitura_id else "",
                record.data_consegna_prevista.strftime("%Y/%m/%d"),
                record.chiave_idempotenza,
                str(position),
                riga.varieta_id.value,
                _decimal_text(riga.quantita.value),
                riga.quantita.unit.value,
            ))))
    return tuple(rows)
