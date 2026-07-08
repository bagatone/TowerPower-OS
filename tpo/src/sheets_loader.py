from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class SheetsLoaderError(RuntimeError):
    pass


REQUIRED_SHEETS = [
    "CLIENTI",
    "CONSEGNE",
    "LOTTI",
    "SEMINE",
    "RACCOLTI",
    "STOCK",
    "MASTER_VARIETA",
    "PROBLEMI",
    "PIANO_SEMINE",
    "CALENDARIO_PRODUZIONE",
    "PIANO_EXTRA",
    "BRIEFING_GIORNALIERO",
    "PHOTO_BANK_INDEX",
]


@dataclass(frozen=True)
class SheetData:
    name: str
    headers: list[str]
    rows: list[dict[str, str]]
    raw_values: list[list[str]]


class SheetsLoader:
    def __init__(
        self,
        spreadsheet_id: str,
        credentials_file: str | Path,
        scopes: list[str] | None = None,
    ) -> None:
        self.spreadsheet_id = spreadsheet_id
        self.credentials_file = Path(credentials_file)
        self.scopes = scopes or ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SheetsLoader":
        sheets_config = config.get("google_sheets", {})
        return cls(
            spreadsheet_id=sheets_config["spreadsheet_id"],
            credentials_file=sheets_config["credentials_file"],
            scopes=sheets_config.get("scopes"),
        )

    def load_required_sheets(
        self,
        names: list[str] | None = None,
        expected_headers: dict[str, list[str]] | None = None,
    ) -> dict[str, SheetData]:
        sheet_names = names or REQUIRED_SHEETS
        service = self._build_service()
        result: dict[str, SheetData] = {}

        for name in sheet_names:
            values = self._read_values(service, f"{name}!A:ZZ")
            result[name] = self._to_sheet_data(
                name,
                values,
                expected_headers=(expected_headers or {}).get(name),
            )

        return result

    def _build_service(self):
        if not self.credentials_file.exists():
            raise FileNotFoundError(
                f"Credenziali Google non trovate: {self.credentials_file}"
            )

        credentials = service_account.Credentials.from_service_account_file(
            self.credentials_file,
            scopes=self.scopes,
        )
        return build("sheets", "v4", credentials=credentials)

    def _read_values(self, service, range_name: str) -> list[list[str]]:
        try:
            response = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=range_name)
                .execute()
            )
        except HttpError as exc:
            if exc.resp.status == 400 and "Unable to parse range" in str(exc):
                return []
            raise SheetsLoaderError(f"Google Sheets non disponibile: {exc}") from exc
        except Exception as exc:
            raise SheetsLoaderError(f"Google Sheets non disponibile: {exc}") from exc
        return response.get("values", [])

    def _to_sheet_data(
        self,
        name: str,
        values: list[list[str]],
        expected_headers: list[str] | None = None,
    ) -> SheetData:
        if not values:
            return SheetData(name=name, headers=[], rows=[], raw_values=[])

        cleaned_values = self._drop_leading_empty_rows(values)
        if not cleaned_values:
            return SheetData(name=name, headers=[], rows=[], raw_values=values)

        header_index = self._find_header_index(cleaned_values, expected_headers)
        if header_index is None and expected_headers:
            headers = expected_headers
            data_rows = cleaned_values
        else:
            header_index = header_index or 0
            headers = [cell.strip() for cell in cleaned_values[header_index]]
            data_rows = cleaned_values[header_index + 1 :]

        rows: list[dict[str, str]] = []
        for raw_row in data_rows:
            normalized = raw_row + [""] * max(0, len(headers) - len(raw_row))
            rows.append(dict(zip(headers, normalized[: len(headers)])))

        return SheetData(name=name, headers=headers, rows=rows, raw_values=values)

    def _drop_leading_empty_rows(self, values: list[list[str]]) -> list[list[str]]:
        for index, row in enumerate(values):
            if any(str(cell).strip() for cell in row):
                return values[index:]
        return []

    def _find_header_index(
        self,
        values: list[list[str]],
        expected_headers: list[str] | None,
    ) -> int | None:
        if not expected_headers:
            return 0

        expected = set(expected_headers)
        for index, row in enumerate(values[:10]):
            cells = [cell.strip() for cell in row]
            matching_headers = sum(1 for cell in cells if cell in expected)
            if matching_headers >= max(1, min(3, len(expected_headers))):
                return index
        return None
