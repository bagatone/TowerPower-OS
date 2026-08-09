"""Errori provider-neutral del Bootstrap applicativo."""


class OperationalRuntimeUnavailableError(RuntimeError):
    """Il grafo operativo completo non può essere composto."""
