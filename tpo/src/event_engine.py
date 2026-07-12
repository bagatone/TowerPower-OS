from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
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
SUPPORTED_EVENTS = {"SEMINA", "NUOVO_ORDINE_RICORRENTE"}
SEMINA_REQUIRED_SHEETS = [
    "MASTER_VARIETA",
    "SEMINE",
    "LOTTI",
    "INVENTARIO",
    "RICETTE_PRODUZIONE",
    "MOVIMENTI_MAGAZZINO",
]
RECURRING_ORDER_REQUIRED_SHEETS = [
    "CLIENTI",
    "CONSEGNE",
    "MASTER_VARIETA",
    "PIANO_SEMINE",
    "CALENDARIO_PRODUZIONE",
    "STOCK",
    "INVENTARIO",
    "RICETTE_PRODUZIONE",
]
WEEKDAYS = {
    "LUNEDI": 0,
    "LUNEDÌ": 0,
    "MARTEDI": 1,
    "MARTEDÌ": 1,
    "MERCOLEDI": 2,
    "MERCOLEDÌ": 2,
    "GIOVEDI": 3,
    "GIOVEDÌ": 3,
    "VENERDI": 4,
    "VENERDÌ": 4,
    "SABATO": 5,
    "DOMENICA": 6,
}
WEEKDAY_LABELS = [
    "Lunedì",
    "Martedì",
    "Mercoledì",
    "Giovedì",
    "Venerdì",
    "Sabato",
    "Domenica",
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
    stock_delta_preview: list[dict[str, str]] = field(default_factory=list)
    resource_commitment_preview: list[dict[str, str]] = field(default_factory=list)
    calendar_preview: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocking_errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.status == EventStatus.PRONTO and not self.errors and self.write_plan is not None

    def block(self, message: str) -> None:
        self.errors.append(message)
        self.blocking_errors.append(message)


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
            required_sheet_names = list(dict.fromkeys([*sheet_names, *RECURRING_ORDER_REQUIRED_SHEETS]))
            sheets = loader.load_required_sheets(
                names=required_sheet_names,
                expected_headers={name: schemas[name] for name in required_sheet_names if name in schemas},
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
                result.block(
                    "SOURCE_NOT_AVAILABLE: fonti mancanti o non lette: "
                    + ", ".join(source_gate_result.missing_sources)
                )
                return result
            return self._process_semina(event, result)
        if event.event_type == "NUOVO_ORDINE_RICORRENTE":
            source_gate_result = SourceGate().check_request("event_ordine_ricorrente", self.context.sheets)
            result.provenance = source_gate_result.provenance
            if not source_gate_result.allowed:
                result.block(
                    "SOURCE_NOT_AVAILABLE: fonti mancanti o non lette: "
                    + ", ".join(source_gate_result.missing_sources)
                )
                return result
            return self._process_recurring_order(event, result)
        result.errors.append(f"Evento non supportato nell'MVP: {event.event_type}")
        return result

    def _validate_event_structure(self, event: OperationalEvent, result: EventResult) -> None:
        if not event.event_id:
            result.errors.append("event_id mancante.")
        if event.event_type not in SUPPORTED_EVENTS:
            result.errors.append(f"event_type non supportato: {event.event_type}")
        if event.timezone != DEFAULT_TIMEZONE:
            result.errors.append(f"timezone non valida: {event.timezone}. Attesa: {DEFAULT_TIMEZONE}.")
        if event.status not in (EventStatus.CONFERMATO, EventStatus.PRONTO):
            result.errors.append("stato evento insufficiente: usare almeno CONFERMATO.")
        if not event.timestamp:
            result.errors.append("timestamp mancante.")
        else:
            try:
                datetime.fromisoformat(event.timestamp)
            except ValueError:
                result.errors.append("timestamp non valido: usare YYYY-MM-DDTHH:MM:SS.")

    def _process_recurring_order(self, event: OperationalEvent, result: EventResult) -> EventResult:
        self._validate_sheet_structures(RECURRING_ORDER_REQUIRED_SHEETS, result)
        if result.errors:
            result.blocking_errors.extend(result.errors)
            return result

        payload = event.payload
        products = payload.get("prodotti")
        delivery_date = self._validate_recurring_order_payload(payload, result)
        if result.errors or delivery_date is None:
            result.blocking_errors.extend(result.errors)
            return result

        client = str(payload["cliente"]).strip()
        frequency_days = int(payload["frequenza_giorni"])
        delivery_weekday = str(payload["giorno_consegna"]).strip().upper()
        note = str(payload.get("note", ""))

        client_operation = self._client_operation(client, payload, result)
        if result.errors:
            result.blocking_errors.extend(result.errors)
            return result

        new_delivery_rows: list[dict[str, str]] = []
        plan_rows: list[dict[str, str]] = []
        calendar_rows: list[dict[str, str]] = []
        resource_rows: list[dict[str, str]] = []
        stock_delta: list[dict[str, str]] = []

        for product in products:
            variety = str(product["varieta"]).strip()
            quantity = float(product["quantita"])
            quantity_text = _format_number(quantity)
            if self._is_duplicate_recurring_delivery(client, variety, frequency_days, delivery_date):
                result.block(f"Ordine duplicato in CONSEGNE: {client} / {variety}.")
                continue

            master_row = self._find_by_value("MASTER_VARIETA", "VARIETA", variety)
            if not master_row:
                result.block(f"Varietà non presente in MASTER_VARIETA: {variety}.")
                continue
            missing_cycle = [
                field
                for field in ("GERMINAZIONE_GG", "TOTALE_GG")
                if not str(master_row.get(field, "")).strip()
            ]
            if missing_cycle:
                result.block(
                    f"Parametri ciclo mancanti per {variety}: {', '.join(missing_cycle)}."
                )
                continue
            invalid_cycle = [
                field
                for field in ("GERMINAZIONE_GG", "TOTALE_GG", "IDRATAZIONE_ORE")
                if _parse_number(master_row.get(field, "0") or "0") is None
            ]
            if invalid_cycle:
                result.block(
                    f"Parametri ciclo non numerici per {variety}: {', '.join(invalid_cycle)}."
                )
                continue
            if not self._recipe_rows_for(variety):
                result.block(f"Ricetta mancante in RICETTE_PRODUZIONE per: {variety}.")
                continue

            calendar = self._build_calendar_for_variety(variety, master_row, delivery_date)
            result.calendar_preview.append(calendar)
            stock_delta.append(
                {
                    "varieta": variety,
                    "delta_prenotato": quantity_text,
                    "unita": "set",
                    "nota": "Preview: STOCK non aggiornato dal Writer v1.",
                }
            )

            try:
                resource_rows.extend(self._resource_commitment_for(variety, quantity))
            except EventEngineError as exc:
                result.block(str(exc))
                continue
            new_delivery_rows.append(
                {
                    "CLIENTE": client,
                    "PRODOTTO": variety,
                    "QUANTITA": quantity_text,
                    "UNITA": "set",
                    "ID_LOTTO": "",
                    "STATO": "ATTIVA",
                    "GIORNO_CONSEGNA": delivery_weekday,
                    "FREQUENZA": str(frequency_days),
                    "PROSSIMA_CONSEGNA": delivery_date.isoformat(),
                    "NOTE": note,
                }
            )
            plan_rows.append(
                {
                    "DATA_IDRATAZIONE": calendar["data_idratazione"],
                    "DATA_SEMINA": calendar["data_semina"],
                    "VARIETA": variety,
                    "SET": quantity_text,
                    "CLIENTE_DESTINAZIONE": client,
                    "DATA_CONSEGNA_PREVISTA": delivery_date.isoformat(),
                    "PRIORITA": "ORDINE_RICORRENTE",
                    "STATO": "PIANIFICATO",
                    "NOTE": note,
                }
            )
            calendar_rows.extend(
                self._calendar_rows_for_order(
                    client=client,
                    variety=variety,
                    quantity=quantity_text,
                    calendar=calendar,
                    note=note,
                )
            )

        if result.errors:
            return result

        resource_summary = self._aggregate_resources(resource_rows)
        inventory_errors = self._validate_resource_commitment(resource_summary)
        result.resource_commitment_preview = resource_summary
        result.stock_delta_preview = stock_delta
        if inventory_errors:
            for error in inventory_errors:
                result.block(error)
            return result

        operations: list[dict[str, Any]] = []
        if client_operation:
            operations.append(client_operation)
        operations.extend(
            [
                {"sheet_name": "CONSEGNE", "mode": "append", "rows": new_delivery_rows},
                {"sheet_name": "PIANO_SEMINE", "mode": "append", "rows": plan_rows},
                {
                    "sheet_name": "CALENDARIO_PRODUZIONE",
                    "mode": "append",
                    "rows": calendar_rows,
                },
            ]
        )
        result.write_plan = WritePlan.from_dict({"operations": operations})
        result.status = EventStatus.PRONTO
        return result

    def _validate_recurring_order_payload(
        self,
        payload: dict[str, Any],
        result: EventResult,
    ) -> date | None:
        if not str(payload.get("cliente", "")).strip():
            result.errors.append("cliente mancante.")
        try:
            frequency_days = int(payload.get("frequenza_giorni"))
            if frequency_days <= 0:
                result.errors.append("frequenza_giorni deve essere maggiore di zero.")
        except (TypeError, ValueError):
            result.errors.append("frequenza_giorni deve essere un intero.")

        delivery_text = str(payload.get("prima_consegna", "")).strip()
        delivery_date: date | None = None
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", delivery_text):
            result.errors.append("prima_consegna deve essere ISO YYYY-MM-DD.")
        else:
            try:
                delivery_date = datetime.strptime(delivery_text, "%Y-%m-%d").date()
            except ValueError:
                result.errors.append("prima_consegna deve essere una data ISO valida.")

        weekday = str(payload.get("giorno_consegna", "")).strip().upper()
        if weekday not in WEEKDAYS:
            result.errors.append("giorno_consegna non valido.")
        elif delivery_date and delivery_date.weekday() != WEEKDAYS[weekday]:
            result.errors.append(
                f"giorno_consegna incompatibile con prima_consegna: "
                f"{delivery_text} è {WEEKDAY_LABELS[delivery_date.weekday()]}."
            )

        products = payload.get("prodotti")
        if not isinstance(products, list) or not products:
            result.errors.append("prodotti non può essere vuoto.")
            return delivery_date

        for index, product in enumerate(products, start=1):
            if not str(product.get("varieta", "")).strip():
                result.errors.append(f"prodotti[{index}].varieta mancante.")
            try:
                quantity = float(product.get("quantita"))
                if quantity <= 0:
                    result.errors.append(f"prodotti[{index}].quantita deve essere maggiore di zero.")
            except (TypeError, ValueError):
                result.errors.append(f"prodotti[{index}].quantita deve essere numerica.")
            if str(product.get("unita", "")).strip().lower() != "set":
                result.errors.append(f"prodotti[{index}].unita deve essere 'set'.")
        return delivery_date

    def _client_operation(
        self,
        client: str,
        payload: dict[str, Any],
        result: EventResult,
    ) -> dict[str, Any] | None:
        existing = self._find_by_value("CLIENTI", "CLIENTE", client)
        if existing:
            status = _canonical(existing.get("STATO", ""))
            if status == "SOSPESO":
                result.block(
                    f"Cliente sospeso: {client}. Richiedere prima CLIENTE_RIATTIVATO."
                )
            return None
        return {
            "sheet_name": "CLIENTI",
            "mode": "append",
            "rows": [
                {
                    "CLIENTE": client,
                    "FREQUENZA": str(payload.get("frequenza_giorni", "")),
                    "GIORNO": str(payload.get("giorno_consegna", "")),
                    "STATO": str(payload.get("stato_cliente", "ATTIVO") or "ATTIVO"),
                    "NOTE": str(payload.get("note", "")),
                }
            ],
        }

    def _is_duplicate_recurring_delivery(
        self,
        client: str,
        variety: str,
        frequency_days: int,
        delivery_date: date,
    ) -> bool:
        sheet = self.context.sheets.get("CONSEGNE")
        if not sheet:
            return False
        client_key = _canonical(client)
        variety_key = _canonical(variety)
        for row in sheet.rows:
            same_client = _canonical(row.get("CLIENTE", "")) == client_key
            same_product = _canonical(row.get("PRODOTTO", "")) == variety_key
            same_frequency = str(row.get("FREQUENZA", "")).strip() == str(frequency_days)
            row_delivery = _parse_sheet_date(row.get("PROSSIMA_CONSEGNA", ""))
            same_delivery = row_delivery == delivery_date
            if same_client and same_product and same_frequency and same_delivery:
                return True
        return False

    def _build_calendar_for_variety(
        self,
        variety: str,
        master_row: dict[str, str],
        delivery_date: date,
    ) -> dict[str, str]:
        total_days = int(_parse_number(master_row.get("TOTALE_GG", "0")) or 0)
        germination_days = int(_parse_number(master_row.get("GERMINAZIONE_GG", "0")) or 0)
        hydration_hours = _parse_number(master_row.get("IDRATAZIONE_ORE", "0") or "0") or 0
        sowing_date = delivery_date - timedelta(days=total_days)
        light_date = sowing_date + timedelta(days=germination_days)
        hydration_date = ""
        if hydration_hours > 0:
            hydration_days = max(1, int((hydration_hours + 23) // 24))
            hydration_date = (sowing_date - timedelta(days=hydration_days)).isoformat()
        return {
            "varieta": variety,
            "data_idratazione": hydration_date,
            "data_semina": sowing_date.isoformat(),
            "data_passaggio_luce": light_date.isoformat(),
            "data_raccolta": delivery_date.isoformat(),
            "data_consegna": delivery_date.isoformat(),
            "giorno_consegna": WEEKDAY_LABELS[delivery_date.weekday()],
        }

    def _calendar_rows_for_order(
        self,
        client: str,
        variety: str,
        quantity: str,
        calendar: dict[str, str],
        note: str,
    ) -> list[dict[str, str]]:
        rows = []
        if calendar["data_idratazione"]:
            rows.append(
                self._calendar_row(
                    calendar["data_idratazione"],
                    f"IDRATAZIONE {variety}",
                    variety,
                    quantity,
                    client,
                    "idratazione",
                    note,
                )
            )
        rows.extend(
            [
                self._calendar_row(calendar["data_semina"], f"SEMINA {variety}", variety, quantity, client, "semina", note),
                self._calendar_row(
                    calendar["data_passaggio_luce"],
                    f"PASSAGGIO_LUCE {variety}",
                    variety,
                    quantity,
                    client,
                    "luce",
                    note,
                ),
                self._calendar_row(
                    calendar["data_raccolta"],
                    f"RACCOLTA {variety}",
                    variety,
                    quantity,
                    client,
                    "raccolta",
                    note,
                ),
            ]
        )
        return rows

    def _calendar_row(
        self,
        date_value: str,
        event_name: str,
        variety: str,
        quantity: str,
        client: str,
        phase: str,
        note: str,
    ) -> dict[str, str]:
        return {
            "DATA": date_value,
            "EVENTO": event_name,
            "VARIETA": variety,
            "SET": quantity,
            "ID_LOTTO": "",
            "CLIENTE_COLLEGATO": client,
            "FASE": phase,
            "STATO": "PIANIFICATO",
            "PRIORITA": "ORDINE_RICORRENTE",
            "NOTE": note,
        }

    def _resource_commitment_for(self, variety: str, set_count: float) -> list[dict[str, str]]:
        return [
            {**item, "varieta": variety}
            for item in self._calculate_consumi(self._recipe_rows_for(variety), set_count)
        ]

    def _aggregate_resources(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        aggregated: dict[tuple[str, str, str], dict[str, str]] = {}
        for row in rows:
            key = (row["id_articolo"], row["risorsa"], row["unita"])
            current = aggregated.setdefault(
                key,
                {
                    "risorsa": row["risorsa"],
                    "id_articolo": row["id_articolo"],
                    "quantita": "0",
                    "unita": row["unita"],
                    "varieta": "",
                },
            )
            quantity = float(current["quantita"]) + float(row["quantita"])
            current["quantita"] = _format_number(quantity)
            varieties = [item for item in current["varieta"].split(", ") if item]
            if row["varieta"] not in varieties:
                varieties.append(row["varieta"])
            current["varieta"] = ", ".join(varieties)
        return list(aggregated.values())

    def _validate_resource_commitment(self, commitment: list[dict[str, str]]) -> list[str]:
        errors = []
        inventory = self.context.sheets.get("INVENTARIO")
        if not inventory:
            return ["Foglio INVENTARIO mancante."]
        by_id = {row.get("ID_ARTICOLO", ""): row for row in inventory.rows}
        for item in commitment:
            row = by_id.get(item["id_articolo"])
            if not row:
                errors.append(f"Risorsa non presente in INVENTARIO: {item['id_articolo']}.")
                continue
            available = _parse_number(row.get("QUANTITA_DISPONIBILE_REALE") or row.get("QUANTITA_DISPONIBILE") or "0")
            required = _parse_number(item["quantita"])
            if available is None:
                errors.append(f"Quantità inventario non valida per {item['id_articolo']}.")
                continue
            if required is None:
                errors.append(f"Quantità richiesta non valida per {item['id_articolo']}.")
                continue
            item["disponibile"] = _format_number(available)
            if available < required:
                item["mancante"] = _format_number(required - available)
                errors.append(
                    f"Inventario insufficiente per {item['id_articolo']}: richiesto "
                    f"{item['quantita']} {item['unita']}, disponibile {_format_number(available)}, "
                    f"mancante {item['mancante']}."
                )
        return errors

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
    for sheet_name in [
        "CLIENTI",
        "CONSEGNE",
        "SEMINE",
        "LOTTI",
        "PIANO_SEMINE",
        "CALENDARIO_PRODUZIONE",
        "STOCK",
    ]:
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
        },
        {
            "VARIETA": "Basilico",
            "CODICE": "BAS",
            "GRAMMI_SET": "10",
            "IDRATAZIONE_ORE": "0",
            "GERMINAZIONE_GG": "3",
            "LUCE_GG": "7",
            "TOTALE_GG": "10",
            "STATO": "ATTIVO",
            "NOTE": "Demo ordine ricorrente",
        },
        {
            "VARIETA": "Amaranto",
            "CODICE": "AMA",
            "GRAMMI_SET": "8",
            "IDRATAZIONE_ORE": "0",
            "GERMINAZIONE_GG": "3",
            "LUCE_GG": "7",
            "TOTALE_GG": "10",
            "STATO": "ATTIVO",
            "NOTE": "Demo ordine ricorrente",
        },
        {
            "VARIETA": "Finocchietto",
            "CODICE": "FIN",
            "GRAMMI_SET": "3",
            "IDRATAZIONE_ORE": "0",
            "GERMINAZIONE_GG": "4",
            "LUCE_GG": "8",
            "TOTALE_GG": "12",
            "STATO": "ATTIVO",
            "NOTE": "Demo ordine ricorrente",
        },
    ]
    sheets["MASTER_VARIETA"] = _sheet_from_dicts("MASTER_VARIETA", master_headers, master_rows)

    for sheet_name in ["INVENTARIO", "RICETTE_PRODUZIONE"]:
        headers = RESOURCE_HEADERS[sheet_name]
        rows = [list(row) for row in INITIAL_ROWS[sheet_name]]
        if sheet_name == "INVENTARIO":
            rows.extend(
                [
                    ["SEM-BAS", "500", "0", "500", "g", "", "OK", "Demo", "2026-07-12", "Demo ordine ricorrente"],
                    ["SEM-AMA", "500", "0", "500", "g", "", "OK", "Demo", "2026-07-12", "Demo ordine ricorrente"],
                    ["SEM-FIN", "500", "0", "500", "g", "", "OK", "Demo", "2026-07-12", "Demo ordine ricorrente"],
                ]
            )
        if sheet_name == "RICETTE_PRODUZIONE":
            rows.extend(
                [
                    ["MICROGREENS", "Basilico", "Standard", "SEMINA", "Semi basilico", "SEM-BAS", "10", "g", "1 set", "ATTIVA", "Demo ordine ricorrente"],
                    ["MICROGREENS", "Basilico", "Standard", "CICLO_COMPLETO", "Vaschetta", "CON-VAS", "4", "unita", "1 set", "ATTIVA", ""],
                    ["MICROGREENS", "Basilico", "Standard", "SEMINA", "Substrato cocco", "SUB-COC", "4", "unita", "1 set", "ATTIVA", ""],
                    ["MICROGREENS", "Amaranto", "Standard", "SEMINA", "Semi amaranto", "SEM-AMA", "8", "g", "1 set", "ATTIVA", "Demo ordine ricorrente"],
                    ["MICROGREENS", "Amaranto", "Standard", "CICLO_COMPLETO", "Vaschetta", "CON-VAS", "4", "unita", "1 set", "ATTIVA", ""],
                    ["MICROGREENS", "Amaranto", "Standard", "SEMINA", "Substrato cocco", "SUB-COC", "4", "unita", "1 set", "ATTIVA", ""],
                    ["MICROGREENS", "Finocchietto", "Standard", "SEMINA", "Semi finocchietto", "SEM-FIN", "3", "g", "1 set", "ATTIVA", "Demo ordine ricorrente"],
                    ["MICROGREENS", "Finocchietto", "Standard", "CICLO_COMPLETO", "Vaschetta", "CON-VAS", "4", "unita", "1 set", "ATTIVA", ""],
                    ["MICROGREENS", "Finocchietto", "Standard", "SEMINA", "Substrato cocco", "SUB-COC", "4", "unita", "1 set", "ATTIVA", ""],
                ]
            )
        sheets[sheet_name] = SheetData(
            sheet_name,
            headers,
            [dict(zip(headers, row)) for row in rows],
            [headers, *rows],
            provenance=build_google_sheets_provenance(
                sheet_name,
                "demo",
                [headers, *rows],
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


def _parse_sheet_date(value: Any) -> date | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _parse_number(value: Any) -> float | None:
    try:
        return float(str(value or "").strip().replace(",", "."))
    except ValueError:
        return None


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)
