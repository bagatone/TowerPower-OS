class RaccoltaError(Exception):
    code = "RACCOLTA_FAILED"


class InvalidRaccoltaCommandError(RaccoltaError): code = "RACCOLTA_INPUT_INVALID"
class InvalidRaccoltaQuantityError(InvalidRaccoltaCommandError): code = "RACCOLTA_QUANTITY_INVALID"
class InvalidRaccoltaEffectiveAtError(InvalidRaccoltaCommandError): code = "RACCOLTA_EFFECTIVE_AT_INVALID"
class RaccoltaSeminaNotFoundError(RaccoltaError): code = "RACCOLTA_SEMINA_NOT_FOUND"
class RaccoltaSeminaStateError(RaccoltaError): code = "RACCOLTA_SEMINA_STATE_INELIGIBLE"
class RaccoltaTraceabilityUnavailableError(RaccoltaError): code = "RACCOLTA_TRACEABILITY_UNAVAILABLE"
class RaccoltaIdempotencyConflictError(RaccoltaError): code = "RACCOLTA_IDEMPOTENCY_CONFLICT"
class RaccoltaIdentityUnavailableError(RaccoltaError): code = "RACCOLTA_IDENTITY_UNAVAILABLE"
class RaccoltaPersistenceInvariantError(RaccoltaError): code = "RACCOLTA_PERSISTENCE_INVARIANT"
class RaccoltaReconciliationRequiredError(RaccoltaError): code = "RACCOLTA_RECONCILIATION_REQUIRED"
class RaccoltaCommitRolledBackError(RaccoltaError): code = "RACCOLTA_COMMIT_ROLLED_BACK"
class RaccoltaCommitOutcomeUncertainError(RaccoltaReconciliationRequiredError): code = "RACCOLTA_COMMIT_OUTCOME_UNCERTAIN"

# Raccolta Correzione (RACCOLTA_CORREZIONE_AUTHORITY_FREEZE.md) — errori tipizzati dedicati.
class RaccoltaOriginalNotFoundError(RaccoltaError): code = "RACCOLTA_ORIGINAL_NOT_FOUND"
class RaccoltaOriginalIsCorrectionError(RaccoltaError): code = "RACCOLTA_ORIGINAL_IS_CORRECTION"
class RaccoltaCorrectionSeminaMismatchError(RaccoltaError): code = "RACCOLTA_CORRECTION_SEMINA_MISMATCH"
class RaccoltaCorrectionUnitMismatchError(RaccoltaError): code = "RACCOLTA_CORRECTION_UOM_MISMATCH"
class RaccoltaCorrectionNetQuantityNegativeError(RaccoltaError): code = "RACCOLTA_CORRECTION_NET_QUANTITY_NEGATIVE"
