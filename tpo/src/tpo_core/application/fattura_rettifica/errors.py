"""Errori provider-neutral del boundary FATTURA_RETTIFICA V1."""


class FatturaRettificaError(RuntimeError):
    code = "FATTURA_RETTIFICA_FAILED"


class InvalidRectifyFatturaCommandError(ValueError, FatturaRettificaError):
    code = "FATTURA_RETTIFICA_INPUT_INVALID"


class FatturaRettificaValidationError(FatturaRettificaError):
    code = "FATTURA_RETTIFICA_VALIDATION_FAILED"


class FatturaRettificaConcurrencyError(FatturaRettificaError):
    code = "FATTURA_RETTIFICA_CONCURRENCY_CONFLICT"


class FatturaRettificaIdempotencyConflictError(FatturaRettificaError):
    code = "FATTURA_RETTIFICA_IDEMPOTENCY_CONFLICT"


class FatturaRettificaCommitError(FatturaRettificaError):
    code = "FATTURA_RETTIFICA_COMMIT_ROLLED_BACK"


class FatturaRettificaCommitOutcomeUncertain(FatturaRettificaError):
    code = "FATTURA_RETTIFICA_COMMIT_OUTCOME_UNCERTAIN"


class FatturaRettificaReconciliationRequiredError(FatturaRettificaError):
    code = "FATTURA_RETTIFICA_RECONCILIATION_REQUIRED"
