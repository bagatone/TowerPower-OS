from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.semente_impiego_commissioning.models import (
    CommissionSementeImpiego, CommissionSementeImpiegoResult,
    SementeImpiegoCommissioningAuthority,
)
from src.tpo_core.application.semente_impiego_commissioning.service import (
    SementeImpiegoCommissioningService,
)
from src.tpo_core.domain.identifiers import ActorId, ProtocolloVersioneId
from src.tpo_core.domain.states import SementeRaccomandazione


def command(**changes):
    values = dict(
        fornitore="INTERSEMILLAS", referenza_commerciale="VERDE MICROGREENS",
        protocol_version_public_id=ProtocolloVersioneId("PV-000001"),
        raccomandazione=SementeRaccomandazione.RACCOMANDATA,
        rating=Decimal("85"), motivazione="Germinazione uniforme in prova.",
        authority=SementeImpiegoCommissioningAuthority(ActorId("owner"), "commission", "corr-1", "key-1"),
    )
    values.update(changes)
    return CommissionSementeImpiego(**values)


class Writer:
    def __init__(self): self.commands = []
    def commission(self, item):
        self.commands.append(item)
        return CommissionSementeImpiegoResult(
            1, "INSERTED", item.fornitore, item.referenza_commerciale,
            "VAR-000001", "Cilantro", "Microgreens", item.raccomandazione, item.rating,
            item.motivazione, date(2026, 9, 3), datetime.now(timezone.utc),
        )


def test_service_delegates_typed_command_and_hash_is_stable():
    item = command(); writer = Writer()
    assert SementeImpiegoCommissioningService(writer).commission(item).semente_impiego_id == 1
    assert writer.commands == [item]
    assert item.canonical_payload_hash == command().canonical_payload_hash
    assert len(item.canonical_payload_hash) == 64
    assert "PV-000001" in item.canonical_payload


def test_payload_excludes_runtime_authority_but_includes_evaluation_facts():
    first = command()
    second = command(authority=SementeImpiegoCommissioningAuthority(ActorId("other"), "other", "corr-2", "key-2"))
    assert first.canonical_payload_hash == second.canonical_payload_hash
    assert first.canonical_payload_hash != command(rating=Decimal("50")).canonical_payload_hash
    assert first.canonical_payload_hash != command(
        raccomandazione=SementeRaccomandazione.SCONSIGLIATA
    ).canonical_payload_hash
    assert first.canonical_payload_hash != command(
        protocol_version_public_id=ProtocolloVersioneId("PV-000002")
    ).canonical_payload_hash


def test_service_rejects_untyped_command():
    with pytest.raises(ValueError):
        SementeImpiegoCommissioningService(Writer()).commission(object())


@pytest.mark.parametrize("field", ["fornitore", "referenza_commerciale"])
def test_command_requires_normalized_constitutive_fields(field):
    with pytest.raises(ValueError):
        command(**{field: ""})
    with pytest.raises(ValueError):
        command(**{field: "  padded  "})


def test_command_requires_typed_protocol_version_and_raccomandazione():
    with pytest.raises(ValueError):
        command(protocol_version_public_id="PV-000001")
    with pytest.raises(ValueError):
        command(raccomandazione="RACCOMANDATA")


@pytest.mark.parametrize("rating", [Decimal("-1"), Decimal("101"), "85"])
def test_command_rejects_out_of_domain_or_non_decimal_rating(rating):
    with pytest.raises(ValueError):
        command(rating=rating)


def test_command_allows_none_rating_and_motivazione_but_rejects_blank():
    assert command(rating=None, motivazione=None)
    with pytest.raises(ValueError):
        command(motivazione="")


def test_result_rejects_non_positive_internal_identity():
    with pytest.raises(ValueError):
        CommissionSementeImpiegoResult(
            0, "INSERTED", "F", "R", "VAR-000001", "C", "U",
            SementeRaccomandazione.RACCOMANDATA, None, None,
            date(2026, 9, 3), datetime.now(timezone.utc),
        )
