from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .config_loader import load_config


WRITE_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


RESOURCE_HEADERS = {
    "ANAGRAFICA_ARTICOLI": [
        "ID_ARTICOLO",
        "CATEGORIA",
        "ARTICOLO",
        "VARIANTE",
        "UNITA_MISURA",
        "TRACCIABILE",
        "CONSERVAZIONE",
        "SCADENZA_GESTITA",
        "UTILIZZO",
        "STATO",
        "NOTE",
    ],
    "INVENTARIO": [
        "ID_ARTICOLO",
        "QUANTITA_DISPONIBILE",
        "QUANTITA_IMPEGNATA",
        "QUANTITA_DISPONIBILE_REALE",
        "UNITA_MISURA",
        "SCORTA_MINIMA",
        "STATO_SCORTA",
        "UBICAZIONE",
        "ULTIMO_AGGIORNAMENTO",
        "NOTE",
    ],
    "MOVIMENTI_MAGAZZINO": [
        "DATA",
        "ID_MOVIMENTO",
        "ID_ARTICOLO",
        "TIPO_MOVIMENTO",
        "QUANTITA",
        "UNITA_MISURA",
        "CAUSALE",
        "ID_LOTTO",
        "OPERATORE",
        "DOCUMENTO_RIFERIMENTO",
        "NOTE",
    ],
    "RICETTE_PRODUZIONE": [
        "TIPO_PRODUZIONE",
        "PRODOTTO",
        "VARIANTE",
        "FASE",
        "RISORSA",
        "ID_ARTICOLO",
        "QUANTITA_PER_UNITA",
        "UNITA_MISURA",
        "BASE_CALCOLO",
        "STATO",
        "NOTE",
    ],
    "FORNITORI": [
        "ID_FORNITORE",
        "RAGIONE_SOCIALE",
        "CONTATTO",
        "EMAIL",
        "TELEFONO",
        "SITO_WEB",
        "TEMPO_CONSEGNA_GG",
        "STATO",
        "NOTE",
    ],
}


