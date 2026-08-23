from .errors import InvalidOnboardingCommandError
from .models import CommissionCustomer, CommissionSupplyProgram, CommissionVariety, OnboardingResult
from .ports import OperationalDataOnboardingWriter


class OperationalDataOnboardingService:
    def __init__(self, writer: OperationalDataOnboardingWriter) -> None:
        self._writer = writer

    def commission_customer(self, command: CommissionCustomer) -> OnboardingResult:
        if not isinstance(command, CommissionCustomer):
            raise InvalidOnboardingCommandError("command customer non valido.")
        return self._writer.commission_customer(command)

    def commission_variety(self, command: CommissionVariety) -> OnboardingResult:
        if not isinstance(command, CommissionVariety):
            raise InvalidOnboardingCommandError("command variety non valido.")
        return self._writer.commission_variety(command)

    def commission_supply_program(self, command: CommissionSupplyProgram) -> OnboardingResult:
        if not isinstance(command, CommissionSupplyProgram):
            raise InvalidOnboardingCommandError("command supply-program non valido.")
        return self._writer.commission_supply_program(command)
