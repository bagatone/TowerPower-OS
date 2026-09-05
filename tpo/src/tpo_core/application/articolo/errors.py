"""Errori provider-neutral del boundary ARTICOLO_COMMISSIONING V1."""


class ArticoloError(Exception):
    code = "ARTICOLO_FAILED"


class InvalidArticoloCommandError(ArticoloError):
    code = "ARTICOLO_INPUT_INVALID"


class ArticoloIdempotencyConflictError(ArticoloError):
    code = "ARTICOLO_IDEMPOTENCY_CONFLICT"


class ArticoloIdentityUnavailableError(ArticoloError):
    code = "ARTICOLO_IDENTITY_UNAVAILABLE"


class ArticoloConcurrencyError(ArticoloError):
    code = "ARTICOLO_CONCURRENCY_CONFLICT"


class ArticoloPersistenceInvariantError(ArticoloError):
    code = "ARTICOLO_PERSISTENCE_INVARIANT"


class ArticoloReconciliationRequiredError(ArticoloError):
    code = "ARTICOLO_RECONCILIATION_REQUIRED"


class ArticoloCommitRolledBackError(ArticoloError):
    code = "ARTICOLO_COMMIT_ROLLED_BACK"


class ArticoloCommitOutcomeUncertainError(ArticoloReconciliationRequiredError):
    code = "ARTICOLO_COMMIT_OUTCOME_UNCERTAIN"
