"""Configurazione PostgreSQL validata senza caricamento di file dotenv."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

from .errors import InvalidPostgreSQLSettingsError

_ENV_KEYS = {
    "host": "TPO_DATABASE_HOST",
    "port": "TPO_DATABASE_PORT",
    "database": "TPO_DATABASE_NAME",
    "user": "TPO_DATABASE_USER",
    "password": "TPO_DATABASE_PASSWORD",
    "sslmode": "TPO_DATABASE_SSLMODE",
    "connect_timeout_seconds": "TPO_DATABASE_CONNECT_TIMEOUT",
}
_SSL_MODES = frozenset({"require", "verify-ca", "verify-full"})


@dataclass(frozen=True)
class PostgreSQLSettings:
    """Parametri immutabili; la password è esclusa dalla rappresentazione."""

    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)
    sslmode: str
    connect_timeout_seconds: int

    def __post_init__(self) -> None:
        for name in ("host", "database", "user", "password", "sslmode"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidPostgreSQLSettingsError(
                    f"Il parametro PostgreSQL '{name}' è obbligatorio."
                )
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise InvalidPostgreSQLSettingsError("La porta PostgreSQL deve essere tra 1 e 65535.")
        if (
            isinstance(self.connect_timeout_seconds, bool)
            or not isinstance(self.connect_timeout_seconds, int)
            or self.connect_timeout_seconds <= 0
        ):
            raise InvalidPostgreSQLSettingsError("Il timeout PostgreSQL deve essere positivo.")
        if self.sslmode not in _SSL_MODES:
            raise InvalidPostgreSQLSettingsError("La modalità SSL PostgreSQL non è valida.")

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> PostgreSQLSettings:
        """Costruisce impostazioni da una mappa esplicita."""

        try:
            port = _integer(values.get("port"), "port")
            timeout = _integer(values.get("connect_timeout_seconds"), "connect_timeout_seconds")
            return cls(
                host=values.get("host"),  # type: ignore[arg-type]
                port=port,
                database=values.get("database"),  # type: ignore[arg-type]
                user=values.get("user"),  # type: ignore[arg-type]
                password=values.get("password"),  # type: ignore[arg-type]
                sslmode=values.get("sslmode"),  # type: ignore[arg-type]
                connect_timeout_seconds=timeout,
            )
        except InvalidPostgreSQLSettingsError:
            raise
        except (TypeError, ValueError) as exc:
            raise InvalidPostgreSQLSettingsError("Configurazione PostgreSQL non valida.") from exc

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> PostgreSQLSettings:
        """Legge solo le variabili note dall'ambiente fornito (o dal processo)."""

        source = os.environ if environment is None else environment
        return cls.from_mapping({name: source.get(key) for name, key in _ENV_KEYS.items()})

    def connection_parameters(self) -> dict[str, object]:
        """Restituisce i parametri esclusivamente per il driver, senza URI."""

        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.database,
            "user": self.user,
            "password": self.password,
            "sslmode": self.sslmode,
            "connect_timeout": self.connect_timeout_seconds,
        }


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise InvalidPostgreSQLSettingsError(f"Il parametro PostgreSQL '{name}' non è valido.")
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise InvalidPostgreSQLSettingsError(
            f"Il parametro PostgreSQL '{name}' non è valido."
        ) from exc
