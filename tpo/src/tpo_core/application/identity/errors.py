"""Errori applicativi dell'allocazione persistente degli identificativi."""


class IdentityAllocationError(RuntimeError):
    """Errore base della policy applicativa di allocazione."""


class IdentifierSequenceNotFoundError(IdentityAllocationError):
    """Sequenza persistente non disponibile per il tipo richiesto."""


class IdentifierSequenceConflictError(IdentityAllocationError):
    """La sequenza è stata modificata da un'altra allocazione."""


class InvalidIdentifierSequenceError(IdentityAllocationError, ValueError):
    """Sequenza persistente incoerente o non valida."""
