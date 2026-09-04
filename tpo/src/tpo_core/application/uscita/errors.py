class UscitaError(Exception):
    code = "USCITA_FAILED"


class InvalidUscitaCommandError(UscitaError): code = "USCITA_INPUT_INVALID"
class InvalidUscitaAmountError(InvalidUscitaCommandError): code = "USCITA_AMOUNT_INVALID"
class InvalidUscitaEffectiveAtError(InvalidUscitaCommandError): code = "USCITA_EFFECTIVE_AT_INVALID"
class UscitaIdempotencyConflictError(UscitaError): code = "USCITA_IDEMPOTENCY_CONFLICT"
class UscitaIdentityUnavailableError(UscitaError): code = "USCITA_IDENTITY_UNAVAILABLE"
class UscitaPersistenceInvariantError(UscitaError): code = "USCITA_PERSISTENCE_INVARIANT"
class UscitaReconciliationRequiredError(UscitaError): code = "USCITA_RECONCILIATION_REQUIRED"
class UscitaCommitRolledBackError(UscitaError): code = "USCITA_COMMIT_ROLLED_BACK"
class UscitaCommitOutcomeUncertainError(UscitaReconciliationRequiredError): code = "USCITA_COMMIT_OUTCOME_UNCERTAIN"

# Uscita Correzione — errori tipizzati dedicati (FINANZE_AZIENDALI_AUTHORITY_FREEZE.md §6).
class UscitaOriginalNotFoundError(UscitaError): code = "USCITA_ORIGINAL_NOT_FOUND"
class UscitaOriginalIsCorrectionError(UscitaError): code = "USCITA_ORIGINAL_IS_CORRECTION"
