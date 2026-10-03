"""Errori provider-neutral del boundary RETTIFICA_GIACENZA V1."""


class RettificaGiacenzaError(Exception):
    code = "RETTIFICA_GIACENZA_FAILED"


class InvalidRettificaGiacenzaCommandError(RettificaGiacenzaError):
    code = "RETTIFICA_GIACENZA_INPUT_INVALID"


class RettificaGiacenzaVarietaNotFoundError(RettificaGiacenzaError):
    code = "RETTIFICA_GIACENZA_VARIETA_NOT_FOUND"


class RettificaGiacenzaStockError(RettificaGiacenzaError):
    code = "RETTIFICA_GIACENZA_STOCK_INSUFFICIENT"


class RettificaGiacenzaOrigineError(RettificaGiacenzaError):
    code = "RETTIFICA_GIACENZA_ORIGINE_NON_ONORABILE"


class RettificaGiacenzaIdempotencyConflictError(RettificaGiacenzaError):
    code = "RETTIFICA_GIACENZA_IDEMPOTENCY_CONFLICT"


class RettificaGiacenzaIdentityUnavailableError(RettificaGiacenzaError):
    code = "RETTIFICA_GIACENZA_IDENTITY_UNAVAILABLE"


class RettificaGiacenzaConcurrencyError(RettificaGiacenzaError):
    code = "RETTIFICA_GIACENZA_CONCURRENCY_CONFLICT"


class RettificaGiacenzaPersistenceInvariantError(RettificaGiacenzaError):
    code = "RETTIFICA_GIACENZA_PERSISTENCE_INVARIANT"


class RettificaGiacenzaReconciliationRequiredError(RettificaGiacenzaError):
    code = "RETTIFICA_GIACENZA_RECONCILIATION_REQUIRED"


class RettificaGiacenzaCommitRolledBackError(RettificaGiacenzaError):
    code = "RETTIFICA_GIACENZA_COMMIT_ROLLED_BACK"


class RettificaGiacenzaCommitOutcomeUncertainError(RettificaGiacenzaReconciliationRequiredError):
    code = "RETTIFICA_GIACENZA_COMMIT_OUTCOME_UNCERTAIN"
