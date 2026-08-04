"""Composizione esplicita delle dipendenze applicative."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..application.scheduling.engine import SchedulingEngine
from ..application.scheduling.use_case import RunScheduling
from ..domain.identifiers import IdGenerator
from ..infrastructure.google_sheets.google_api_gateway import GoogleApiSheetsGateway
from ..infrastructure.google_sheets.ordini_repository import GoogleSheetsOrdineRepository
from ..infrastructure.google_sheets.programmi_repository import (
    GoogleSheetsProgrammaFornituraRepository,
)
from ..infrastructure.postgresql.connection import PostgreSQLConnectionFactory
from ..infrastructure.postgresql.health import PostgreSQLHealthCheck
from ..infrastructure.postgresql.settings import PostgreSQLSettings
from .settings import ApplicationSettings


@dataclass(frozen=True)
class ApplicationContainer:
    """Grafo completo e immutabile delle dipendenze runtime."""

    settings: ApplicationSettings
    google_gateway: GoogleApiSheetsGateway
    programmi_repository: GoogleSheetsProgrammaFornituraRepository
    ordini_repository: GoogleSheetsOrdineRepository
    scheduling_engine: SchedulingEngine
    run_scheduling: RunScheduling
    postgresql_settings: PostgreSQLSettings | None = None
    postgresql_connection_factory: PostgreSQLConnectionFactory | None = None
    postgresql_health_check: PostgreSQLHealthCheck | None = None


def _build_container(
    *,
    settings: ApplicationSettings,
    google_service: Any,
    id_generator: IdGenerator,
    postgresql_settings: PostgreSQLSettings | None = None,
) -> ApplicationContainer:
    google_gateway = GoogleApiSheetsGateway(google_service)
    programmi_repository = GoogleSheetsProgrammaFornituraRepository(
        settings.spreadsheet_id,
        google_gateway,
        settings.programmi_fornitura_sheet,
    )
    ordini_repository = GoogleSheetsOrdineRepository(
        settings.spreadsheet_id,
        google_gateway,
        settings.ordini_sheet,
    )
    scheduling_engine = SchedulingEngine()
    run_scheduling = RunScheduling(
        programmi_repository,
        ordini_repository,
        id_generator,
        scheduling_engine,
    )
    postgresql_connection_factory = (
        PostgreSQLConnectionFactory(postgresql_settings)
        if postgresql_settings is not None
        else None
    )
    postgresql_health_check = (
        PostgreSQLHealthCheck(postgresql_connection_factory)
        if postgresql_connection_factory is not None
        else None
    )
    return ApplicationContainer(
        settings=settings,
        google_gateway=google_gateway,
        programmi_repository=programmi_repository,
        ordini_repository=ordini_repository,
        scheduling_engine=scheduling_engine,
        run_scheduling=run_scheduling,
        postgresql_settings=postgresql_settings,
        postgresql_connection_factory=postgresql_connection_factory,
        postgresql_health_check=postgresql_health_check,
    )
