from datetime import datetime, timezone

import pytest

from src.tpo_core.application.semente_commissioning.models import (
    CommissionSemente, CommissionSementeResult, SementeCommissioningAuthority,
)
from src.tpo_core.application.semente_commissioning.service import SementeCommissioningService
from src.tpo_core.domain.identifiers import ActorId


def command(**changes):
    values = dict(
        fornitore="INTERSEMILLAS", referenza_commerciale="VERDE MICROGREENS",
        marca=None, formato=None, trattamento="Sin tratamiento", certificazioni=None,
        authority=SementeCommissioningAuthority(ActorId("owner"), "commission", "corr-1", "key-1"),
    )
    values.update(changes)
    return CommissionSemente(**values)


class Writer:
    def __init__(self): self.commands = []
    def commission(self, item):
        self.commands.append(item)
        return CommissionSementeResult(
            1, "INSERTED", item.fornitore, item.referenza_commerciale,
            item.marca, item.formato, item.trattamento, item.certificazioni,
            True, datetime.now(timezone.utc),
        )


def test_service_delegates_typed_command_and_hash_is_stable():
    item = command(); writer = Writer()
    assert SementeCommissioningService(writer).commission(item).semente_id == 1
    assert writer.commands == [item]
    assert item.canonical_payload_hash == command().canonical_payload_hash
    assert len(item.canonical_payload_hash) == 64
    assert "INTERSEMILLAS" in item.canonical_payload


def test_payload_excludes_runtime_authority_but_includes_constitutive_and_metadata():
    first = command()
    second = command(authority=SementeCommissioningAuthority(ActorId("other"), "other", "corr-2", "key-2"))
    assert first.canonical_payload_hash == second.canonical_payload_hash
    assert first.canonical_payload_hash != command(trattamento="Trattato").canonical_payload_hash
    assert first.canonical_payload_hash != command(referenza_commerciale="ALTRO").canonical_payload_hash


def test_service_rejects_untyped_command():
    with pytest.raises(ValueError):
        SementeCommissioningService(Writer()).commission(object())


@pytest.mark.parametrize("field", ["fornitore", "referenza_commerciale"])
def test_command_requires_normalized_constitutive_fields(field):
    with pytest.raises(ValueError):
        command(**{field: ""})
    with pytest.raises(ValueError):
        command(**{field: "  padded  "})
    with pytest.raises(ValueError):
        command(**{field: None})


@pytest.mark.parametrize("field", ["marca", "formato", "trattamento", "certificazioni"])
def test_command_allows_none_but_rejects_blank_optional_metadata(field):
    assert command(**{field: None})
    with pytest.raises(ValueError):
        command(**{field: ""})
    with pytest.raises(ValueError):
        command(**{field: "  padded  "})


def test_authority_requires_normalized_text_and_typed_actor():
    with pytest.raises(ValueError):
        SementeCommissioningAuthority(ActorId("owner"), "", "corr-1", "key-1")
    with pytest.raises(ValueError):
        SementeCommissioningAuthority("owner", "commission", "corr-1", "key-1")


def test_result_rejects_non_positive_internal_identity():
    with pytest.raises(ValueError):
        CommissionSementeResult(0, "INSERTED", "F", "R", None, None, None, None, True, datetime.now(timezone.utc))
