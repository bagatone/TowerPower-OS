"""Health check PostgreSQL strettamente read-only."""

from __future__ import annotations

from dataclasses import dataclass

from .connection import PostgreSQLConnectionFactory
from .errors import PostgreSQLConnectionError, PostgreSQLHealthCheckError


@dataclass(frozen=True)
class PostgreSQLHealthResult:
    ok: bool
    database_name: str | None = None
    server_version: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class PostgreSQLHealthCheck:
    """Esegue soltanto ``SELECT 1`` e rilascia sempre le risorse."""

    def __init__(self, connection_factory: PostgreSQLConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def check(self) -> PostgreSQLHealthResult:
        connection = None
        cursor = None
        try:
            connection = self._connection_factory.connect()
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            if row != (1,):
                raise PostgreSQLHealthCheckError("Risposta health check PostgreSQL non valida.")
            return PostgreSQLHealthResult(
                ok=True,
                database_name=self._connection_factory.database_name,
                server_version=_server_version(connection),
            )
        except PostgreSQLConnectionError:
            return PostgreSQLHealthResult(
                ok=False,
                error_code="connection_error",
                error_message="Connessione PostgreSQL non disponibile.",
            )
        except Exception as exc:
            error = PostgreSQLHealthCheckError("Health check PostgreSQL fallito.")
            error.__cause__ = exc
            return PostgreSQLHealthResult(
                ok=False,
                error_code="health_check_error",
                error_message=str(error),
            )
        finally:
            _cleanup(cursor, connection)


def _server_version(connection: object) -> str | None:
    info = getattr(connection, "info", None)
    value = getattr(info, "server_version", None)
    return None if value is None else str(value)


def _cleanup(cursor: object | None, connection: object | None) -> None:
    if cursor is not None:
        try:
            cursor.close()  # type: ignore[attr-defined]
        except Exception:
            pass

    if connection is not None:
        try:
            connection.rollback()  # type: ignore[attr-defined]
        except Exception:
            pass
        finally:
            try:
                connection.close()  # type: ignore[attr-defined]
            except Exception:
                pass
