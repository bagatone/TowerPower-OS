from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config_loader import load_config
from .schema_validator import SchemaValidator


WRITE_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
DEFAULT_SCHEMA_PATH = Path("docs/TPO_SHEETS_SCHEMA.md")
DEFAULT_LOG_DIR = Path("outputs/write_logs")


class SheetsWriterError(RuntimeError):
    pass


@dataclass(frozen=True)
class WriteOperation:
    sheet_name: str
    mode: str
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class WritePlan:
    operations: list[WriteOperation]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WritePlan":
        operations = [
            WriteOperation(
                sheet_name=str(item.get("sheet_name", "")).strip(),
                mode=str(item.get("mode", "")).strip(),
                rows=list(item.get("rows", [])),
            )
            for item in data.get("operations", [])
        ]
        return cls(operations=operations)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "WritePlan":
        with Path(path).open("r", encoding="utf-8") as file:
            return cls.from_dict(json.load(file))


@dataclass
class WriteResult:
    mode: str
    success: bool
    rows_requested: dict[str, int] = field(default_factory=dict)
    rows_valid: dict[str, int] = field(default_factory=dict)
    rows_written: dict[str, int] = field(default_factory=dict)
    duplicates: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    log_path: str | None = None


DEDUP_KEYS = {
    "CLIENTI": [["CLIENTE"]],
    "CONSEGNE": [["CLIENTE", "PRODOTTO", "PROSSIMA_CONSEGNA", "ID_LOTTO"]],
    "LOTTI": [["CALENDARIO_PROD"], ["ID_LOTTO"]],
    "SEMINE": [["ID_LOTTO"]],
    "RACCOLTI": [["ID_LOTTO"]],
    "STOCK": [["VARIETA"]],
    "PROBLEMI": [["DATA", "AREA", "PROBLEMA"]],
    "PIANO_SEMINE": [["DATA_SEMINA", "VARIETA", "CLIENTE_DESTINAZIONE"]],
    "CALENDARIO_PRODUZIONE": [["DATA", "EVENTO", "ID_LOTTO"]],
    "PHOTO_BANK_INDEX": [["ID_FOTO"], ["PHOTO_ID"], ["ID"], ["FILE_NAME"], ["NOME_FILE"]],
    "ANAGRAFICA_ARTICOLI": [["ID_ARTICOLO"]],
    "INVENTARIO": [["ID_ARTICOLO"]],
    "MOVIMENTI_MAGAZZINO": [["ID_MOVIMENTO"]],
    "RICETTE_PRODUZIONE": [["TIPO_PRODUZIONE", "PRODOTTO", "VARIANTE", "FASE", "ID_ARTICOLO"]],
    "FORNITORI": [["ID_FORNITORE"]],
}


