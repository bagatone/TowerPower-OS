class OperationalDataOnboardingError(RuntimeError):
    """Base error for governed operational-data onboarding."""


class InvalidOnboardingCommandError(ValueError, OperationalDataOnboardingError):
    pass


class OnboardingConflictError(OperationalDataOnboardingError):
    pass


class OnboardingPersistenceError(OperationalDataOnboardingError):
    pass


class OnboardingOutcomeUncertain(OperationalDataOnboardingError):
    pass