INITIAL_ROWS = {
    "ANAGRAFICA_ARTICOLI": [
        ["SEM-RAB", "SEMI", "Rábano morado", "Microgreens", "g", "SI", "Ambiente asciutto", "SI", "Microgreens", "ATTIVO", ""],
        ["SEM-AFI", "SEMI", "Guisante Afila", "Microgreens", "g", "SI", "Ambiente asciutto", "SI", "Microgreens", "ATTIVO", ""],
        ["SEM-LEN", "SEMI", "Lenticchie", "Microgreens", "g", "SI", "Ambiente asciutto", "SI", "Microgreens", "ATTIVO", ""],
        ["SEM-COL", "SEMI", "Col Roja", "Microgreens", "g", "SI", "Ambiente asciutto", "SI", "Microgreens", "ATTIVO", ""],
        ["SEM-GIR", "SEMI", "Girasole", "Microgreens", "g", "SI", "Ambiente asciutto", "SI", "Microgreens", "ATTIVO", ""],
        ["SEM-CIL", "SEMI", "Cilantro", "Microgreens", "g", "SI", "Ambiente asciutto", "SI", "Microgreens", "ATTIVO", ""],
        ["SEM-MOS", "SEMI", "Mostaza", "Microgreens", "g", "SI", "Ambiente asciutto", "SI", "Microgreens", "ATTIVO", ""],
        ["SEM-MIZ", "SEMI", "Mizuna Roja", "Microgreens", "g", "SI", "Ambiente asciutto", "SI", "Microgreens", "ATTIVO", ""],
        ["SEM-FIN", "SEMI", "Finocchietto", "Microgreens", "g", "SI", "Ambiente asciutto", "SI", "Microgreens", "ATTIVO", ""],
        ["CON-VAS", "CONTENITORI", "Vaschetta", "Standard microgreens", "unita", "NO", "Magazzino", "NO", "Microgreens", "ATTIVO", "1 set = 4 vaschette"],
        ["SUB-COC", "SUBSTRATI", "Substrato cocco", "Disco per vaschetta", "unita", "NO", "Ambiente asciutto", "NO", "Microgreens", "ATTIVO", "1 disco per vaschetta"],
    ],
    "INVENTARIO": [
        ["SEM-RAB", "408", "0", "408", "g", "", "DA_CONFIGURARE", "Magazzino semi", "10/07/2026", "Quantità iniziale dichiarata"],
        ["SEM-AFI", "4780", "0", "4780", "g", "", "DA_CONFIGURARE", "Magazzino semi", "10/07/2026", "Quantità iniziale dichiarata"],
        ["SEM-LEN", "660", "0", "660", "g", "", "DA_CONFIGURARE", "Magazzino semi", "10/07/2026", "Quantità iniziale dichiarata"],
        ["SEM-COL", "770", "0", "770", "g", "", "DA_CONFIGURARE", "Magazzino semi", "10/07/2026", "Quantità iniziale dichiarata"],
        ["SEM-GIR", "327", "0", "327", "g", "", "DA_CONFIGURARE", "Magazzino semi", "10/07/2026", "Quantità iniziale dichiarata"],
        ["SEM-CIL", "480", "0", "480", "g", "", "DA_CONFIGURARE", "Magazzino semi", "10/07/2026", "Quantità iniziale dichiarata"],
        ["SEM-MOS", "700", "0", "700", "g", "", "DA_CONFIGURARE", "Magazzino semi", "10/07/2026", "Quantità iniziale dichiarata"],
        ["SEM-MIZ", "613", "0", "613", "g", "", "DA_CONFIGURARE", "Magazzino semi", "10/07/2026", "Quantità iniziale dichiarata"],
        ["SEM-FIN", "0", "0", "0", "g", "", "ESAURITO", "Magazzino semi", "10/07/2026", "Quantità iniziale dichiarata"],
        ["CON-VAS", "1152", "0", "1152", "unita", "", "DA_CONFIGURARE", "Magazzino materiali", "10/07/2026", "1 set = 4 vaschette"],
        ["SUB-COC", "1100", "0", "1100", "unita", "", "DA_CONFIGURARE", "Magazzino substrati", "10/07/2026", "1 substrato per vaschetta"],
    ],
    "MOVIMENTI_MAGAZZINO": [
        ["10/07/2026", "MOV-20260710-001", "SEM-RAB", "INVENTARIO_INIZIALE", "408", "g", "Caricamento inventario iniziale", "", "Matteo", "", "Quantità iniziale dichiarata"],
        ["10/07/2026", "MOV-20260710-002", "SEM-AFI", "INVENTARIO_INIZIALE", "4780", "g", "Caricamento inventario iniziale", "", "Matteo", "", "Quantità iniziale dichiarata"],
        ["10/07/2026", "MOV-20260710-003", "SEM-LEN", "INVENTARIO_INIZIALE", "660", "g", "Caricamento inventario iniziale", "", "Matteo", "", "Quantità iniziale dichiarata"],
        ["10/07/2026", "MOV-20260710-004", "SEM-COL", "INVENTARIO_INIZIALE", "770", "g", "Caricamento inventario iniziale", "", "Matteo", "", "Quantità iniziale dichiarata"],
        ["10/07/2026", "MOV-20260710-005", "SEM-GIR", "INVENTARIO_INIZIALE", "327", "g", "Caricamento inventario iniziale", "", "Matteo", "", "Quantità iniziale dichiarata"],
        ["10/07/2026", "MOV-20260710-006", "SEM-CIL", "INVENTARIO_INIZIALE", "480", "g", "Caricamento inventario iniziale", "", "Matteo", "", "Quantità iniziale dichiarata"],
        ["10/07/2026", "MOV-20260710-007", "SEM-MOS", "INVENTARIO_INIZIALE", "700", "g", "Caricamento inventario iniziale", "", "Matteo", "", "Quantità iniziale dichiarata"],
        ["10/07/2026", "MOV-20260710-008", "SEM-MIZ", "INVENTARIO_INIZIALE", "613", "g", "Caricamento inventario iniziale", "", "Matteo", "", "Quantità iniziale dichiarata"],
        ["10/07/2026", "MOV-20260710-009", "SEM-FIN", "INVENTARIO_INIZIALE", "0", "g", "Caricamento inventario iniziale", "", "Matteo", "", "Quantità iniziale dichiarata"],
        ["10/07/2026", "MOV-20260710-010", "CON-VAS", "INVENTARIO_INIZIALE", "1152", "unita", "Caricamento inventario iniziale", "", "Matteo", "", "Quantità iniziale dichiarata"],
        ["10/07/2026", "MOV-20260710-011", "SUB-COC", "INVENTARIO_INIZIALE", "1100", "unita", "Caricamento inventario iniziale", "", "Matteo", "", "Quantità iniziale dichiarata"],
    ],
    "RICETTE_PRODUZIONE": [],
    "FORNITORI": [],
}


