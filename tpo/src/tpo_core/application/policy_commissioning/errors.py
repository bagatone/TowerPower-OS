"""Sanitized errors for Production Planning policy commissioning."""


class PolicyCommissioningError(RuntimeError):
    """Base error for the provider-neutral commissioning boundary."""


class InvalidPolicyCommissioningCommandError(PolicyCommissioningError, ValueError):
    """The explicit commissioning command is invalid."""


class PolicyCommissioningConflictError(PolicyCommissioningError):
    """The requested policy identity already owns a different payload."""


class PolicyCommissioningPersistenceError(PolicyCommissioningError):
    """Commissioning certainly failed and was rolled back."""


class PolicyCommissioningOutcomeUncertain(PolicyCommissioningError):
    """The physical outcome of the commissioning commit is uncertain."""
