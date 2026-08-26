from datetime import date, datetime, time, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.onboarding import (
    CommissionCustomer, CommissionSupplyProgram, CommissionVariety,
    OnboardingAuthority, OnboardingResult, OperationalDataOnboardingService,
)
from src.tpo_core.application.onboarding.errors import InvalidOnboardingCommandError
from src.tpo_core.domain.entities.programma_fornitura import (
    ConfigurazioneTemporale, ProgrammaFornitura, RigaProgrammaFornitura, TipoRicorrenza,
)
from src.tpo_core.domain.entities.varieta import Varieta
from src.tpo_core.domain.identifiers import ActorId, ClienteId, ProgrammaFornituraId, VarietaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import ProgrammaFornituraState, VarietaState
import inspect


AUTHORITY = OnboardingAuthority(ActorId("owner"), "Real onboarding", "onboard:1")


class Writer:
    def __init__(self): self.commands = []
    def commission_customer(self, command): self.commands.append(command); return OnboardingResult("CLIENTE", command.customer_id.value, True)
    def commission_variety(self, command): self.commands.append(command); return OnboardingResult("VARIETA", command.variety.id.value, True)
    def commission_supply_program(self, command): self.commands.append(command); return OnboardingResult("PROGRAMMA_FORNITURA", command.program.id.value, True)


def test_provider_neutral_service_delegates_explicit_customer_and_variety():
    writer = Writer(); service = OperationalDataOnboardingService(writer)
    customer = CommissionCustomer(ClienteId("CLI-000001"), "Real Customer", AUTHORITY)
    variety = CommissionVariety(Varieta(VarietaId("VAR-000001"), "Cilantro", VarietaState.ATTIVA), AUTHORITY)
    assert service.commission_customer(customer).public_id == "CLI-000001"
    assert service.commission_variety(variety).public_id == "VAR-000001"
    assert writer.commands == [customer, variety]


@pytest.mark.parametrize(("inserted", "updated", "outcome"), [
    (True, False, "INSERTED"),
    (False, True, "UPDATED"),
    (False, False, "COMPATIBLE_REPLAY"),
])
def test_onboarding_result_distinguishes_material_outcomes(inserted, updated, outcome):
    result = OnboardingResult("VARIETA", "VAR-000001", inserted, updated)
    assert result.outcome == outcome


def test_onboarding_result_rejects_two_material_outcomes():
    with pytest.raises(InvalidOnboardingCommandError):
        OnboardingResult("VARIETA", "VAR-000001", True, True)


def test_supply_program_validates_positive_quantity_uom_and_recurrence():
    line = RigaProgrammaFornitura(
        VarietaId("VAR-000001"), Quantity(Decimal("1.5"), UnitOfMeasure.SET),
        ConfigurazioneTemporale(TipoRicorrenza.GIORNI_SETTIMANA, giorni_settimana=(1, 4)),
    )
    program = ProgrammaFornitura(
        ProgrammaFornituraId("PF-000001"), ClienteId("CLI-000001"), (line,),
        date(2026, 8, 24), ProgrammaFornituraState.ATTIVO, 14, None, time(5, 0),
    )
    command = CommissionSupplyProgram(program, 1, datetime(2026, 8, 23, tzinfo=timezone.utc), AUTHORITY)
    writer = Writer()
    assert OperationalDataOnboardingService(writer).commission_supply_program(command).public_id == "PF-000001"


@pytest.mark.parametrize("value", ["", " spaced "])
def test_authority_rejects_missing_or_non_normalized_provenance(value):
    with pytest.raises(ValueError):
        OnboardingAuthority(ActorId("owner"), value, "correlation")


def test_onboarding_boundary_has_no_google_or_order_writer_dependency():
    import src.tpo_core.application.onboarding.service as service
    source = inspect.getsource(service).lower()
    assert "google" not in source
    assert "ordine" not in source


def test_identity_authority_reuses_incremental_commissioning_types():
    from src.tpo_core.application.identity.onboarding import ONBOARDING_SEQUENCE_TYPES
    assert tuple(ONBOARDING_SEQUENCE_TYPES) == (
        "CLIENTE_ID", "VARIETA_ID", "PROGRAMMA_FORNITURA_ID",
    )
