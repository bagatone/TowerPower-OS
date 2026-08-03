"""Gateway runtime per Google Sheets API, privo di conoscenza del dominio."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .errors import (
    GoogleSheetsRepositoryError,
    InvalidSheetRowError,
    InvalidSheetSchemaError,
)


DEFAULT_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


def build_google_sheets_service(
    credentials_path: str | Path,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
) -> Any:
    """Costruisce esplicitamente un client Google Sheets da service account."""

    try:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=list(scopes),
        )
        return build("sheets", "v4", credentials=credentials)
    except (GoogleAuthError, OSError, ValueError) as exc:
        raise GoogleSheetsRepositoryError(
            "Impossibile costruire il servizio Google Sheets con le credenziali fornite."
        ) from exc


class GoogleApiSheetsGateway:
    """Implementazione di GoogleSheetsGateway basata sul client Google API."""

    def __init__(self, service: Any) -> None:
        self._service = service

    def list_sheet_names(self, *, spreadsheet_id: str) -> tuple[str, ...]:
        """Legge esclusivamente i titoli dei fogli dallo spreadsheet metadata."""

        try:
            response = (
                self._service.spreadsheets()
                .get(
                    spreadsheetId=spreadsheet_id,
                    fields="sheets.properties.title",
                )
                .execute()
            )
        except HttpError as exc:
            raise GoogleSheetsRepositoryError(
                self._error_message("lettura metadata", spreadsheet_id, "<metadata>")
            ) from exc
        sheets = response.get("sheets", [])
        if not isinstance(sheets, list):
            raise GoogleSheetsRepositoryError(
                self._error_message("validazione metadata", spreadsheet_id, "<metadata>")
            )
        titles: list[str] = []
        for sheet in sheets:
            if not isinstance(sheet, dict):
                raise GoogleSheetsRepositoryError("Metadata dei fogli Google non validi.")
            properties = sheet.get("properties")
            title = properties.get("title") if isinstance(properties, dict) else None
            if not isinstance(title, str) or not title:
                raise GoogleSheetsRepositoryError("Titolo di un foglio Google non valido.")
            titles.append(title)
        return tuple(titles)

    def read_headers(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
    ) -> tuple[str, ...]:
        """Legge e valida esclusivamente la riga fisica delle intestazioni."""

        values = self._read_values(
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            operation="lettura intestazioni",
        )
        if not values:
            raise InvalidSheetSchemaError(
                f"{sheet_name}: riga delle intestazioni mancante."
            )
        return self._headers(values, sheet_name)

    def read_rows(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
    ) -> tuple[dict[str, str], ...]:
        values = self._read_values(
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            operation="lettura",
        )
        if not values:
            return ()
        headers = self._headers(values, sheet_name)
        result: list[dict[str, str]] = []
        for row_number, physical_row in enumerate(values[1:], start=2):
            cells = tuple(str(value) for value in physical_row)
            if not cells or all(value == "" for value in cells):
                continue
            if len(cells) > len(headers):
                raise InvalidSheetRowError(
                    f"{sheet_name} riga {row_number}: più celle ({len(cells)}) "
                    f"delle intestazioni ({len(headers)})."
                )
            padded = cells + ("",) * (len(headers) - len(cells))
            result.append(dict(zip(headers, padded)))
        return tuple(result)

    def append_rows(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
        rows: tuple[dict[str, str], ...],
    ) -> None:
        if not rows:
            return
        values = self._read_values(
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            operation="verifica schema prima dell'append",
        )
        if not values:
            raise InvalidSheetSchemaError(
                f"{sheet_name}: foglio vuoto, intestazioni non disponibili."
            )
        headers = self._headers(values, sheet_name)
        serialized: list[list[str]] = []
        for row_number, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise InvalidSheetRowError(
                    f"{sheet_name} append riga {row_number}: atteso dict."
                )
            actual = tuple(row.keys())
            if actual != headers:
                raise InvalidSheetSchemaError(
                    f"{sheet_name} append riga {row_number}: schema o ordine colonne "
                    f"non valido; atteso={list(headers)}, trovato={list(actual)}."
                )
            if any(not isinstance(value, str) for value in row.values()):
                raise InvalidSheetRowError(
                    f"{sheet_name} append riga {row_number}: tutti i valori devono essere stringhe."
                )
            serialized.append([row[header] for header in headers])

        try:
            (
                self._service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=spreadsheet_id,
                    range=self._a1_range(sheet_name),
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": serialized},
                )
                .execute()
            )
        except HttpError as exc:
            raise GoogleSheetsRepositoryError(
                self._error_message("append", spreadsheet_id, sheet_name)
            ) from exc

    def _read_values(
        self,
        *,
        spreadsheet_id: str,
        sheet_name: str,
        operation: str,
    ) -> list[list[Any]]:
        try:
            response = (
                self._service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=spreadsheet_id,
                    range=self._a1_range(sheet_name),
                )
                .execute()
            )
        except HttpError as exc:
            raise GoogleSheetsRepositoryError(
                self._error_message(operation, spreadsheet_id, sheet_name)
            ) from exc
        values = response.get("values", [])
        if not isinstance(values, list) or any(not isinstance(row, list) for row in values):
            raise InvalidSheetSchemaError(
                f"{sheet_name}: risposta Google Sheets priva di una matrice values valida."
            )
        return values

    @staticmethod
    def _headers(values: list[list[Any]], sheet_name: str) -> tuple[str, ...]:
        raw_headers = values[0]
        if not raw_headers:
            raise InvalidSheetSchemaError(f"{sheet_name}: riga delle intestazioni mancante.")
        headers = tuple(str(value) for value in raw_headers)
        if any(header == "" for header in headers):
            raise InvalidSheetSchemaError(f"{sheet_name}: intestazione vuota non consentita.")
        if len(set(headers)) != len(headers):
            raise InvalidSheetSchemaError(f"{sheet_name}: intestazioni duplicate non consentite.")
        return headers

    @staticmethod
    def _a1_range(sheet_name: str) -> str:
        if not isinstance(sheet_name, str) or not sheet_name:
            raise InvalidSheetSchemaError("Nome del foglio mancante.")
        escaped = sheet_name.replace("'", "''")
        return f"'{escaped}'!A:ZZ"

    @staticmethod
    def _masked_spreadsheet_id(spreadsheet_id: str) -> str:
        if len(spreadsheet_id) <= 4:
            return "***"
        return f"{spreadsheet_id[:2]}***{spreadsheet_id[-2:]}"

    @classmethod
    def _error_message(cls, operation: str, spreadsheet_id: str, sheet_name: str) -> str:
        return (
            f"Errore Google Sheets durante {operation}; "
            f"spreadsheet_id={cls._masked_spreadsheet_id(spreadsheet_id)}, "
            f"sheet_name={sheet_name!r}."
        )
