class ProgrammaFornituraSospensioneError(Exception):
    code = "PROGRAMMA_FORNITURA_SOSPENSIONE_FAILED"


class InvalidProgrammaFornituraSospensioneCommandError(ProgrammaFornituraSospensioneError):
    code = "PROGRAMMA_FORNITURA_SOSPENSIONE_INPUT_INVALID"


class ProgrammaFornituraNotFoundError(ProgrammaFornituraSospensioneError):
    code = "PROGRAMMA_FORNITURA_NOT_FOUND"


class ProgrammaFornituraStateIneligibleError(ProgrammaFornituraSospensioneError):
    code = "PROGRAMMA_FORNITURA_STATE_INELIGIBLE"


class ProgrammaFornituraVersionConflictError(ProgrammaFornituraSospensioneError):
    code = "PROGRAMMA_FORNITURA_VERSION_CONFLICT"


class ProgrammaFornituraTimestampRegressionError(ProgrammaFornituraSospensioneError):
    code = "PROGRAMMA_FORNITURA_EFFECTIVE_AT_REGRESSION"


class ProgrammaFornituraClienteGiaAttivoError(ProgrammaFornituraSospensioneError):
    code = "PROGRAMMA_FORNITURA_CLIENTE_GIA_ATTIVO"


class ProgrammaFornituraIdempotencyConflictError(ProgrammaFornituraSospensioneError):
    code = "PROGRAMMA_FORNITURA_IDEMPOTENCY_CONFLICT"


class ProgrammaFornituraReconciliationRequiredError(ProgrammaFornituraSospensioneError):
    code = "PROGRAMMA_FORNITURA_RECONCILIATION_REQUIRED"


class ProgrammaFornituraCommitRolledBackError(ProgrammaFornituraSospensioneError):
    code = "PROGRAMMA_FORNITURA_COMMIT_ROLLED_BACK"


class ProgrammaFornituraCommitOutcomeUncertainError(ProgrammaFornituraReconciliationRequiredError):
    code = "PROGRAMMA_FORNITURA_COMMIT_OUTCOME_UNCERTAIN"


class ProgrammaFornituraIdentityUnavailableError(ProgrammaFornituraSospensioneError):
    code = "PROGRAMMA_FORNITURA_IDENTITY_UNAVAILABLE"


class ProgrammaFornituraPersistenceInvariantError(ProgrammaFornituraSospensioneError):
    code = "PROGRAMMA_FORNITURA_PERSISTENCE_INVARIANT"
