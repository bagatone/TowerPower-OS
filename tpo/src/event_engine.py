from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .config_loader import load_config
from .init_resource_engine import INITIAL_ROWS, RESOURCE_HEADERS
from .schema_validator import SchemaValidator
from .sheets_loader import SheetData, SheetsLoader
from .source_gate import SourceGate, SourceProvenance, build_google_sheets_provenance
from .sheets_writer import WritePlan


DEFAULT_TIMEZONE = "Atlantic/Canary"
DEFAULT_SCHEMA_PATH = Path("docs/TPO_SHEETS_SCHEMA.md")
SUPPORTED_EVENTS = {"SEMINA"}
SEMINA_REQUIRED_SHEETS = [
    "MASTER_VARIETA",
    "SEMINE",
    "LOTTI",
    "INVENTARIO",
    "RICETTE_PRODUZIONE",
    "MOVIMENTI_MAGAZZINO",
]


class EventEngineError(RuntimeError):
    pass


class EventStatus(str, Enum):
    BOZZA = "BOZZA"
    VALIDATO = "VALIDATO"
    CONFERMATO = "CONFERMATO"
    PRONTO = "PRONTO"
    APPLICATO = "APPLICATO"
    BLOCCATO = "BLOCCATO"


@dataclass(frozen=True)
class OperationalEvent:
    event_id: str
    event_type: str
    timestamp: str
    timezone: str
    operatore: str
    source: str
    payload: dict[str, Any]
    status: EventStatus = EventStatus.BOZZA

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OperationalEvent":
        status_value = str(data.get("status", EventStatus.BOZZA.value)).strip() or EventStatus.BOZZA.value
        try:
            status = EventStatus(status_value)
        except ValueError as exc:
            raise EventEngineError(f"Stato evento non valido: {status_value}") from exc
        return cls(
            event_id=str(data.get("event_id", "")).strip(),
            event_type=str(data.get("event_type", "")).strip().upper(),
            timestamp=str(data.get("timestamp", "")).strip(),
            timezone=str(data.get("timezone", DEFAULT_TIMEZONE)).strip(),
            operatore=str(data.get("operatore", "")).strip(),
            source=str(data.get("source", "")).strip(),
            payload=dict(data.get("payload", {})),
            status=status,
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "OperationalEvent":
        with Path(path).open("r", encoding="utf-8") as file:
            return cls.from_dict(json.load(file))


@dataclass
class EventResult:
    event: OperationalEvent
    status: EventStatus
    errors: list[str] = field(default_factory=list)
    consumi: list[dict[str, str]] = field(default_factory=list)
    write_plan: WritePlan | None = None
    provenance: list[SourceProvenance] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.status == EventStatus.PRONTO and not self.errors and self.write_plan is not None


@dataclass(frozen=True)
class EventDataContext:
    sheets: dict[str, SheetData]
    schemas: dict[str, list[str]]


class EventEngine:
    def __init__(self, context: EventDataContext) -> None:
        self.context = context

    @classmethod
    def from_context(cls, context: EventDataContext) -> "EventEngine":
        return cls(context)

    @classmethod
    def from_default_sources(
        cls,
        config_path: str | Path = "config/settings.yaml",
        schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    ) -> "EventEngine":
        schemas = _load_schemas(schema_path)
        path = Path(config_path)
        if path.exists():
            config = load_config(path)
            loader = SheetsLoader.from_config(config)
            sheet_names = [
                "MASTER_VARIETA",
                "SEMINE",
                "LOTTI",
                "INVENTARIO",
                "RICETTE_PRODUZIONE",
                "MOVIMENTI_MAGAZZINO",
            ]
            sheets = loader.load_required_sheets(
                names=sheet_names,
                expected_headers={name: schemas[name] for name in sheet_names if name in schemas},
            )
        else:
            sheets = build_demo_sheets(schemas)
        return cls(EventDataContext(sheets=sheets, schemas=schemas))

    def process(self, event: OperationalEvent) -> EventResult:
        result = EventResult(event=event, status=EventStatus.BLOCCATO)
        self._validate_event_structure(event, result)
        if result.errors:
            return result
        if event.event_type == "SEMINA":
            source_gate_result = SourceGate().check_request("event_semina", self.context.sheets)
            result.provenance = source_gate_result.provenance
            if not source_gate_result.allowed:
                result.errors.append(
                    "SOURCE_NOT_AVAILABLE: fonti mancanti o non lette: "
                    + ", ".join(source_gate_result.missing_sources)
                )
                return result
            return self._process_semina(event, result)
        result.errors.append(f"Evento non supportato nell'MVP: {event.event_type}")
        return result

    def _validate_event_structure(self, event: OperationalEvent, result: EventResult) -> None:
        if not event.event_id:
            result.errors.append("event_id mancante.")
        if event.event_type not in SUPPORTED_EVENTS:
            result.errors.append(f"event_type non supportato: {event.event_type}")
        if event.timezone != DEFAULT_TIMEZONE:
            result.errors.append(f"timezone non valida: {event.timezone}. Attesa: {DEFAULT_TIMEZONE}.")
        if not event.timestamp:
            result.errors.append("timestamp mancante.")
        else:
            try:
                datetime.fromisoformat(event.timestamp)
            except ValueError:
                result.errors.append("timestamp non valido: usare YYYY-MM-DDTHH:MM:SS.")

    def _process_semina(self, event: OperationalEvent, result: EventResult) -> EventResult:
        self._validate_sheet_structures(SEMINA_REQUIRED_SHEETS, result)
        if result.errors:
            return result

        payload = event.payload
        required = ["varieta", "set", "unita", "data_semina"]
        missing = [field for field in required if payload.get(field) in (None, "")]
        if missing:
            result.errors.append(f"Campi obbligatori mancanti: {', '.join(missing)}.")
            return result

        id_lotto = str(payload.get("id_lotto", "")).strip()
        if not id_lotto:
            result.errors.append(
                "ID_LOTTO mancante. Fornire un ID lotto oppure implementare Lot ID Generator."
            )
            return result

        try:
            set_count = float(payload["set"])
        except (TypeError, ValueError):
            result.errors.append("set deve essere numerico.")
            return result
        if set_count <= 0:
            result.errors.append("set deve essere maggiore di zero.")
        if str(payload.get("unita", "")).strip().lower() != "set":
            result.errors.append("unita deve essere 'set'.")
        data_semina = str(payload.get("data_semina", "")).strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_semina):
            result.errors.append("data_semina deve essere ISO YYYY-MM-DD.")
        else:
            try:
                datetime.fromisoformat(data_semina)
            except ValueError:
                result.errors.append("data_semina deve essere una data ISO valida.")
        if self._id_lotto_exists(id_lotto):
            result.errors.append(f"ID_LOTTO già presente: {id_lotto}.")
        if result.errors:
            return result

        varieta = str(payload["varieta"]).strip()
        master_row = self._find_by_value("MASTER_VARIETA", "VARIETA", varieta)
        if not master_row:
            result.errors.append(f"Varietà non presente in MASTER_VARIETA: {varieta}.")
            return result
        if not str(master_row.get("GRAMMI_SET", "")).strip():
            result.errors.append(f"GRAMMI_SET mancante in MASTER_VARIETA per: {varieta}.")
            return result

        recipe_rows = self._recipe_rows_for(varieta)
        if not recipe_rows:
            result.errors.append(f"Ricetta mancante in RICETTE_PRODUZIONE per: {varieta}.")
            return result

        consumi = self._calculate_consumi(recipe_rows, set_count)
        inventory_errors = self._validate_inventory(consumi)
        if inventory_errors:
            result.errors.extend(inventory_errors)
            return result

        result.consumi = consumi
        result.write_plan = self._build_semina_write_plan(event, id_lotto, varieta, set_count, consumi)
        result.status = EventStatus.PRONTO
        return result

    def _validate_sheet_structures(self, sheet_names: list[str], result: EventResult) -> None:
        for sheet_name in sheet_names:
            expected_headers = self.context.schemas.get(sheet_name)
            if not expected_headers:
                result.errors.append(f"{sheet_name}: schema ufficiale mancante.")
                continue
            sheet = self.context.sheets.get(sheet_name)
            if not sheet:
                result.errors.append(f"{sheet_name}: foglio mancante.")
                continue
            if sheet.headers != expected_headers:
                result.errors.append(
                    f"{sheet_name}: intestazioni non valide. "
                    f"Attese {expected_headers}, trovate {sheet.headers}."
                )

    def _id_lotto_exists(self, id_lotto: str) -> bool:
        return (
            self._find_by_value("SEMINE", "ID_LOTTO", id_lotto) is not None
            or self._find_by_value("LOTTI", "CALENDARIO_PROD", id_lotto) is not None
        )

    def _find_by_value(self, sheet_name: str, column: str, expected: str) -> dict[str, str] | None:
        sheet = self.context.sheets.get(sheet_name)
        if not sheet:
            return None
        expected_key = _canonical(expected)
        for row in sheet.rows:
            if _canonical(row.get(column, "")) == expected_key:
                return row
        return None

    def _recipe_rows_for(self, varieta: str) -> list[dict[str, str]]:
        sheet = self.context.sheets.get("RICETTE_PRODUZIONE")
        if not sheet:
            return []
        product_key = _canonical(varieta)
        return [
            row
            for row in sheet.rows
            if _canonical(row.get("PRODOTTO", "")) == product_key
            and _canonical(row.get("STATO", "")) == "ATTIVA"
        ]

    def _calculate_consumi(self, recipe_rows: list[dict[str, str]], set_count: float) -> list[dict[str, str]]:
        consumi: list[dict[str, str]] = []
        for row in recipe_rows:
            try:
                quantity = float(str(row.get("QUANTITA_PER_UNITA", "")).replace(",", "."))
            except ValueError as exc:
                raise EventEngineError(
                    f"QUANTITA_PER_UNITA non valida per {row.get('ID_ARTICOLO', '')}."
                ) from exc
            required = quantity * set_count
            consumi.append(
                {
                    "risorsa": row.get("RISORSA", ""),
                    "id_articolo": row.get("ID_ARTICOLO", ""),
                    "quantita": _format_number(required),
                    "unita": row.get("UNITA_MISURA", ""),
                }
            )
        return consumi

    def _validate_inventory(self, consumi: list[dict[str, str]]) -> list[str]:
        errors: list[str] = []
        inventory = self.context.sheets.get("INVENTARIO")
        if not inventory:
            return ["Foglio INVENTARIO mancante."]
        by_id = {row.get("ID_ARTICOLO", ""): row for row in inventory.rows}
        for consumo in consumi:
            article_id = consumo["id_articolo"]
            row = by_id.get(article_id)
            if not row:
                errors.append(f"Risorsa non presente in INVENTARIO: {article_id}.")
                continue
            available_raw = row.get("QUANTITA_DISPONIBILE_REALE") or row.get("QUANTITA_DISPONIBILE") or "0"
            try:
                available = float(str(available_raw).replace(",", "."))
                required = float(str(consumo["quantita"]).replace(",", "."))
            except ValueError:
                errors.append(f"Quantità inventario non valida per {article_id}.")
                continue
            if available < required:
                missing = required - available
                errors.append(
                    f"Inventario insufficiente per {article_id}: richiesto {_format_number(required)} "
                    f"{consumo['unita']}, disponibile {_format_number(available)}, "
                    f"mancante {_format_number(missing)}."
                )
        return errors

    def _build_semina_write_plan(
        self,
        event: OperationalEvent,
        id_lotto: str,
        varieta: str,
        set_count: float,
        consumi: list[dict[str, str]],
    ) -> WritePlan:
        payload = event.payload
        data_semina = str(payload["data_semina"])
        operatore = str(payload.get("operatore") or event.operatore)
        note = str(payload.get("note", ""))
        grammi = next((item["quantita"] for item in consumi if item["unita"] == "g"), "")

        movement_rows = []
        for index, consumo in enumerate(consumi, start=1):
            movement_rows.append(
                {
                    "DATA": data_semina,
                    "ID_MOVIMENTO": f"MOV-{event.event_id}-{index:03d}",
                    "ID_ARTICOLO": consumo["id_articolo"],
                    "TIPO_MOVIMENTO": "USCITA_PRODUZIONE",
                    "QUANTITA": consumo["quantita"],
                    "UNITA_MISURA": consumo["unita"],
                    "CAUSALE": f"Semina {id_lotto}",
                    "ID_LOTTO": id_lotto,
                    "OPERATORE": operatore,
                    "DOCUMENTO_RIFERIMENTO": event.event_id,
                    "NOTE": note,
                }
            )

        operations = [
            {
                "sheet_name": "SEMINE",
                "mode": "append",
                "rows": [
                    {
                        "DATA": data_semina,
                        "ID_LOTTO": id_lotto,
                        "VARIETA": varieta,
                        "SET": _format_number(set_count),
                        "GRAMMI_SEME": grammi,
                        "INIZIO_IDRATAZIONE": str(payload.get("inizio_idratazione", "")),
                        "DATA_SEMINA": data_semina,
                        "OPERATORE": operatore,
                        "NOTE": note,
                    }
                ],
            },
            {
                "sheet_name": "LOTTI",
                "mode": "append",
                "rows": [
                    {
                        "CALENDARIO_PROD": id_lotto,
                        "SET": _format_number(set_count),
                        "VARIETA": varieta,
                        "DATA_SEMINA": data_semina,
                        "DATA_PASSAGGIO": "",
                        "FASE": "germinazione",
                        "STATO": "ok",
                        "DATA_RACCOLTA": "",
                        "NOTE": note,
                    }
                ],
            },
            {
                "sheet_name": "MOVIMENTI_MAGAZZINO",
                "mode": "append",
                "rows": movement_rows,
            },
        ]
        return WritePlan.from_dict({"operations": operations})


