from datetime import date
from decimal import Decimal

import pytest

from src.tpo_core.application.semente_lettura.errors import InvalidSementeLetturaQueryError
from src.tpo_core.application.semente_lettura.models import (
    ElencoLotti, ElencoSementi, LottoSeme, RichiediElencoLotti,
    RichiediElencoSementi, RichiediLotto, Semente,
)
from src.tpo_core.application.semente_lettura.service import SementeLetturaService
from src.tpo_core.domain.identifiers import LottoSemeId


def test_semente_rejects_blank_fornitore():
    with pytest.raises(InvalidSementeLetturaQueryError):
        Semente(1, "  ", "REF-1", None, None, True)


def test_elenco_sementi_rejects_non_semente_items():
    with pytest.raises(InvalidSementeLetturaQueryError):
        ElencoSementi(("not-a-semente",))


def test_richiedi_lotto_requires_lotto_seme_id_type():
    with pytest.raises(InvalidSementeLetturaQueryError):
        RichiediLotto(lotto_seme_id="LSE-000001")


def test_lotto_rejects_quantita_residua_over_iniziale():
    with pytest.raises(InvalidSementeLetturaQueryError):
        LottoSeme(
            LottoSemeId("LSE-000001"), "Fornitore", "REF-1", "NUM-1",
            date(2026, 1, 1), None, Decimal("10"), Decimal("11"), "GRAM", None,
        )


def test_lotto_rejects_scadenza_before_ricezione():
    with pytest.raises(InvalidSementeLetturaQueryError):
        LottoSeme(
            LottoSemeId("LSE-000001"), "Fornitore", "REF-1", "NUM-1",
            date(2026, 6, 1), date(2026, 1, 1), Decimal("10"), Decimal("5"), "GRAM", None,
        )


def test_lotto_allows_valid_values():
    result = LottoSeme(
        LottoSemeId("LSE-000001"), "Fornitore", "REF-1", "NUM-1",
        date(2026, 1, 1), date(2027, 1, 1), Decimal("10"), Decimal("5"), "GRAM", None,
    )
    assert result.quantita_residua == Decimal("5")


def test_elenco_lotti_rejects_non_lotto_items():
    with pytest.raises(InvalidSementeLetturaQueryError):
        ElencoLotti(("not-a-lotto",))


def test_service_elenco_sementi_is_thin_and_typed():
    class Reader:
        def elenco_sementi(self, query):
            assert query == RichiediElencoSementi()
            return "ok"

        def lotto(self, query):
            raise AssertionError("not expected")

        def elenco_lotti(self, query):
            raise AssertionError("not expected")

    service = SementeLetturaService(Reader())
    assert service.elenco_sementi(RichiediElencoSementi()) == "ok"
    with pytest.raises(InvalidSementeLetturaQueryError):
        service.elenco_sementi(object())


def test_service_lotto_is_thin_and_typed():
    class Reader:
        def elenco_sementi(self, query):
            raise AssertionError("not expected")

        def lotto(self, query):
            assert query == RichiediLotto(LottoSemeId("LSE-000001"))
            return "ok"

        def elenco_lotti(self, query):
            raise AssertionError("not expected")

    service = SementeLetturaService(Reader())
    assert service.lotto(RichiediLotto(LottoSemeId("LSE-000001"))) == "ok"
    with pytest.raises(InvalidSementeLetturaQueryError):
        service.lotto(object())


def test_service_elenco_lotti_is_thin_and_typed():
    class Reader:
        def elenco_sementi(self, query):
            raise AssertionError("not expected")

        def lotto(self, query):
            raise AssertionError("not expected")

        def elenco_lotti(self, query):
            assert query == RichiediElencoLotti()
            return "ok"

    service = SementeLetturaService(Reader())
    assert service.elenco_lotti(RichiediElencoLotti()) == "ok"
    with pytest.raises(InvalidSementeLetturaQueryError):
        service.elenco_lotti(object())
