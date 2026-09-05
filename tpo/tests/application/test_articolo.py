from datetime import datetime, timezone

import pytest

from src.tpo_core.application.articolo.errors import InvalidArticoloCommandError
from src.tpo_core.application.articolo.models import (
    ArticoloCommissioningAuthority, CommissionArticolo,
)
from src.tpo_core.application.articolo.service import ArticoloService
from src.tpo_core.domain.identifiers import ActorId


AUTH = ArticoloCommissioningAuthority(ActorId("magazziniere"), "nuovo materiale", "corr", "idem")


def command(**changes):
    values = dict(
        denominazione="Substrato fibra di cocco",
        unita_misura="GRAM",
        authority=AUTH,
    )
    values.update(changes)
    return CommissionArticolo(**values)


def test_canonical_payload_is_deterministic_and_64_hex():
    value = command()
    assert len(value.canonical_payload_hash) == 64
    assert value.canonical_payload_hash == command().canonical_payload_hash


def test_canonical_payload_is_sensitive_to_denominazione_and_unita_misura():
    base = command()
    different_denominazione = command(denominazione="Vaso biodegradabile")
    different_unita = command(unita_misura="UNIT")
    assert base.canonical_payload_hash != different_denominazione.canonical_payload_hash
    assert base.canonical_payload_hash != different_unita.canonical_payload_hash


@pytest.mark.parametrize("value", ["", "   ", "Substrato \n"])
def test_blank_or_unnormalized_denominazione_is_rejected(value):
    with pytest.raises(InvalidArticoloCommandError):
        command(denominazione=value)


def test_invalid_unita_misura_is_rejected():
    with pytest.raises(InvalidArticoloCommandError):
        command(unita_misura="KILOGRAM")


def test_service_is_thin_and_typed():
    class Writer:
        def commission(self, value):
            assert value == command()
            return "ok"

    service = ArticoloService(Writer())
    assert service.commission(command()) == "ok"
    with pytest.raises(InvalidArticoloCommandError):
        service.commission(object())
