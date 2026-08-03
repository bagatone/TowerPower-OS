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


class WritePlanValidationError(WritePlanError):
    """Errore base della validazione pre-commit del Write Plan."""


class WriteTargetMismatchError(WritePlanValidationError):
    """Il target disponibile non coincide con quello atteso."""


class WriteSchemaMismatchError(WritePlanValidationError):
    """Nome o versione dello schema non coincidono con quelli attesi."""


class DuplicateWritePlanKeyError(WritePlanValidationError):
    """Il piano contiene chiavi idempotenti duplicate."""


class DuplicateWritePlanRecordError(WritePlanValidationError):
    """Il piano contiene più record per lo stesso ordine logico."""


class ExistingIdempotencyKeyError(WritePlanValidationError):
    """Almeno una chiave del piano è già presente nel target."""


class WritePlanCountMismatchError(WritePlanValidationError):
    """I conteggi dichiarati dal piano non coincidono con il contenuto."""


class InvalidWriteTargetSnapshotError(WritePlanValidationError):
    """Snapshot del target assente, incompleto o incoerente."""
