class SeedLotCommissioningError(RuntimeError):
    code = "SEED_LOT_COMMISSIONING_FAILED"


class InvalidSeedLotCommandError(ValueError, SeedLotCommissioningError):
    code = "SEED_LOT_INPUT_INVALID"


class SeedAuthorityNotFoundError(SeedLotCommissioningError):
    code = "SEED_AUTHORITY_NOT_FOUND"


class SeedAuthorityInactiveError(SeedLotCommissioningError):
    code = "SEED_AUTHORITY_INACTIVE"


class SeedAuthorityAmbiguousError(SeedLotCommissioningError):
    code = "SEED_AUTHORITY_AMBIGUOUS"


class SeedLotIncompatibleError(SeedLotCommissioningError):
    code = "SEED_LOT_INCOMPATIBLE"


class SeedLotQuantityInvalidError(InvalidSeedLotCommandError):
    code = "SEED_LOT_QUANTITY_INVALID"


class SeedLotDuplicateError(SeedLotCommissioningError):
    code = "SEED_LOT_DUPLICATE"


class SeedLotIdempotencyConflictError(SeedLotCommissioningError):
    code = "SEED_LOT_IDEMPOTENCY_CONFLICT"


class SeedLotConcurrencyConflictError(SeedLotCommissioningError):
    code = "SEED_LOT_CONCURRENCY_CONFLICT"


class SeedLotIdentityUnavailableError(SeedLotCommissioningError):
    code = "SEED_LOT_IDENTITY_UNAVAILABLE"


class SeedLotCommitRolledBackError(SeedLotCommissioningError):
    code = "SEED_LOT_COMMIT_ROLLED_BACK"


class SeedLotReconciliationRequiredError(SeedLotCommissioningError):
    code = "SEED_LOT_RECONCILIATION_REQUIRED"
