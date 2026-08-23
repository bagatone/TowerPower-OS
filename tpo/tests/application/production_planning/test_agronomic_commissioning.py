from dataclasses import replace
from datetime import date, datetime, time, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.agronomic_commissioning.errors import InvalidAgronomicCommissioningCommandError
from src.tpo_core.application.agronomic_commissioning.models import CommissionAgronomicProtocolCommand
from src.tpo_core.application.agronomic_commissioning.service import AgronomicProtocolCommissioningService
from src.tpo_core.domain.identifiers import ActorId, ProtocolloVersioneId, VarietaId
from src.tpo_core.domain.time_reference import CurrentSystemDate


NOW = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)


def command(**changes):
    values = dict(
        variety_id=VarietaId("VAR-000001"), variety_name="Afila", cultivar_name="Afila",
        productive_use_code="MICROGREEN", productive_use_name="Microgreens",
        protocol_name="Tower Power standard Afila", protocol_version_id=ProtocolloVersioneId("PV-000001"),
        version=1, valid_from=date(2026, 8, 1), valid_to=None,
        hydration_hours=Decimal("12"), planned_sowing_time=time(6), target_harvest_time=time(6),
        germination_days=5, light_growth_days=5, seed_grams_per_set=Decimal("32"),
        expected_yield=Decimal("1"), production_granularity=Decimal("0.5"),
        harvest_min_lead_days=1, harvest_max_lead_days=1, temporal_buffer_minutes=0,
        content="Owner-authorized protocol", motivation="Initial commissioning", evidence=None,
        provenance="OWNER_AUTHORIZED_REAL_GROWING_PROTOCOL_2026-08", actor=ActorId("tpo.owner"),
        reason="Initial real agronomic protocol commissioning",
        correlation_id="real-agronomic-protocol-v1:afila",
    )
    values.update(changes)
    return CommissionAgronomicProtocolCommand(**values)


class Clock:
    def now(self): return CurrentSystemDate(NOW)


class Writer:
    def __init__(self): self.values = []
    def commission(self, value): self.values.append(value); return value


def test_service_uses_injected_clock_and_exact_command():
    writer = Writer()
    result = AgronomicProtocolCommissioningService(writer=writer, clock=Clock()).commission(command())
    assert result.approved_at == NOW and writer.values == [result]
    assert result.command.protocol_version_id == ProtocolloVersioneId("PV-000001")


@pytest.mark.parametrize("changes", [
    {"version": 2}, {"harvest_min_lead_days": 0}, {"harvest_max_lead_days": 0},
    {"seed_grams_per_set": Decimal("0")}, {"production_granularity": Decimal("0")},
    {"correlation_id": " correlation"}, {"actor": "tpo.owner"},
])
def test_invalid_authority_fails_closed(changes):
    with pytest.raises(InvalidAgronomicCommissioningCommandError): command(**changes)


def test_command_is_immutable_and_no_latest_selector():
    assert replace(command(), germination_days=6).germination_days == 6
    assert "latest" not in " ".join(CommissionAgronomicProtocolCommand.__dataclass_fields__).lower()
