from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.fattura_emissione.errors import InvalidEmitFatturaCommandError
from src.tpo_core.application.fattura_emissione.models import (
    EmitFattura, EmitFatturaAuthority, EmitFatturaResult,
)
from src.tpo_core.application.fattura_emissione.service import FatturaEmissioneService
from src.tpo_core.domain.identifiers import ActorId, ClienteId, ConsegnaId, NumeroFattura


def authority(**changes):
    values = dict(actor=ActorId("owner"), reason="emissione", correlation_id="corr-1",
                  idempotency_key="key-1")
    values.update(changes)
    return EmitFatturaAuthority(**values)


def command(**changes):
    values = dict(
        cliente_id=ClienteId("CLI-000001"),
        consegna_ids=(ConsegnaId("CON-000001"), ConsegnaId("CON-000002")),
        data_emissione=date(2026, 9, 3),
        authority=authority(),
    )
    values.update(changes)
    return EmitFattura(**values)


def test_canonical_payload_hash_is_stable_and_deterministic():
    first = command()
    assert first.canonical_payload_hash == command().canonical_payload_hash
    assert len(first.canonical_payload_hash) == 64
    assert "CON-000001" in first.canonical_payload
    assert "CON-000002" in first.canonical_payload


def test_payload_excludes_runtime_authority_but_includes_business_facts():
    first = command()
    second = command(authority=authority(actor=ActorId("other"), correlation_id="corr-2",
                                          idempotency_key="key-2"))
    assert first.canonical_payload_hash == second.canonical_payload_hash
    assert first.canonical_payload_hash != command(
        consegna_ids=(ConsegnaId("CON-000001"),)
    ).canonical_payload_hash
    assert first.canonical_payload_hash != command(
        data_emissione=date(2026, 9, 4)
    ).canonical_payload_hash
    assert first.canonical_payload_hash != command(
        cliente_id=ClienteId("CLI-000002")
    ).canonical_payload_hash


def test_rejects_empty_or_duplicate_consegna_ids():
    with pytest.raises(InvalidEmitFatturaCommandError):
        command(consegna_ids=())
    with pytest.raises(InvalidEmitFatturaCommandError):
        command(consegna_ids=(ConsegnaId("CON-000001"), ConsegnaId("CON-000001")))


def test_rejects_invalid_authority_fields():
    with pytest.raises(InvalidEmitFatturaCommandError):
        authority(reason="  ")
    with pytest.raises(InvalidEmitFatturaCommandError):
        authority(idempotency_key="")


class Writer:
    def __init__(self):
        self.commands = []

    def emit(self, item):
        self.commands.append(item)
        return EmitFatturaResult(
            1, "INSERTED", NumeroFattura("2026/0001"), item.cliente_id, item.data_emissione,
            date(2026, 10, 3), Decimal("100.00"), Decimal("7.00"), Decimal("107.00"), 2, 2,
            datetime.now(timezone.utc),
        )


def test_service_delegates_typed_command_only():
    item = command()
    writer = Writer()
    result = FatturaEmissioneService(writer).emit(item)
    assert result.fattura_id == 1
    assert result.numero_fattura == NumeroFattura("2026/0001")
    assert writer.commands == [item]
    with pytest.raises(InvalidEmitFatturaCommandError):
        FatturaEmissioneService(writer).emit(object())
