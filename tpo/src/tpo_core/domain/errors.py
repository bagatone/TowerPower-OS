"""Errori condivisi del Domain Layer."""


class DomainError(Exception):
    """Errore base del dominio Tower Power Operations."""


class InvalidIdentifierError(DomainError):
    """Identificativo permanente non valido."""


class InvalidQuantityError(DomainError):
    """Quantità non valida."""


class InvalidUnitOfMeasureError(DomainError):
    """Unità di misura non valida."""


class InvalidTimeReferenceError(DomainError):
    """Riferimento temporale ufficiale non valido."""


class InvalidTraceabilityCodeError(DomainError):
    """Codice autorevole di tracciabilita non valido."""


class InvalidStateTransitionError(DomainError):
    """Transizione di stato non consentita."""


class InvariantViolationError(DomainError):
    """Violazione di un invariante del dominio."""