def _load_schemas(schema_path: str | Path) -> dict[str, list[str]]:
    markdown = Path(schema_path).read_text(encoding="utf-8")
    parsed = SchemaValidator().parse_schema(markdown)
    return {sheet_name: schema.headers for sheet_name, schema in parsed.items()}


def build_demo_sheets(schemas: dict[str, list[str]]) -> dict[str, SheetData]:
    sheets: dict[str, SheetData] = {}
    for sheet_name in ["SEMINE", "LOTTI"]:
        headers = schemas[sheet_name]
        sheets[sheet_name] = SheetData(
            sheet_name,
            headers,
            [],
            [headers],
            provenance=build_google_sheets_provenance(sheet_name, "demo", [headers]),
        )

    movement_headers = schemas["MOVIMENTI_MAGAZZINO"]
    sheets["MOVIMENTI_MAGAZZINO"] = SheetData(
        "MOVIMENTI_MAGAZZINO",
        movement_headers,
        [],
        [movement_headers],
        provenance=build_google_sheets_provenance(
            "MOVIMENTI_MAGAZZINO",
            "demo",
            [movement_headers],
        ),
    )

    master_headers = schemas["MASTER_VARIETA"]
    master_rows = [
        {
            "VARIETA": "Cilantro",
            "CODICE": "CIL",
            "GRAMMI_SET": "14",
            "IDRATAZIONE_ORE": "24",
            "GERMINAZIONE_GG": "5",
            "LUCE_GG": "7",
            "TOTALE_GG": "12",
            "STATO": "ATTIVO",
            "NOTE": "Demo MVP",
        }
    ]
    sheets["MASTER_VARIETA"] = _sheet_from_dicts("MASTER_VARIETA", master_headers, master_rows)

    for sheet_name in ["INVENTARIO", "RICETTE_PRODUZIONE"]:
        headers = RESOURCE_HEADERS[sheet_name]
        sheets[sheet_name] = SheetData(
            sheet_name,
            headers,
            [dict(zip(headers, row)) for row in INITIAL_ROWS[sheet_name]],
            [headers, *INITIAL_ROWS[sheet_name]],
            provenance=build_google_sheets_provenance(
                sheet_name,
                "demo",
                [headers, *INITIAL_ROWS[sheet_name]],
            ),
        )
    return sheets


def _sheet_from_dicts(sheet_name: str, headers: list[str], rows: list[dict[str, str]]) -> SheetData:
    raw_rows = [[row.get(header, "") for header in headers] for row in rows]
    return SheetData(
        sheet_name,
        headers,
        rows,
        [headers, *raw_rows],
        provenance=build_google_sheets_provenance(sheet_name, "demo", [headers, *raw_rows]),
    )


def _canonical(value: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", str(value))
        if not unicodedata.combining(char)
    )
    return re.sub(r"[\s_]+", "", without_accents).upper()


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)
