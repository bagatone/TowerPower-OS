"""Errori applicativi del protocollo di preparazione del commit."""


class CommitError(RuntimeError):
    """Errore base del protocollo applicativo di commit."""


class InvalidCommitRequestError(CommitError, ValueError):
    """Richiesta o risultato di preparazione non validi."""


class CommitPreparationError(CommitError):
    """Il repository non ha potuto preparare il commit."""


class CommitExecutionError(CommitError):
    """Il repository non ha potuto eseguire il commit richiesto."""


class CommitSchemaChangedError(CommitExecutionError):
    """Lo schema fisico non coincide più con quello validato."""


class CommitExistingKeyError(CommitExecutionError):
    """Una chiave idempotente del piano è già presente nel target."""


class CommitSerializationError(CommitExecutionError):
    """Il piano non può essere serializzato nel target fisico."""


class CommitReceiptMismatchError(CommitError):
    """La ricevuta del repository non coincide con la richiesta."""
