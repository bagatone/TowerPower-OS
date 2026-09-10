from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.varieta_lettura.errors import InvalidVarietaLetturaQueryError
from src.tpo_core.application.varieta_lettura.models import (
    ElencoVarieta, RichiediElencoVarieta, RichiediVarieta, Varieta,
)
from src.tpo_core.application.varieta_lettura.service import VarietaLetturaService
from src.tpo_core.domain.identifiers import VarietaId

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)


def test_richiedi_varieta_requires_varieta_id_type():
    with pytest.raises(InvalidVarietaLetturaQueryError):
        RichiediVarieta(varieta_id="VAR-000001")


def test_varieta_allows_absent_prezzo():
    result = Varieta(VarietaId("VAR-000001"), "Rucola", "ATTIVA", None, None, NOW, NOW)
    assert result.prezzo_unitario is None
    assert result.aliquota_igic is None


def test_varieta_allows_present_prezzo():
    result = Varieta(
        VarietaId("VAR-000001"), "Rucola", "ATTIVA", Decimal("3.50"), Decimal("7"), NOW, NOW,
    )
    assert result.prezzo_unitario == Decimal("3.50")


def test_varieta_rejects_invalid_stato():
    with pytest.raises(InvalidVarietaLetturaQueryError):
        Varieta(VarietaId("VAR-000001"), "Rucola", "BOH", None, None, NOW, NOW)


def test_varieta_rejects_negative_prezzo():
    with pytest.raises(InvalidVarietaLetturaQueryError):
        Varieta(
            VarietaId("VAR-000001"), "Rucola", "ATTIVA", Decimal("-1"), Decimal("7"), NOW, NOW,
        )


def test_varieta_rejects_aliquota_out_of_range():
    with pytest.raises(InvalidVarietaLetturaQueryError):
        Varieta(
            VarietaId("VAR-000001"), "Rucola", "ATTIVA", Decimal("3.50"), Decimal("101"), NOW, NOW,
        )


def test_varieta_rejects_partial_prezzo_aliquota():
    with pytest.raises(InvalidVarietaLetturaQueryError):
        Varieta(VarietaId("VAR-000001"), "Rucola", "ATTIVA", Decimal("3.50"), None, NOW, NOW)


def test_elenco_varieta_rejects_non_varieta_items():
    with pytest.raises(InvalidVarietaLetturaQueryError):
        ElencoVarieta(("not-a-varieta",))


def test_service_varieta_is_thin_and_typed():
    class Reader:
        def varieta(self, query):
            assert query == RichiediVarieta(VarietaId("VAR-000001"))
            return "ok"

        def elenco(self, query):
            raise AssertionError("not expected")

    service = VarietaLetturaService(Reader())
    assert service.varieta(RichiediVarieta(VarietaId("VAR-000001"))) == "ok"
    with pytest.raises(InvalidVarietaLetturaQueryError):
        service.varieta(object())


def test_service_elenco_is_thin_and_typed():
    class Reader:
        def varieta(self, query):
            raise AssertionError("not expected")

        def elenco(self, query):
            assert query == RichiediElencoVarieta()
            return "ok"

    service = VarietaLetturaService(Reader())
    assert service.elenco(RichiediElencoVarieta()) == "ok"
    with pytest.raises(InvalidVarietaLetturaQueryError):
        service.elenco(object())
