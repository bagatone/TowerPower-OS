from datetime import date, datetime
from decimal import Decimal

import pytest

from src.tpo_core.application.incasso.errors import (
    InvalidIncassoAmountError, InvalidIncassoCommandError, InvalidIncassoEffectiveAtError,
)
from src.tpo_core.application.incasso.models import (
    CorreggiIncasso, IncassoAuthority, RegistraIncasso,
)
from src.tpo_core.application.incasso.service import IncassoService
from src.tpo_core.domain.identifiers import ActorId, IncassoId, NumeroFattura
from src.tpo_core.domain.states import MetodoPagamento


AUTH = IncassoAuthority(ActorId("owner"), "payment received", "corr", "idem")


def command(**changes):
    values = dict(
        fattura_numero=NumeroFattura("2026/0001"),
        importo=Decimal("107.40"),
        data_incasso=date(2026, 9, 4),
        metodo=MetodoPagamento.BONIFICO,
        authority=AUTH,
    )
    values.update(changes)
    return RegistraIncasso(**values)


def test_valid_command_and_canonical_payload():
    value = command()
    assert value.importo == Decimal("107.40")
    assert len(value.canonical_payload_hash) == 64
    assert value.data_incasso == date(2026, 9, 4)


@pytest.mark.parametrize("value", ["0", "-1", "1.001"])
def test_nonpositive_or_overprecision_importo_is_rejected(value):
    with pytest.raises(InvalidIncassoAmountError):
        command(importo=Decimal(value))


def test_wrong_data_type_and_invalid_metodo_are_rejected():
    with pytest.raises(InvalidIncassoEffectiveAtError):
        command(data_incasso=datetime(2026, 9, 4, 8))
    with pytest.raises(InvalidIncassoCommandError):
        command(metodo="ASSEGNO")


def test_service_record_is_thin_and_typed():
    class Writer:
        def record(self, value):
            assert value == command()
            return "ok"
    service = IncassoService(Writer())
    assert service.record(command()) == "ok"
    with pytest.raises(InvalidIncassoCommandError):
        service.record(object())


def correction(**changes):
    values = dict(
        original_incasso_id=IncassoId("INC-000001"),
        fattura_numero=NumeroFattura("2026/0001"),
        importo=Decimal("-50.00"),
        data_incasso=date(2026, 9, 4),
        metodo=MetodoPagamento.BONIFICO,
        authority=AUTH,
    )
    values.update(changes)
    return CorreggiIncasso(**values)


def test_negative_and_positive_correction_are_valid():
    negative = correction()
    positive = correction(importo=Decimal("50.00"))
    assert negative.importo == Decimal("-50.00")
    assert positive.importo == Decimal("50.00")


@pytest.mark.parametrize("value", ["0", "0.001", "-0.001"])
def test_zero_or_overprecision_correction_importo_is_rejected(value):
    with pytest.raises(InvalidIncassoAmountError):
        correction(importo=Decimal(value))


def test_invalid_original_and_fattura_identifiers_are_rejected():
    with pytest.raises(InvalidIncassoCommandError):
        correction(original_incasso_id="INC-000001")
    with pytest.raises(InvalidIncassoCommandError):
        correction(fattura_numero="2026/0001")


def test_distinct_correction_payloads_hash_differently():
    base = correction()
    other_amount = correction(importo=Decimal("-25.00"))
    other_original = correction(original_incasso_id=IncassoId("INC-000002"))
    assert base.canonical_payload_hash != other_amount.canonical_payload_hash
    assert base.canonical_payload_hash != other_original.canonical_payload_hash


def test_service_correct_is_thin_and_typed():
    class Writer:
        def record(self, value):
            raise AssertionError("record non deve essere invocato")

        def correct(self, value):
            assert value == correction()
            return "ok"

    service = IncassoService(Writer())
    assert service.correct(correction()) == "ok"
    with pytest.raises(InvalidIncassoCommandError):
        service.correct(object())
