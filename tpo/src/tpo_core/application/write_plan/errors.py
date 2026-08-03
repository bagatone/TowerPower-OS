"""Errori applicativi del Write Plan."""


class WritePlanError(ValueError):
    """Errore base della costruzione o validazione del Write Plan."""


class InvalidWritePlanError(WritePlanError):
    """Write Plan privo degli invarianti applicativi richiesti."""


class DuplicateIdempotencyKeyError(WritePlanError):
    """Il piano contiene chiavi idempotenti duplicate."""


class WritePlanRunMismatchError(WritePlanError):
    """Risultato Scheduling e RUN conclusa non appartengono alla stessa RUN."""


class WritePlanConsistencyError(WritePlanError):
    """RUN conclusa e risultato Scheduling non sono coerenti."""
