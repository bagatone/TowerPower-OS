"""Errori provider-neutral del boundary ASSEGNAZIONE_FISICA V1."""


class AssegnazioneFisicaError(Exception):
    code = "ASSEGNAZIONE_FISICA_FAILED"


class InvalidAssegnazioneFisicaCommandError(AssegnazioneFisicaError):
    code = "ASSEGNAZIONE_FISICA_INPUT_INVALID"


class AssegnazioneFisicaRaccoltaNotFoundError(AssegnazioneFisicaError):
    code = "ASSEGNAZIONE_FISICA_RACCOLTA_NOT_FOUND"


class AssegnazioneFisicaRigaOrdineNotFoundError(AssegnazioneFisicaError):
    code = "ASSEGNAZIONE_FISICA_RIGA_ORDINE_NOT_FOUND"


class AssegnazioneFisicaConsegnaNotFoundError(AssegnazioneFisicaError):
    code = "ASSEGNAZIONE_FISICA_CONSEGNA_NOT_FOUND"


class AssegnazioneFisicaConsegnaRigaOrdineMismatchError(AssegnazioneFisicaError):
    code = "ASSEGNAZIONE_FISICA_CONSEGNA_RIGA_ORDINE_MISMATCH"


class AssegnazioneFisicaIdempotencyConflictError(AssegnazioneFisicaError):
    code = "ASSEGNAZIONE_FISICA_IDEMPOTENCY_CONFLICT"


class AssegnazioneFisicaIdentityUnavailableError(AssegnazioneFisicaError):
    code = "ASSEGNAZIONE_FISICA_IDENTITY_UNAVAILABLE"


class AssegnazioneFisicaPersistenceInvariantError(AssegnazioneFisicaError):
    code = "ASSEGNAZIONE_FISICA_PERSISTENCE_INVARIANT"


class AssegnazioneFisicaReconciliationRequiredError(AssegnazioneFisicaError):
    code = "ASSEGNAZIONE_FISICA_RECONCILIATION_REQUIRED"


class AssegnazioneFisicaCommitRolledBackError(AssegnazioneFisicaError):
    code = "ASSEGNAZIONE_FISICA_COMMIT_ROLLED_BACK"


class AssegnazioneFisicaCommitOutcomeUncertainError(AssegnazioneFisicaReconciliationRequiredError):
    code = "ASSEGNAZIONE_FISICA_COMMIT_OUTCOME_UNCERTAIN"
