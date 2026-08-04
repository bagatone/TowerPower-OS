"""Errori sicuri e classificabili dell'infrastruttura PostgreSQL."""


class PostgreSQLError(RuntimeError):
    """Errore base PostgreSQL."""


class InvalidPostgreSQLSettingsError(PostgreSQLError, ValueError):
    """Configurazione PostgreSQL assente o non valida."""


class PostgreSQLConnectionError(PostgreSQLError):
    """Apertura della connessione PostgreSQL fallita."""


class PostgreSQLHealthCheckError(PostgreSQLError):
    """Health check PostgreSQL fallito."""
