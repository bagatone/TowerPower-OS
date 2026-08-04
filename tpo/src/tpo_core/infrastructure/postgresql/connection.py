"""Factory pigra di connessioni PostgreSQL."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import psycopg

from .errors import PostgreSQLConnectionError
from .settings import PostgreSQLSettings


class PostgreSQLConnectionFactory:
    """Apre una nuova connessione solo su richiesta."""

    def __init__(
        self,
        settings: PostgreSQLSettings,
        *,
        connector: Callable[..., Any] = psycopg.connect,
    ) -> None:
        self._settings = settings
        self._connector = connector

    @property
    def database_name(self) -> str:
        return self._settings.database

    def connect(self) -> Any:
        try:
            return self._connector(**self._settings.connection_parameters())
        except psycopg.Error as exc:
            raise PostgreSQLConnectionError(
                "Impossibile aprire la connessione PostgreSQL."
            ) from exc
