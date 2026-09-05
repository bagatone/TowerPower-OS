"""Errori provider-neutral del boundary MOVIMENTO_ARTICOLO V1."""


class MovimentoArticoloError(Exception):
    code = "MOVIMENTO_ARTICOLO_FAILED"


class InvalidMovimentoArticoloCommandError(MovimentoArticoloError):
    code = "MOVIMENTO_ARTICOLO_INPUT_INVALID"


class MovimentoArticoloArticoloNotFoundError(MovimentoArticoloError):
    code = "MOVIMENTO_ARTICOLO_ARTICOLO_NOT_FOUND"


class MovimentoArticoloStockUnitMismatchError(MovimentoArticoloError):
    code = "MOVIMENTO_ARTICOLO_STOCK_UOM_MISMATCH"


class MovimentoArticoloIdempotencyConflictError(MovimentoArticoloError):
    code = "MOVIMENTO_ARTICOLO_IDEMPOTENCY_CONFLICT"


class MovimentoArticoloIdentityUnavailableError(MovimentoArticoloError):
    code = "MOVIMENTO_ARTICOLO_IDENTITY_UNAVAILABLE"


class MovimentoArticoloConcurrencyError(MovimentoArticoloError):
    code = "MOVIMENTO_ARTICOLO_CONCURRENCY_CONFLICT"


class MovimentoArticoloPersistenceInvariantError(MovimentoArticoloError):
    code = "MOVIMENTO_ARTICOLO_PERSISTENCE_INVARIANT"


class MovimentoArticoloReconciliationRequiredError(MovimentoArticoloError):
    code = "MOVIMENTO_ARTICOLO_RECONCILIATION_REQUIRED"


class MovimentoArticoloCommitRolledBackError(MovimentoArticoloError):
    code = "MOVIMENTO_ARTICOLO_COMMIT_ROLLED_BACK"


class MovimentoArticoloCommitOutcomeUncertainError(MovimentoArticoloReconciliationRequiredError):
    code = "MOVIMENTO_ARTICOLO_COMMIT_OUTCOME_UNCERTAIN"


class MovimentoArticoloInsufficientStockError(MovimentoArticoloError):
    code = "MOVIMENTO_ARTICOLO_INSUFFICIENT_STOCK"
