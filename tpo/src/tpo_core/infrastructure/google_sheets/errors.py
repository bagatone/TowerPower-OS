"""Errori specifici degli adapter Google Sheets."""


class GoogleSheetsRepositoryError(RuntimeError):
    """Errore di accesso a un Repository basato su Google Sheets."""


class InvalidSheetSchemaError(GoogleSheetsRepositoryError):
    """Intestazioni fisiche incompatibili con lo schema congelato."""


class InvalidSheetRowError(GoogleSheetsRepositoryError):
    """Valore di una riga fisica non valido o ambiguo."""


class DuplicateScheduledOrderError(GoogleSheetsRepositoryError):
    """Chiave idempotente già presente nel foglio ORDINI."""
