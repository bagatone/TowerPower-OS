"""Factory pubblica del bootstrap applicativo."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from ..domain.identifiers import IdGenerator
from ..application.ports.clock import Clock
from .container import (
    ApplicationContainer,
    _build_container,
    _build_operational_container,
)
from .settings import load_settings
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from ..infrastructure.postgresql.errors import InvalidPostgreSQLSettingsError
from .errors import OperationalRuntimeUnavailableError


def build_application(
    settings_path: str | Path,
    *,
    google_service: Any,
    id_generator: IdGenerator,
    postgresql_environment: Mapping[str, str] | None = None,
    clock: Clock | None = None,
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
        clock=clock,
    )


def _build_operational_application(
    settings_path: str | Path,
    *,
    postgresql_environment: Mapping[str, str] | None = None,
    clock: Clock | None = None,
) -> ApplicationContainer:
    """Compone il boundary operativo senza autenticare o usare Google."""

    environment = os.environ if postgresql_environment is None else postgresql_environment
    try:
        settings = load_settings(settings_path)
        postgresql_settings = PostgreSQLSettings.from_environment(environment)
        return _build_operational_container(
            settings=settings,
            postgresql_settings=postgresql_settings,
            clock=clock,
        )
    except InvalidPostgreSQLSettingsError as exc:
        raise OperationalRuntimeUnavailableError(
            "Il runtime PostgreSQL operativo non è disponibile."
        ) from exc
