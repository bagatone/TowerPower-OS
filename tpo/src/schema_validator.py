from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .sheets_loader import SheetData


@dataclass(frozen=True)
class SheetSchema:
    sheet_name: str
    headers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationIssue:
    sheet_name: str
    level: str
    message: str


class SchemaValidator:
    def parse_schema(self, markdown: str) -> dict[str, SheetSchema]:
        schemas: dict[str, SheetSchema] = {}
        current_sheet: str | None = None
        field_table_mode = False

        for line in markdown.splitlines():
            sheet = self._extract_sheet_name(line)
            if sheet:
                current_sheet = sheet
                field_table_mode = False
                schemas.setdefault(current_sheet, SheetSchema(sheet_name=current_sheet))
                continue

            if not current_sheet:
                continue

            headers, is_field_table = self._extract_headers(line, field_table_mode)
            field_table_mode = is_field_table
            if headers:
                existing = list(schemas[current_sheet].headers)
                for header in headers:
                    if header and header not in existing:
                        existing.append(header)
                schemas[current_sheet] = SheetSchema(current_sheet, existing)

        return schemas

    def validate(
        self, sheets: dict[str, SheetData], schemas: dict[str, SheetSchema]
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        for sheet_name, schema in schemas.items():
            sheet = sheets.get(sheet_name)
            if not sheet:
                issues.append(
                    ValidationIssue(sheet_name, "ERROR", "Foglio mancante in Google Sheets.")
                )
                continue

            sheet_header_keys = {self._canonical(header) for header in sheet.headers}
            schema_header_keys = {self._canonical(header) for header in schema.headers}
            missing = [
                header
                for header in schema.headers
                if self._canonical(header) not in sheet_header_keys
            ]
            extra = [
                header
                for header in sheet.headers
                if self._canonical(header) not in schema_header_keys
            ]

            if missing:
                issues.append(
                    ValidationIssue(
                        sheet_name,
                        "ERROR",
                        f"Intestazioni mancanti: {', '.join(missing)}",
                    )
                )
            if extra and schema.headers:
                issues.append(
                    ValidationIssue(
                        sheet_name,
                        "WARN",
                        f"Intestazioni non presenti nello schema: {', '.join(extra)}",
                    )
                )

        return issues

    def _extract_sheet_name(self, line: str) -> str | None:
        normalized = line.strip().strip("#").strip()
        known_prefixes = ("Foglio:", "Sheet:", "Tabella:", "TABLE:")
        for prefix in known_prefixes:
            if normalized.lower().startswith(prefix.lower()):
                return normalized[len(prefix) :].strip().upper()

        if normalized.isupper() and re.fullmatch(r"[A-Z0-9_]+", normalized):
            return normalized

        match = re.match(r"^#+\s+([A-Z0-9_]+)\s*$", line.strip())
        return match.group(1) if match else None

    def _extract_headers(self, line: str, field_table_mode: bool) -> tuple[list[str], bool]:
        stripped = line.strip()
        if not stripped:
            return [], False

        lower = stripped.lower()
        if lower.startswith(("headers:", "intestazioni:", "colonne:", "columns:")):
            return self._split_headers(stripped.split(":", 1)[1]), False

        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            lower_cells = {cell.lower() for cell in cells}
            if all(set(cell) <= {"-", ":"} for cell in cells):
                return [], field_table_mode
            if not {"campo", "field", "colonna", "column"}.isdisjoint(lower_cells):
                return [], True
            if field_table_mode and cells:
                return [cells[0]], True
            if cells:
                return [cell for cell in cells if cell], False

        if " | " in stripped:
            return self._split_headers(stripped), False

        bullet = re.match(r"^[-*]\s+`?([A-Za-z0-9_ ]+)`?\s*$", stripped)
        if bullet:
            return [bullet.group(1).strip()], False

        return [], False

    def _split_headers(self, value: str) -> list[str]:
        return [header.strip().strip("`") for header in re.split(r"[,;|]", value) if header.strip()]

    def _canonical(self, value: str) -> str:
        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFKD", value)
            if not unicodedata.combining(char)
        )
        return re.sub(r"[\s_]+", "", without_accents).upper()
