class IncassoError(Exception):
    code = "INCASSO_FAILED"


class InvalidIncassoCommandError(IncassoError): code = "INCASSO_INPUT_INVALID"
class InvalidIncassoAmountError(InvalidIncassoCommandError): code = "INCASSO_AMOUNT_INVALID"
class InvalidIncassoEffectiveAtError(InvalidIncassoCommandError): code = "INCASSO_EFFECTIVE_AT_INVALID"
class IncassoFatturaNotFoundError(IncassoError): code = "INCASSO_FATTURA_NOT_FOUND"
class IncassoIdempotencyConflictError(IncassoError): code = "INCASSO_IDEMPOTENCY_CONFLICT"
class IncassoIdentityUnavailableError(IncassoError): code = "INCASSO_IDENTITY_UNAVAILABLE"
class IncassoPersistenceInvariantError(IncassoError): code = "INCASSO_PERSISTENCE_INVARIANT"
class IncassoReconciliationRequiredError(IncassoError): code = "INCASSO_RECONCILIATION_REQUIRED"
class IncassoCommitRolledBackError(IncassoError): code = "INCASSO_COMMIT_ROLLED_BACK"
class IncassoCommitOutcomeUncertainError(IncassoReconciliationRequiredError): code = "INCASSO_COMMIT_OUTCOME_UNCERTAIN"

# Incasso Correzione — errori tipizzati dedicati (FINANZE_AZIENDALI_AUTHORITY_FREEZE.md §6).
class IncassoOriginalNotFoundError(IncassoError): code = "INCASSO_ORIGINAL_NOT_FOUND"
class IncassoOriginalIsCorrectionError(IncassoError): code = "INCASSO_ORIGINAL_IS_CORRECTION"
class IncassoCorrectionFatturaMismatchError(IncassoError): code = "INCASSO_CORRECTION_FATTURA_MISMATCH"