class SheetsWriter:
    def __init__(
        self,
        spreadsheet_id: str | None = None,
        service: Any | None = None,
        schema_path: str | Path = DEFAULT_SCHEMA_PATH,
        log_dir: str | Path = DEFAULT_LOG_DIR,
        allow_offline: bool = False,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id
        self.service = service
        self.schema_path = Path(schema_path)
        self.log_dir = Path(log_dir)
        self.allow_offline = allow_offline

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SheetsWriter":
        sheets_config = config.get("google_sheets", {})
        credentials_file = Path(sheets_config["credentials_file"])
        if not credentials_file.exists():
            raise FileNotFoundError(f"Credenziali Google non trovate: {credentials_file}")
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=[WRITE_SCOPE],
        )
        service = build("sheets", "v4", credentials=credentials)
        return cls(
            spreadsheet_id=sheets_config["spreadsheet_id"],
            service=service,
        )

    @classmethod
    def from_config_path(
        cls,
        config_path: str | Path = "config/settings.yaml",
        allow_offline: bool = False,
    ) -> "SheetsWriter":
        path = Path(config_path)
        if allow_offline and not path.exists():
            return cls(allow_offline=True)
        return cls.from_config(load_config(path))

    def dry_run(self, plan: WritePlan) -> WriteResult:
        result, _ = self._preflight(plan)
        result.mode = "dry-run"
        result.success = not result.errors
        result.log_path = self._write_log(result, plan)
        return result

    def apply(self, plan: WritePlan) -> WriteResult:
        result, prepared = self._preflight(plan)
        result.mode = "apply"
        if result.errors:
            result.success = False
            result.log_path = self._write_log(result, plan)
            return result
        if not self.service or not self.spreadsheet_id:
            raise SheetsWriterError("Configurazione Google Sheets mancante: impossibile applicare.")

        data = [
            {"range": f"{sheet_name}!A{start_row}", "values": rows}
            for sheet_name, start_row, rows in self._merge_prepared_rows(prepared)
            if rows
        ]
        if data:
            (
                self.service.spreadsheets()
                .values()
                .batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"valueInputOption": "RAW", "data": data},
                )
                .execute()
            )
        result.rows_written = {
            sheet_name: len(rows)
            for sheet_name, _, rows in self._merge_prepared_rows(prepared)
        }
        result.success = True
        result.log_path = self._write_log(result, plan)
        return result

    def _preflight(self, plan: WritePlan) -> tuple[WriteResult, list[tuple[str, int, list[list[str]]]]]:
        schemas = self._load_schema()
        result = WriteResult(mode="preflight", success=False)
        prepared: list[tuple[str, int, list[list[str]]]] = []
        if not plan.operations:
            result.errors.append("Piano vuoto: nessuna operazione presente.")
            return result, prepared

        seen_new_keys: dict[str, set[tuple[str, ...]]] = {}
        for operation in plan.operations:
            sheet_name = operation.sheet_name
            result.rows_requested[sheet_name] = result.rows_requested.get(sheet_name, 0) + len(operation.rows)
            errors_before = len(result.errors)

            if operation.mode != "append":
                result.errors.append(f"{sheet_name}: mode non supportato: {operation.mode}")
                continue
            headers = schemas.get(sheet_name)
            if not headers:
                result.errors.append(f"{sheet_name}: foglio non presente nello schema ufficiale.")
                continue

            existing_values = self._read_existing_values(sheet_name, result)
            if existing_values is None:
                continue
            if existing_values:
                current_headers = [cell.strip() for cell in existing_values[0]]
                if current_headers != headers:
                    result.errors.append(
                        f"{sheet_name}: intestazioni reali incompatibili. "
                        f"Attese {headers}, trovate {current_headers}"
                    )
                    continue
                existing_rows = existing_values[1:]
            else:
                if not self.allow_offline:
                    result.errors.append(f"{sheet_name}: foglio mancante o vuoto nel Google Sheet.")
                    continue
                existing_rows = []

            key_columns = self._dedup_key(sheet_name, headers, result)
            if not key_columns:
                continue

            existing_keys = self._existing_keys(headers, existing_rows, key_columns)
            seen_new_keys.setdefault(sheet_name, set())
            normalized_rows: list[list[str]] = []
            for row_index, row in enumerate(operation.rows, start=1):
                normalized = self._normalize_row(sheet_name, headers, row, row_index, result)
                if normalized is None:
                    continue
                row_key = self._row_key_from_dict(row, key_columns)
                if row_key in existing_keys or row_key in seen_new_keys[sheet_name]:
                    result.duplicates.setdefault(sheet_name, []).append(row)
                    result.errors.append(f"{sheet_name} riga {row_index}: duplicato su chiave {key_columns}.")
                    continue
                seen_new_keys[sheet_name].add(row_key)
                normalized_rows.append(normalized)

            result.rows_valid[sheet_name] = result.rows_valid.get(sheet_name, 0) + len(normalized_rows)
            if len(result.errors) == errors_before:
                prepared.append((sheet_name, len(existing_rows) + 2, normalized_rows))

        return result, prepared

    def _load_schema(self) -> dict[str, list[str]]:
        markdown = self.schema_path.read_text(encoding="utf-8")
        parsed = SchemaValidator().parse_schema(markdown)
        return {sheet_name: schema.headers for sheet_name, schema in parsed.items()}

    def _merge_prepared_rows(
        self,
        prepared: list[tuple[str, int, list[list[str]]]],
    ) -> list[tuple[str, int, list[list[str]]]]:
        merged: dict[str, tuple[int, list[list[str]]]] = {}
        for sheet_name, start_row, rows in prepared:
            if sheet_name not in merged:
                merged[sheet_name] = (start_row, [])
            merged[sheet_name][1].extend(rows)
        return [
            (sheet_name, start_row, rows)
            for sheet_name, (start_row, rows) in merged.items()
        ]

    def _read_existing_values(self, sheet_name: str, result: WriteResult) -> list[list[str]] | None:
        if self.allow_offline and not self.service:
            return []
        if not self.service or not self.spreadsheet_id:
            result.errors.append("Configurazione Google Sheets mancante.")
            return None
        try:
            response = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=f"{sheet_name}!A:ZZ")
                .execute()
            )
            return response.get("values", [])
        except Exception as exc:
            result.errors.append(f"{sheet_name}: foglio mancante o non leggibile: {exc}")
            return None

    def _dedup_key(
        self,
        sheet_name: str,
        headers: list[str],
        result: WriteResult,
    ) -> list[str] | None:
        for candidate in DEDUP_KEYS.get(sheet_name, []):
            if all(column in headers for column in candidate):
                return candidate
        result.errors.append(f"{sheet_name}: chiave di deduplicazione non configurata.")
        return None

    def _normalize_row(
        self,
        sheet_name: str,
        headers: list[str],
        row: dict[str, Any],
        row_index: int,
        result: WriteResult,
    ) -> list[str] | None:
        if not isinstance(row, dict):
            result.errors.append(f"{sheet_name} riga {row_index}: la riga deve essere un oggetto JSON.")
            return None
        unknown = sorted(set(row) - set(headers))
        if unknown:
            result.errors.append(f"{sheet_name} riga {row_index}: colonne sconosciute: {', '.join(unknown)}")
            return None
        values = [str(row.get(header, "") or "") for header in headers]
        if not any(value.strip() for value in values):
            result.errors.append(f"{sheet_name} riga {row_index}: riga completamente vuota.")
            return None
        return values

    def _existing_keys(
        self,
        headers: list[str],
        rows: list[list[str]],
        key_columns: list[str],
    ) -> set[tuple[str, ...]]:
        indexes = [headers.index(column) for column in key_columns]
        return {
            tuple((row[index] if index < len(row) else "").strip() for index in indexes)
            for row in rows
        }

    def _row_key_from_dict(self, row: dict[str, Any], key_columns: list[str]) -> tuple[str, ...]:
        return tuple(str(row.get(column, "") or "").strip() for column in key_columns)

    def _write_log(self, result: WriteResult, plan: WritePlan) -> str:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.log_dir / f"write-{timestamp}.json"
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "mode": result.mode,
            "sheets": [operation.sheet_name for operation in plan.operations],
            "rows_requested": result.rows_requested,
            "rows_valid": result.rows_valid,
            "rows_written": result.rows_written,
            "duplicates": result.duplicates,
            "errors": result.errors,
            "success": result.success,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)
