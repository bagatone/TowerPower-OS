from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.semina_raccolta_lettura.errors import (
    InvalidSeminaRaccoltaLetturaQueryError,
)
from src.tpo_core.application.semina_raccolta_lettura.models import (
    ElencoSemine, Raccolta, RichiediElencoSemine, RichiediSemina, Semina,
)
from src.tpo_core.application.semina_raccolta_lettura.service import (
    SeminaRaccoltaLetturaService,
)
from src.tpo_core.domain.identifiers import RaccoltaId, SeminaId, VarietaId

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)


def _semina(**overrides):
    base = dict(
        semina_id=SeminaId("SEM-000001"),
        varieta_id=VarietaId("VAR-000001"),
        varieta_denominazione="Rucola",
        stato="AVVIATA",
        quantita_seme=Decimal("30"),
        unita_misura="GRAM",
        data_avvio=NOW,
        causa_origine="MANUALE",
        esito_finale=None,
        cultivar_snapshot="Rucola standard",
        lotto_seme_snapshot="LSE-000001 Rijk Zwaan",
        raccolte=(),
    )
    base.update(overrides)
    return Semina(**base)


def test_richiedi_semina_requires_semina_id_type():
    with pytest.raises(InvalidSeminaRaccoltaLetturaQueryError):
        RichiediSemina(semina_id="SEM-000001")


def test_semina_requires_esito_finale_iff_chiusa():
    with pytest.raises(InvalidSeminaRaccoltaLetturaQueryError):
        _semina(stato="CHIUSA", esito_finale=None)
    with pytest.raises(InvalidSeminaRaccoltaLetturaQueryError):
        _semina(stato="AVVIATA", esito_finale="RACCOLTA_COMPLETA")


def test_semina_allows_chiusa_with_esito():
    result = _semina(stato="CHIUSA", esito_finale="RACCOLTA_COMPLETA")
    assert result.esito_finale == "RACCOLTA_COMPLETA"


def test_semina_rejects_invalid_stato():
    with pytest.raises(InvalidSeminaRaccoltaLetturaQueryError):
        _semina(stato="BOH")


def test_semina_rejects_raccolta_of_another_semina():
    altra = Raccolta(
        RaccoltaId("RAC-000001"), SeminaId("SEM-000002"), NOW, Decimal("2"), "SET",
        None, None, None,
    )
    with pytest.raises(InvalidSeminaRaccoltaLetturaQueryError):
        _semina(raccolte=(altra,))


def test_semina_allows_matching_raccolta():
    propria = Raccolta(
        RaccoltaId("RAC-000001"), SeminaId("SEM-000001"), NOW, Decimal("2"), "SET",
        None, None, None,
    )
    result = _semina(raccolte=(propria,))
    assert result.raccolte == (propria,)


def test_raccolta_rejects_non_positive_quantita():
    with pytest.raises(InvalidSeminaRaccoltaLetturaQueryError):
        Raccolta(
            RaccoltaId("RAC-000001"), SeminaId("SEM-000001"), NOW, Decimal("0"), "SET",
            None, None, None,
        )


def test_elenco_semine_rejects_non_semina_items():
    with pytest.raises(InvalidSeminaRaccoltaLetturaQueryError):
        ElencoSemine(("not-a-semina",))


def test_service_semina_is_thin_and_typed():
    class Reader:
        def semina(self, query):
            assert query == RichiediSemina(SeminaId("SEM-000001"))
            return "ok"

        def elenco(self, query):
            raise AssertionError("not expected")

    service = SeminaRaccoltaLetturaService(Reader())
    assert service.semina(RichiediSemina(SeminaId("SEM-000001"))) == "ok"
    with pytest.raises(InvalidSeminaRaccoltaLetturaQueryError):
        service.semina(object())


def test_service_elenco_is_thin_and_typed():
    class Reader:
        def semina(self, query):
            raise AssertionError("not expected")

        def elenco(self, query):
            assert query == RichiediElencoSemine()
            return "ok"

    service = SeminaRaccoltaLetturaService(Reader())
    assert service.elenco(RichiediElencoSemine()) == "ok"
    with pytest.raises(InvalidSeminaRaccoltaLetturaQueryError):
        service.elenco(object())