ARTICLE_SEED_GRAMS = [
    ("Rábano Morado", "Semi rábano morado", "SEM-RAB", "14", ""),
    ("Guisante Afila", "Semi guisante afila", "SEM-AFI", "30", ""),
    ("Lenticchie", "Semi lenticchie", "SEM-LEN", "20", "Grammatura da rivalutare per densità insufficiente"),
    ("Col Roja", "Semi col roja", "SEM-COL", "14", ""),
    ("Girasole", "Semi girasole", "SEM-GIR", "20", ""),
    ("Cilantro", "Semi cilantro", "SEM-CIL", "14", ""),
    ("Mostaza", "Semi mostaza", "SEM-MOS", "12", "Problema produttivo aperto: collasso finale"),
    ("Mizuna Roja", "Semi mizuna", "SEM-MIZ", "10", ""),
    ("Finocchietto", "Semi finocchietto", "SEM-FIN", "12", ""),
]


for product, seed_resource, article_id, grams, note in ARTICLE_SEED_GRAMS:
    INITIAL_ROWS["RICETTE_PRODUZIONE"].extend(
        [
            ["MICROGREENS", product, "Standard", "SEMINA", seed_resource, article_id, grams, "g", "1 set", "ATTIVA", note],
            ["MICROGREENS", product, "Standard", "CICLO_COMPLETO", "Vaschetta", "CON-VAS", "4", "unita", "1 set", "ATTIVA", ""],
            ["MICROGREENS", product, "Standard", "SEMINA", "Substrato cocco", "SUB-COC", "4", "unita", "1 set", "ATTIVA", ""],
        ]
    )


UNIQUE_KEY_COLUMNS = {
    "ANAGRAFICA_ARTICOLI": ["ID_ARTICOLO"],
    "INVENTARIO": ["ID_ARTICOLO"],
    "MOVIMENTI_MAGAZZINO": ["ID_MOVIMENTO", "ID_ARTICOLO"],
    "RICETTE_PRODUZIONE": ["TIPO_PRODUZIONE", "PRODOTTO", "VARIANTE", "FASE", "ID_ARTICOLO"],
    "FORNITORI": ["ID_FORNITORE"],
}


@dataclass(frozen=True)
class ResourcePlan:
    sheet_names: list[str]
    headers: dict[str, list[str]]
    rows: dict[str, list[list[str]]]


def build_resource_plan() -> ResourcePlan:
    return ResourcePlan(
        sheet_names=list(RESOURCE_HEADERS),
        headers=RESOURCE_HEADERS,
        rows=INITIAL_ROWS,
    )


def validate_initial_data(plan: ResourcePlan) -> list[str]:
    errors: list[str] = []
    for sheet_name, headers in plan.headers.items():
        for row_index, row in enumerate(plan.rows[sheet_name], start=1):
            if len(row) != len(headers):
                errors.append(
                    f"{sheet_name} riga {row_index}: {len(row)} valori per {len(headers)} intestazioni"
                )
    errors.extend(_validate_recipe_units(plan.rows["RICETTE_PRODUZIONE"]))
    errors.extend(_validate_inventory_movements(plan))
    return errors


def summarize_plan(plan: ResourcePlan) -> str:
    lines = ["RESOURCE ENGINE INITIALIZATION", "Modalità: DRY_RUN"]
    for sheet_name in plan.sheet_names:
        lines.append(
            f"- {sheet_name}: {len(plan.headers[sheet_name])} colonne, "
            f"{len(plan.rows[sheet_name])} righe iniziali"
        )
    errors = validate_initial_data(plan)
    if errors:
        lines.append("Dati mancanti/anomalie:")
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("Dati mancanti/anomalie: nessuno")
    lines.append("Nessuna scrittura eseguita.")
    return "\n".join(lines)


