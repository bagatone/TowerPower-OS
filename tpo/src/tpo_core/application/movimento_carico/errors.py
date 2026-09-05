"""Errori provider-neutral del boundary MOVIMENTO_CARICO_RACCOLTA V1."""


class MovimentoCaricoError(Exception):
    code = "MOVIMENTO_CARICO_FAILED"


class InvalidMovimentoCaricoCommandError(MovimentoCaricoError):
    code = "MOVIMENTO_CARICO_INPUT_INVALID"


class MovimentoCaricoRaccoltaNotFoundError(MovimentoCaricoError):
    code = "MOVIMENTO_CARICO_RACCOLTA_NOT_FOUND"


class MovimentoCaricoStockUnitMismatchError(MovimentoCaricoError):
    code = "MOVIMENTO_CARICO_STOCK_UOM_MISMATCH"


class MovimentoCaricoIdempotencyConflictError(MovimentoCaricoError):
    code = "MOVIMENTO_CARICO_IDEMPOTENCY_CONFLICT"


class MovimentoCaricoIdentityUnavailableError(MovimentoCaricoError):
    code = "MOVIMENTO_CARICO_IDENTITY_UNAVAILABLE"


class MovimentoCaricoConcurrencyError(MovimentoCaricoError):
    code = "MOVIMENTO_CARICO_CONCURRENCY_CONFLICT"


class MovimentoCaricoPersistenceInvariantError(MovimentoCaricoError):
    code = "MOVIMENTO_CARICO_PERSISTENCE_INVARIANT"


class MovimentoCaricoReconciliationRequiredError(MovimentoCaricoError):
    code = "MOVIMENTO_CARICO_RECONCILIATION_REQUIRED"


class MovimentoCaricoCommitRolledBackError(MovimentoCaricoError):
    code = "MOVIMENTO_CARICO_COMMIT_ROLLED_BACK"


class MovimentoCaricoCommitOutcomeUncertainError(MovimentoCaricoReconciliationRequiredError):
    code = "MOVIMENTO_CARICO_COMMIT_OUTCOME_UNCERTAIN"
