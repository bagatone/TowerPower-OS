from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.seed_lot_commissioning.models import (
    FACT_FIELDS, CommissionSeedLot, CommissionSeedLotResult,
    SeedLotCommissioningAuthority, SeedLotFactSource,
)
from src.tpo_core.application.seed_lot_commissioning.service import SeedLotCommissioningService
from src.tpo_core.domain.identifiers import ActorId, LottoSemeId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure


def command(**changes):
    values = dict(
        seed_supplier="Supplier", seed_commercial_reference="REF-1",
        manufacturer_lot_number="LOT-1", received_date=date(2026, 8, 24),
        expiry_date=None, initial_quantity=Quantity(Decimal("10.120000"), UnitOfMeasure.GRAM),
        anomaly=None,
        provenance=tuple((f, SeedLotFactSource.UNKNOWN if f in {"expiry_date", "anomaly"}
                          else SeedLotFactSource.OWNER_AUTHORIZED) for f in FACT_FIELDS),
        authority=SeedLotCommissioningAuthority(ActorId("owner"), "commission", "corr-1", "key-1"),
    )
    values.update(changes)
    return CommissionSeedLot(**values)


class Writer:
    def __init__(self): self.commands = []
    def commission(self, item):
        self.commands.append(item)
        return CommissionSeedLotResult(
            LottoSemeId("LSE-000001"), "INSERTED", item.seed_supplier,
            item.seed_commercial_reference, item.manufacturer_lot_number,
            item.initial_quantity, item.initial_quantity, item.received_date,
            item.expiry_date, datetime.now(timezone.utc),
        )


def test_service_delegates_typed_command_and_hash_is_stable():
    item = command(); writer = Writer()
    assert SeedLotCommissioningService(writer).commission(item).seed_lot_id.value == "LSE-000001"
    assert writer.commands == [item]
    assert item.canonical_payload_hash == command().canonical_payload_hash
    assert len(item.canonical_payload_hash) == 64
    assert "10.12" in item.canonical_payload


def test_payload_excludes_runtime_authority_but_includes_provenance():
    first = command()
    second = command(authority=SeedLotCommissioningAuthority(ActorId("other"), "other", "corr-2", "key-2"))
    assert first.canonical_payload_hash == second.canonical_payload_hash
    changed = list(first.provenance)
    index = next(i for i, entry in enumerate(changed) if entry[0] == "seed_supplier")
    changed[index] = (changed[index][0], SeedLotFactSource.LABEL_OR_PACKAGE)
    assert first.canonical_payload_hash != command(provenance=tuple(changed)).canonical_payload_hash


@pytest.mark.parametrize("quantity,uom", [("0", UnitOfMeasure.GRAM), ("1", UnitOfMeasure.SET)])
def test_command_rejects_invalid_quantity(quantity, uom):
    with pytest.raises(ValueError):
        command(initial_quantity=Quantity(Decimal(quantity), uom))


def test_command_requires_exact_complete_provenance_and_reception_date():
    with pytest.raises(ValueError):
        command(provenance=())
    with pytest.raises(ValueError):
        command(received_date=None)
