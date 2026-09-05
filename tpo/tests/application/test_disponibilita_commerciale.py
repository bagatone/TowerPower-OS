from decimal import Decimal

import pytest

from src.tpo_core.application.disponibilita_commerciale.errors import (
    InvalidDisponibilitaCommercialeQueryError,
)
from src.tpo_core.application.disponibilita_commerciale.models import (
    DisponibilitaCommerciale, RichiediDisponibilitaCommerciale,
)
from src.tpo_core.application.disponibilita_commerciale.service import (
    DisponibilitaCommercialeService,
)
from src.tpo_core.domain.identifiers import VarietaId


def test_query_requires_varieta_id_type():
    with pytest.raises(InvalidDisponibilitaCommercialeQueryError):
        RichiediDisponibilitaCommerciale(varieta_id="VAR-000001")


def test_result_computes_vendibile_and_allarme_correctly():
    result = DisponibilitaCommerciale(
        VarietaId("VAR-000001"), "GRAM", Decimal("100"), Decimal("40"), Decimal("60"), False,
    )
    assert result.vendibile == Decimal("60")
    assert result.integrita_allarme is False


def test_result_rejects_inconsistent_vendibile():
    with pytest.raises(InvalidDisponibilitaCommercialeQueryError):
        DisponibilitaCommerciale(
            VarietaId("VAR-000001"), "GRAM", Decimal("100"), Decimal("40"), Decimal("59"), False,
        )


def test_result_rejects_inconsistent_allarme():
    with pytest.raises(InvalidDisponibilitaCommercialeQueryError):
        DisponibilitaCommerciale(
            VarietaId("VAR-000001"), "GRAM", Decimal("10"), Decimal("40"), Decimal("-30"), False,
        )


def test_result_allows_negative_vendibile_with_allarme_true():
    result = DisponibilitaCommerciale(
        VarietaId("VAR-000001"), "GRAM", Decimal("10"), Decimal("40"), Decimal("-30"), True,
    )
    assert result.integrita_allarme is True


@pytest.mark.parametrize("disponibile,prenotato", [(Decimal("-1"), Decimal("0")),
                                                     (Decimal("0"), Decimal("-1"))])
def test_result_rejects_negative_disponibile_or_prenotato(disponibile, prenotato):
    with pytest.raises(InvalidDisponibilitaCommercialeQueryError):
        DisponibilitaCommerciale(
            VarietaId("VAR-000001"), "GRAM", disponibile, prenotato,
            disponibile - prenotato, (disponibile - prenotato) < 0,
        )


def test_service_is_thin_and_typed():
    class Reader:
        def disponibilita(self, value):
            assert value == RichiediDisponibilitaCommerciale(VarietaId("VAR-000001"))
            return "ok"

    service = DisponibilitaCommercialeService(Reader())
    assert service.disponibilita(
        RichiediDisponibilitaCommerciale(VarietaId("VAR-000001"))
    ) == "ok"
    with pytest.raises(InvalidDisponibilitaCommercialeQueryError):
        service.disponibilita(object())
