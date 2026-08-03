"""Errori applicativi del protocollo di preparazione del commit."""


class CommitError(RuntimeError):
    """Errore base del protocollo applicativo di commit."""


class InvalidCommitRequestError(CommitError, ValueError):
    """Richiesta o risultato di preparazione non validi."""


class CommitPreparationError(CommitError):
    """Il repository non ha potuto preparare il commit."""
