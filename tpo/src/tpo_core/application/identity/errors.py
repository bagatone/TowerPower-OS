"""Errori applicativi dell'allocazione persistente degli identificativi."""


class IdentityAllocationError(RuntimeError):
    """Errore base della policy applicativa di allocazione."""


class IdentifierSequenceNotFoundError(IdentityAllocationError):
    """Sequenza persistente non disponibile per il tipo richiesto."""


class IdentifierSequenceConflictError(IdentityAllocationError):
    """La sequenza è stata modificata da un'altra allocazione."""


class InvalidIdentifierSequenceError(IdentityAllocationError, ValueError):
    """Sequenza persistente incoerente o non valida."""


class IdentityCommissioningError(RuntimeError):
    """Errore provider-neutral del commissioning Identity esplicito."""


class InvalidIdentityCommissioningCommandError(
    IdentityCommissioningError, ValueError,
):
    """Il comando di commissioning non rappresenta un'identità congelata."""


class IdentityCommissioningConflictError(IdentityCommissioningError):
    """La registrazione richiesta confligge con l'autorità persistita."""


class IdentityCommissioningPersistenceError(IdentityCommissioningError):
    """Il commissioning non è stato persistito e il rollback è certo."""


class IdentityCommissioningOutcomeUncertain(IdentityCommissioningError):
    """L'esito del commit di commissioning richiede riconciliazione."""
