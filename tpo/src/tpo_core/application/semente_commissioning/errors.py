class SementeCommissioningError(RuntimeError):
    code = "SEMENTE_COMMISSIONING_FAILED"


class InvalidSementeCommandError(ValueError, SementeCommissioningError):
    code = "SEMENTE_INPUT_INVALID"


class SementeDuplicateError(SementeCommissioningError):
    code = "SEMENTE_DUPLICATE"


class SementeIdempotencyConflictError(SementeCommissioningError):
    code = "SEMENTE_IDEMPOTENCY_CONFLICT"


class SementeConcurrencyConflictError(SementeCommissioningError):
    code = "SEMENTE_CONCURRENCY_CONFLICT"


class SementeCommitRolledBackError(SementeCommissioningError):
    code = "SEMENTE_COMMIT_ROLLED_BACK"


class SementeReconciliationRequiredError(SementeCommissioningError):
    code = "SEMENTE_RECONCILIATION_REQUIRED"
