"""Errori tipizzati per la governance di LISTINO_VARIETA."""


class ListinoVarietaConfigurationError(RuntimeError):
    """Errore base della Configuration governata LISTINO_VARIETA."""


class InvalidListinoVarietaCommandError(ValueError, ListinoVarietaConfigurationError):
    """Comando ImpostaPrezzoListinoVarieta non valido."""


class ListinoVarietaVarietaNotFoundError(ListinoVarietaConfigurationError):
    """La VARIETA pubblica indicata non esiste."""


class ListinoVarietaPersistenceError(ListinoVarietaConfigurationError):
    """Scrittura LISTINO_VARIETA PostgreSQL fallita."""
