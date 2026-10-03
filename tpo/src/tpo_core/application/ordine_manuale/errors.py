"""Errori provider-neutral del boundary ORDINE_MANUALE V1."""


class OrdineManualeError(Exception):
    code = "ORDINE_MANUALE_FAILED"


class InvalidOrdineManualeCommandError(OrdineManualeError):
    code = "ORDINE_MANUALE_INPUT_INVALID"


class OrdineManualeClienteNotFoundError(OrdineManualeError):
    code = "ORDINE_MANUALE_CLIENTE_NOT_FOUND"


class OrdineManualeVarietaError(OrdineManualeError):
    code = "ORDINE_MANUALE_VARIETA_NON_VALIDA"


class OrdineManualeIdempotencyConflictError(OrdineManualeError):
    code = "ORDINE_MANUALE_IDEMPOTENCY_CONFLICT"


class OrdineManualeIdentityUnavailableError(OrdineManualeError):
    code = "ORDINE_MANUALE_IDENTITY_UNAVAILABLE"


class OrdineManualePersistenceInvariantError(OrdineManualeError):
    code = "ORDINE_MANUALE_PERSISTENCE_INVARIANT"


class OrdineManualeReconciliationRequiredError(OrdineManualeError):
    code = "ORDINE_MANUALE_RECONCILIATION_REQUIRED"


class OrdineManualeCommitRolledBackError(OrdineManualeError):
    code = "ORDINE_MANUALE_COMMIT_ROLLED_BACK"


class OrdineManualeCommitOutcomeUncertainError(OrdineManualeReconciliationRequiredError):
    code = "ORDINE_MANUALE_COMMIT_OUTCOME_UNCERTAIN"
