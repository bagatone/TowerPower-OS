"""Factory pubblica del bootstrap applicativo."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..domain.identifiers import IdGenerator
from .container import ApplicationContainer, _build_container
from .settings import load_settings
from ..infrastructure.postgresql.settings import PostgreSQLSettings


def build_application(
    settings_path: str | Path,
    *,
    google_service: Any,
    id_generator: IdGenerator,
    postgresql_environment: Mapping[str, str] | None = None,
) -> ApplicationContainer:
    """Carica la configurazione e compone una nuova applicazione completa."""

    settings = load_settings(settings_path)
    postgresql_settings = (
        PostgreSQLSettings.from_environment(postgresql_environment)
        if postgresql_environment is not None
        else None
    )
    return _build_container(
        settings=settings,
        google_service=google_service,
        id_generator=id_generator,
        postgresql_settings=postgresql_settings,
    )
