class AgronomicCommissioningError(Exception):
    pass


class InvalidAgronomicCommissioningCommandError(AgronomicCommissioningError, ValueError):
    pass


class AgronomicCommissioningConflictError(AgronomicCommissioningError):
    pass


class AgronomicCommissioningPersistenceError(AgronomicCommissioningError):
    pass


class AgronomicCommissioningOutcomeUncertain(AgronomicCommissioningError):
    pass