def apply_plan(config_path: str) -> str:
    plan = build_resource_plan()
    errors = validate_initial_data(plan)
    if errors:
        raise RuntimeError("Dati iniziali non validi:\n" + "\n".join(errors))

    config = load_config(config_path)
    service = _build_write_service(config)
    spreadsheet_id = config["google_sheets"]["spreadsheet_id"]
    existing_titles = _sheet_titles(service, spreadsheet_id)
    _create_missing_sheets(service, spreadsheet_id, plan.sheet_names, existing_titles)

    summary = ["RESOURCE ENGINE INITIALIZATION", "Modalità: APPLY"]
    for sheet_name in plan.sheet_names:
        existing_values = _read_sheet(service, spreadsheet_id, sheet_name)
        _ensure_headers(service, spreadsheet_id, sheet_name, plan.headers[sheet_name], existing_values)
        existing_values = _read_sheet(service, spreadsheet_id, sheet_name)
        rows_to_append = _missing_rows(
            headers=plan.headers[sheet_name],
            existing_rows=existing_values[1:] if existing_values else [],
            desired_rows=plan.rows[sheet_name],
            key_columns=UNIQUE_KEY_COLUMNS[sheet_name],
        )
        if rows_to_append:
            _append_rows(service, spreadsheet_id, sheet_name, rows_to_append)
        summary.append(f"- {sheet_name}: aggiunte {len(rows_to_append)} righe")
    return "\n".join(summary)


def _build_write_service(config: dict[str, Any]):
    credentials_file = Path(config["google_sheets"]["credentials_file"])
    if not credentials_file.exists():
        raise FileNotFoundError(f"Credenziali Google non trovate: {credentials_file}")
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=[WRITE_SCOPE],
    )
    return build("sheets", "v4", credentials=credentials)


def _sheet_titles(service, spreadsheet_id: str) -> set[str]:
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    return {sheet["properties"]["title"] for sheet in metadata.get("sheets", [])}


def _create_missing_sheets(
    service,
    spreadsheet_id: str,
    sheet_names: list[str],
    existing_titles: set[str],
) -> None:
    requests = [
        {"addSheet": {"properties": {"title": sheet_name}}}
        for sheet_name in sheet_names
        if sheet_name not in existing_titles
    ]
    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()


def _read_sheet(service, spreadsheet_id: str, sheet_name: str) -> list[list[str]]:
    response = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A:ZZ")
        .execute()
    )
    return response.get("values", [])


def _ensure_headers(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    expected_headers: list[str],
    existing_values: list[list[str]],
) -> None:
    if not existing_values:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="RAW",
            body={"values": [expected_headers]},
        ).execute()
        return

    current_headers = [cell.strip() for cell in existing_values[0]]
    if current_headers != expected_headers:
        raise RuntimeError(
            f"Intestazioni incompatibili in {sheet_name}: "
            f"attese {expected_headers}, trovate {current_headers}"
        )


def _missing_rows(
    headers: list[str],
    existing_rows: list[list[str]],
    desired_rows: list[list[str]],
    key_columns: list[str],
) -> list[list[str]]:
    indexes = [headers.index(column) for column in key_columns]
    existing_keys = {_row_key(row, indexes) for row in existing_rows}
    return [row for row in desired_rows if _row_key(row, indexes) not in existing_keys]


def _row_key(row: list[str], indexes: list[int]) -> tuple[str, ...]:
    return tuple((row[index] if index < len(row) else "").strip() for index in indexes)


def _append_rows(service, spreadsheet_id: str, sheet_name: str, rows: list[list[str]]) -> None:
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A:ZZ",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()


def _validate_recipe_units(rows: list[list[str]]) -> list[str]:
    errors: list[str] = []
    by_product: dict[str, dict[str, str]] = {}
    headers = RESOURCE_HEADERS["RICETTE_PRODUZIONE"]
    product_index = headers.index("PRODOTTO")
    article_index = headers.index("ID_ARTICOLO")
    quantity_index = headers.index("QUANTITA_PER_UNITA")

    for row in rows:
        by_product.setdefault(row[product_index], {})[row[article_index]] = row[quantity_index]

    for product, quantities in by_product.items():
        if quantities.get("CON-VAS") != "4":
            errors.append(f"{product}: CON-VAS deve essere 4 per 1 set")
        if quantities.get("SUB-COC") != "4":
            errors.append(f"{product}: SUB-COC deve essere 4 per 1 set")
    return errors


def _validate_inventory_movements(plan: ResourcePlan) -> list[str]:
    inventory_ids = {row[0] for row in plan.rows["INVENTARIO"]}
    movement_ids = {row[2] for row in plan.rows["MOVIMENTI_MAGAZZINO"]}
    missing = sorted(inventory_ids - movement_ids)
    if missing:
        return [f"Articoli inventario senza movimento iniziale: {', '.join(missing)}"]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Inizializza il Resource Engine TPO.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--config", default="config/settings.yaml")
    args = parser.parse_args()

    try:
        if args.dry_run:
            print(summarize_plan(build_resource_plan()))
        else:
            print(apply_plan(args.config))
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
