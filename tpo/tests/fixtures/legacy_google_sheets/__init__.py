"""Resolver della fixture fisica Google Sheets usata soltanto dai test legacy."""

from pathlib import Path


def legacy_schema_path() -> Path:
    """Restituisce il path stabile della baseline non autorevole."""

    return Path(__file__).with_name("legacy_sheets_schema.md")
