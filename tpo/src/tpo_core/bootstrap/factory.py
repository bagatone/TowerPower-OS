"""Factory pubblica del bootstrap applicativo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..domain.identifiers import IdGenerator
from .container import ApplicationContainer, _build_container
from .settings import load_settings


def build_application(
    settings_path: str | Path,
    *,
    google_service: Any,
    id_generator: IdGenerator,
) -> ApplicationContainer:
    """Carica la configurazione e compone una nuova applicazione completa."""

    settings = load_settings(settings_path)
    return _build_container(
        settings=settings,
        google_service=google_service,
        id_generator=id_generator,
    )
