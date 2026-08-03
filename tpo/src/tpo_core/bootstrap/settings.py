"""Caricamento e validazione della configurazione del bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


class InvalidSettingsError(ValueError):
    """Configurazione assente, illeggibile o non valida."""


@dataclass(frozen=True)
class ApplicationSettings:
    """Configurazione minima necessaria alla composizione dell'applicazione."""

    spreadsheet_id: str
    credentials_file: str
    scopes: tuple[str, ...]
    programmi_fornitura_sheet: str
    ordini_sheet: str


def load_settings(path: str | Path) -> ApplicationSettings:
    """Carica un file YAML e ne valida esclusivamente i dati del bootstrap."""

    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InvalidSettingsError(
            f"Impossibile caricare la configurazione da {config_path}."
        ) from exc

    if not isinstance(raw, Mapping):
        raise InvalidSettingsError("La configurazione deve essere una mappa YAML.")

    google_sheets = raw.get("google_sheets")
    if not isinstance(google_sheets, Mapping):
        raise InvalidSettingsError("La sezione google_sheets è obbligatoria.")

    spreadsheet_id = _required_string(google_sheets, "spreadsheet_id")
    credentials_file = _required_string(google_sheets, "credentials_file")
    scopes = _non_empty_strings(google_sheets.get("scopes"), "google_sheets.scopes")
    sheet_names = _sheet_names(google_sheets.get("sheets"))
    for required in ("PROGRAMMI_FORNITURA", "ORDINI"):
        if required not in sheet_names:
            raise InvalidSettingsError(
                f"Il foglio {required} è obbligatorio nella configurazione."
            )

    return ApplicationSettings(
        spreadsheet_id=spreadsheet_id,
        credentials_file=credentials_file,
        scopes=scopes,
        programmi_fornitura_sheet="PROGRAMMI_FORNITURA",
        ordini_sheet="ORDINI",
    )


def _required_string(section: Mapping[str, Any], key: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidSettingsError(f"google_sheets.{key} deve essere una stringa non vuota.")
    return value


def _sheet_names(value: Any) -> tuple[str, ...]:
    names = _non_empty_strings(value, "google_sheets.sheets")
    if len(set(names)) != len(names):
        raise InvalidSettingsError("google_sheets.sheets contiene nomi duplicati.")
    return names


def _non_empty_strings(value: Any, key: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise InvalidSettingsError(f"{key} deve essere una lista non vuota di stringhe.")
    return tuple(value)
