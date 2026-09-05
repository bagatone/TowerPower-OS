from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.movimento_carico.errors import (
    InvalidMovimentoCaricoCommandError,
)
from src.tpo_core.application.movimento_carico.models import (
    MovimentoCaricoAuthority, RegistraCaricoMagazzino,
)
from src.tpo_core.application.movimento_carico.service import MovimentoCaricoService
from src.tpo_core.domain.identifiers import ActorId, RaccoltaId


AUTH = MovimentoCaricoAuthority(ActorId("magazziniere"), "peso reale", "corr", "idem")


def command(**changes):
    values = dict(
        raccolta_id=RaccoltaId("RAC-000001"),
        quantita_pesata=Decimal("450.5"),
        effective_at=datetime(2026, 9, 5, 8, tzinfo=timezone.utc),
        motivo="pesatura carico magazzino",
        authority=AUTH,
    )
    values.update(changes)
    return RegistraCaricoMagazzino(**values)


def test_canonical_payload_is_deterministic_and_64_hex():
    value = command()
    assert len(value.canonical_payload_hash) == 64
    assert value.canonical_payload_hash == command().canonical_payload_hash
    assert value.effective_at.tzinfo is timezone.utc


def test_canonical_payload_is_sensitive_to_quantity_and_raccolta():
    base = command()
    different_quantity = command(quantita_pesata=Decimal("450.6"))
    different_raccolta = command(raccolta_id=RaccoltaId("RAC-000002"))
    assert base.canonical_payload_hash != different_quantity.canonical_payload_hash
    assert base.canonical_payload_hash != different_raccolta.canonical_payload_hash


@pytest.mark.parametrize("value", ["0", "-1", "1.0000001"])
def test_nonpositive_or_overprecision_quantity_is_rejected(value):
    with pytest.raises(InvalidMovimentoCaricoCommandError):
        command(quantita_pesata=Decimal(value))


def test_naive_effective_at_is_rejected():
    with pytest.raises(InvalidMovimentoCaricoCommandError):
        command(effective_at=datetime(2026, 9, 5, 8))


def test_blank_motivo_is_rejected():
    with pytest.raises(InvalidMovimentoCaricoCommandError):
        command(motivo="   ")


def test_wrong_raccolta_id_type_is_rejected():
    with pytest.raises(InvalidMovimentoCaricoCommandError):
        command(raccolta_id="RAC-000001")


def test_service_is_thin_and_typed():
    class Writer:
        def registra(self, value):
            assert value == command()
            return "ok"

    service = MovimentoCaricoService(Writer())
    assert service.registra(command()) == "ok"
    with pytest.raises(InvalidMovimentoCaricoCommandError):
        service.registra(object())
