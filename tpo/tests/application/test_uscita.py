from datetime import date, datetime
from decimal import Decimal

import pytest

from src.tpo_core.application.uscita.errors import (
    InvalidUscitaAmountError, InvalidUscitaCommandError, InvalidUscitaEffectiveAtError,
)
from src.tpo_core.application.uscita.models import (
    CorreggiUscita, RegistraUscita, UscitaAuthority,
)
from src.tpo_core.application.uscita.service import UscitaService
from src.tpo_core.domain.identifiers import ActorId, UscitaId
from src.tpo_core.domain.states import CategoriaUscita, MetodoPagamento


AUTH = UscitaAuthority(ActorId("owner"), "expense paid", "corr", "idem")


def command(**changes):
    values = dict(
        importo=Decimal("45.50"),
        data_uscita=date(2026, 9, 4),
        categoria=CategoriaUscita.SEMENTI,
        beneficiario="Vivai Canarias SL",
        metodo=MetodoPagamento.BONIFICO,
        authority=AUTH,
    )
    values.update(changes)
    return RegistraUscita(**values)


def test_valid_command_and_canonical_payload():
    value = command()
    assert value.importo == Decimal("45.50")
    assert len(value.canonical_payload_hash) == 64
    assert value.data_uscita == date(2026, 9, 4)


@pytest.mark.parametrize("value", ["0", "-1", "1.001"])
def test_nonpositive_or_overprecision_importo_is_rejected(value):
    with pytest.raises(InvalidUscitaAmountError):
        command(importo=Decimal(value))


def test_wrong_data_type_and_invalid_categoria_metodo_are_rejected():
    with pytest.raises(InvalidUscitaEffectiveAtError):
        command(data_uscita=datetime(2026, 9, 4, 8))
    with pytest.raises(InvalidUscitaCommandError):
        command(categoria="FORNITORI")
    with pytest.raises(InvalidUscitaCommandError):
        command(metodo="ASSEGNO")


def test_blank_beneficiario_is_rejected():
    with pytest.raises(InvalidUscitaCommandError):
        command(beneficiario="")
    with pytest.raises(InvalidUscitaCommandError):
        command(beneficiario="   ")


def test_service_record_is_thin_and_typed():
    class Writer:
        def record(self, value):
            assert value == command()
            return "ok"
    service = UscitaService(Writer())
    assert service.record(command()) == "ok"
    with pytest.raises(InvalidUscitaCommandError):
        service.record(object())


def correction(**changes):
    values = dict(
        original_uscita_id=UscitaId("USC-000001"),
        importo=Decimal("-20.00"),
        data_uscita=date(2026, 9, 4),
        categoria=CategoriaUscita.SEMENTI,
        beneficiario="Vivai Canarias SL",
        metodo=MetodoPagamento.BONIFICO,
        authority=AUTH,
    )
    values.update(changes)
    return CorreggiUscita(**values)


def test_negative_and_positive_correction_are_valid():
    negative = correction()
    positive = correction(importo=Decimal("20.00"))
    assert negative.importo == Decimal("-20.00")
    assert positive.importo == Decimal("20.00")


def test_correction_may_reclassify_categoria_freely():
    reclassified = correction(categoria=CategoriaUscita.ATTREZZATURA)
    assert reclassified.categoria == CategoriaUscita.ATTREZZATURA


@pytest.mark.parametrize("value", ["0", "0.001", "-0.001"])
def test_zero_or_overprecision_correction_importo_is_rejected(value):
    with pytest.raises(InvalidUscitaAmountError):
        correction(importo=Decimal(value))


def test_invalid_original_identifier_is_rejected():
    with pytest.raises(InvalidUscitaCommandError):
        correction(original_uscita_id="USC-000001")


def test_distinct_correction_payloads_hash_differently():
    base = correction()
    other_amount = correction(importo=Decimal("-15.00"))
    other_original = correction(original_uscita_id=UscitaId("USC-000002"))
    assert base.canonical_payload_hash != other_amount.canonical_payload_hash
    assert base.canonical_payload_hash != other_original.canonical_payload_hash


def test_service_correct_is_thin_and_typed():
    class Writer:
        def record(self, value):
            raise AssertionError("record non deve essere invocato")

        def correct(self, value):
            assert value == correction()
            return "ok"

    service = UscitaService(Writer())
    assert service.correct(correction()) == "ok"
    with pytest.raises(InvalidUscitaCommandError):
        service.correct(object())
