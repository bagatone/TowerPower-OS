"""Errori provider-neutral del boundary FATTURA_EMISSIONE V1."""


class FatturaEmissioneError(RuntimeError):
    code = "FATTURA_EMISSIONE_FAILED"


class InvalidEmitFatturaCommandError(ValueError, FatturaEmissioneError):
    code = "FATTURA_EMISSIONE_INPUT_INVALID"


class FatturaValidationError(FatturaEmissioneError):
    code = "FATTURA_EMISSIONE_VALIDATION_FAILED"


class FatturaConcurrencyError(FatturaEmissioneError):
    code = "FATTURA_EMISSIONE_CONCURRENCY_CONFLICT"


class FatturaIdempotencyConflictError(FatturaEmissioneError):
    code = "FATTURA_EMISSIONE_IDEMPOTENCY_CONFLICT"


class FatturaCommitError(FatturaEmissioneError):
    code = "FATTURA_EMISSIONE_COMMIT_ROLLED_BACK"


class FatturaCommitOutcomeUncertain(FatturaEmissioneError):
    code = "FATTURA_EMISSIONE_COMMIT_OUTCOME_UNCERTAIN"


class FatturaReconciliationRequiredError(FatturaEmissioneError):
    code = "FATTURA_EMISSIONE_RECONCILIATION_REQUIRED"
