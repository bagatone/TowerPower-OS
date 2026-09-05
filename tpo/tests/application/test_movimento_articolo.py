from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.movimento_articolo.errors import (
    InvalidMovimentoArticoloCommandError,
)
from src.tpo_core.application.movimento_articolo.models import (
    MovimentoArticoloAuthority, RegistraMovimentoArticolo,
)
from src.tpo_core.application.movimento_articolo.service import MovimentoArticoloService
from src.tpo_core.domain.identifiers import ActorId, ArticoloId
from src.tpo_core.domain.states import MovimentoDirection, MovimentoType


AUTH = MovimentoArticoloAuthority(ActorId("magazziniere"), "rifornimento", "corr", "idem")


def command(**changes):
    values = dict(
        articolo_id=ArticoloId("ART-000001"),
        tipo=MovimentoType.CARICO,
        quantita=Decimal("25.5"),
        unita_misura="GRAM",
        effective_at=datetime(2026, 9, 5, 8, tzinfo=timezone.utc),
        motivo="rifornimento substrato",
        authority=AUTH,
    )
    values.update(changes)
    return RegistraMovimentoArticolo(**values)


def test_canonical_payload_is_deterministic_and_64_hex():
    value = command()
    assert len(value.canonical_payload_hash) == 64
    assert value.canonical_payload_hash == command().canonical_payload_hash
    assert value.effective_at.tzinfo is timezone.utc


def test_carico_direzione_is_implicit_positivo():
    assert command().direzione == MovimentoDirection.POSITIVO


def test_scarico_direzione_is_implicit_negativo():
    assert command(tipo=MovimentoType.SCARICO).direzione == MovimentoDirection.NEGATIVO


def test_carico_rejects_explicit_direzione():
    with pytest.raises(InvalidMovimentoArticoloCommandError):
        command(direzione=MovimentoDirection.POSITIVO)


def test_rettifica_requires_explicit_direzione():
    with pytest.raises(InvalidMovimentoArticoloCommandError):
        command(tipo=MovimentoType.RETTIFICA)


def test_rettifica_accepts_explicit_direzione():
    value = command(tipo=MovimentoType.RETTIFICA, direzione=MovimentoDirection.NEGATIVO)
    assert value.direzione == MovimentoDirection.NEGATIVO


def test_canonical_payload_is_sensitive_to_quantity_and_articolo():
    base = command()
    different_quantity = command(quantita=Decimal("25.6"))
    different_articolo = command(articolo_id=ArticoloId("ART-000002"))
    assert base.canonical_payload_hash != different_quantity.canonical_payload_hash
    assert base.canonical_payload_hash != different_articolo.canonical_payload_hash


@pytest.mark.parametrize("value", ["0", "-1", "1.0000001"])
def test_nonpositive_or_overprecision_quantity_is_rejected(value):
    with pytest.raises(InvalidMovimentoArticoloCommandError):
        command(quantita=Decimal(value))


def test_naive_effective_at_is_rejected():
    with pytest.raises(InvalidMovimentoArticoloCommandError):
        command(effective_at=datetime(2026, 9, 5, 8))


def test_blank_motivo_is_rejected():
    with pytest.raises(InvalidMovimentoArticoloCommandError):
        command(motivo="   ")


def test_invalid_unita_misura_is_rejected():
    with pytest.raises(InvalidMovimentoArticoloCommandError):
        command(unita_misura="KILOGRAM")


def test_wrong_articolo_id_type_is_rejected():
    with pytest.raises(InvalidMovimentoArticoloCommandError):
        command(articolo_id="ART-000001")


def test_service_is_thin_and_typed():
    class Writer:
        def registra(self, value):
            assert value == command()
            return "ok"

    service = MovimentoArticoloService(Writer())
    assert service.registra(command()) == "ok"
    with pytest.raises(InvalidMovimentoArticoloCommandError):
        service.registra(object())
