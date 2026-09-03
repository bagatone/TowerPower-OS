class SementeImpiegoCommissioningError(RuntimeError):
    code = "SEMENTE_IMPIEGO_COMMISSIONING_FAILED"


class InvalidSementeImpiegoCommandError(ValueError, SementeImpiegoCommissioningError):
    code = "SEMENTE_IMPIEGO_INPUT_INVALID"


class SementeAuthorityNotFoundError(SementeImpiegoCommissioningError):
    code = "SEMENTE_AUTHORITY_NOT_FOUND"


class SementeAuthorityInactiveError(SementeImpiegoCommissioningError):
    code = "SEMENTE_AUTHORITY_INACTIVE"


class SementeAuthorityAmbiguousError(SementeImpiegoCommissioningError):
    code = "SEMENTE_AUTHORITY_AMBIGUOUS"


class ProtocolContextUnavailableError(SementeImpiegoCommissioningError):
    code = "PROTOCOL_CONTEXT_UNAVAILABLE"


class SementeImpiegoDuplicateError(SementeImpiegoCommissioningError):
    code = "SEMENTE_IMPIEGO_DUPLICATE"


class SementeImpiegoIdempotencyConflictError(SementeImpiegoCommissioningError):
    code = "SEMENTE_IMPIEGO_IDEMPOTENCY_CONFLICT"


class SementeImpiegoConcurrencyConflictError(SementeImpiegoCommissioningError):
    code = "SEMENTE_IMPIEGO_CONCURRENCY_CONFLICT"


class SementeImpiegoCommitRolledBackError(SementeImpiegoCommissioningError):
    code = "SEMENTE_IMPIEGO_COMMIT_ROLLED_BACK"


class SementeImpiegoReconciliationRequiredError(SementeImpiegoCommissioningError):
    code = "SEMENTE_IMPIEGO_RECONCILIATION_REQUIRED"
