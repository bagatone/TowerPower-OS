class SeminaLifecycleError(Exception):
    code = "SEMINA_LIFECYCLE_FAILED"


class InvalidSeminaLifecycleCommandError(SeminaLifecycleError): code = "SEMINA_LIFECYCLE_INPUT_INVALID"
class SeminaNotFoundError(SeminaLifecycleError): code = "SEMINA_NOT_FOUND"
class SeminaVersionConflictError(SeminaLifecycleError): code = "SEMINA_VERSION_CONFLICT"
class SeminaTransitionInvalidError(SeminaLifecycleError): code = "SEMINA_TRANSITION_INVALID"
class SeminaAlreadyClosedError(SeminaTransitionInvalidError): code = "SEMINA_ALREADY_CLOSED"
class SeminaLifecycleIdempotencyConflictError(SeminaLifecycleError): code = "SEMINA_LIFECYCLE_IDEMPOTENCY_CONFLICT"
class SeminaLifecycleTimestampInvalidError(InvalidSeminaLifecycleCommandError): code = "SEMINA_LIFECYCLE_TIMESTAMP_INVALID"
class SeminaLifecycleTimestampRegressionError(SeminaLifecycleError): code = "SEMINA_LIFECYCLE_TIMESTAMP_REGRESSION"
class SeminaLifecycleProvenanceInvalidError(InvalidSeminaLifecycleCommandError): code = "SEMINA_LIFECYCLE_PROVENANCE_INVALID"
class SeminaFinalOutcomeRequiredError(InvalidSeminaLifecycleCommandError): code = "SEMINA_FINAL_OUTCOME_REQUIRED"
class SeminaFinalOutcomeForbiddenError(InvalidSeminaLifecycleCommandError): code = "SEMINA_FINAL_OUTCOME_FORBIDDEN"
class SeminaLifecycleCommitRolledBackError(SeminaLifecycleError): code = "SEMINA_LIFECYCLE_COMMIT_ROLLED_BACK"
class SeminaLifecycleReconciliationRequiredError(SeminaLifecycleError): code = "SEMINA_LIFECYCLE_RECONCILIATION_REQUIRED"
class SeminaLifecycleCommitOutcomeUncertainError(SeminaLifecycleReconciliationRequiredError): code = "SEMINA_LIFECYCLE_COMMIT_OUTCOME_UNCERTAIN"
