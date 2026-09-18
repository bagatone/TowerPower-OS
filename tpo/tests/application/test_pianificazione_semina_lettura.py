from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.pianificazione_semina_lettura.errors import (
    InvalidPianificazioneSeminaLetturaQueryError,
)
from src.tpo_core.application.pianificazione_semina_lettura.models import (
    ElencoDaSeminare,
    RichiediElencoDaSeminare,
    RigaDaSeminare,
)
from src.tpo_core.application.pianificazione_semina_lettura.service import (
    PianificazioneSeminaLetturaService,
)
from src.tpo_core.domain.identifiers import ClienteId, RigaPianoSeminaId, VarietaId

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)
OGGI = date(2099, 1, 1)


def _riga(**overrides) -> RigaDaSeminare:
    fields = dict(
        riga_id=RigaPianoSeminaId("RPS-000001"),
        varieta_id=VarietaId("VAR-000001"),
        varieta_denominazione="Afila",
        cliente_id=ClienteId("CLI-000001"),
        cliente_denominazione="Selvaje",
        stato="PIANIFICATA",
        quantita_da_seminare=Decimal("2"),
        unita_misura="SET",
        grammi_seme_richiesti=Decimal("50"),
        sowing_at=NOW,
        harvest_target_at=NOW,
        data_consegna=OGGI,
    )
    fields.update(overrides)
    return RigaDaSeminare(**fields)


def test_riga_da_seminare_rejects_blank_varieta_denominazione():
    with pytest.raises(InvalidPianificazioneSeminaLetturaQueryError):
        _riga(varieta_denominazione="  ")


def test_riga_da_seminare_rejects_blank_cliente_denominazione():
    with pytest.raises(InvalidPianificazioneSeminaLetturaQueryError):
        _riga(cliente_denominazione="")


@pytest.mark.parametrize("stato", ["AVVIATA", "SODDISFATTA", "ANNULLATA", "SOSTITUITA", "ALTRO"])
def test_riga_da_seminare_rejects_stato_non_ammesso(stato):
    with pytest.raises(InvalidPianificazioneSeminaLetturaQueryError):
        _riga(stato=stato)


@pytest.mark.parametrize("stato", ["PIANIFICATA", "PRONTA", "TARDIVA"])
def test_riga_da_seminare_accetta_stati_non_avviati(stato):
    result = _riga(stato=stato)
    assert result.stato == stato


def test_riga_da_seminare_rejects_quantita_non_positiva():
    with pytest.raises(InvalidPianificazioneSeminaLetturaQueryError):
        _riga(quantita_da_seminare=Decimal("0"))


def test_riga_da_seminare_rejects_unita_misura_sconosciuta():
    with pytest.raises(InvalidPianificazioneSeminaLetturaQueryError):
        _riga(unita_misura="LITRO")


def test_riga_da_seminare_rejects_grammi_seme_non_positivi():
    with pytest.raises(InvalidPianificazioneSeminaLetturaQueryError):
        _riga(grammi_seme_richiesti=Decimal("-1"))


def test_elenco_da_seminare_rejects_non_riga_items():
    with pytest.raises(InvalidPianificazioneSeminaLetturaQueryError):
        ElencoDaSeminare(("not-a-riga",))


def test_service_elenco_is_thin_and_typed():
    class Reader:
        def elenco(self, query):
            assert query == RichiediElencoDaSeminare()
            return "ok"

    service = PianificazioneSeminaLetturaService(Reader())
    assert service.elenco(RichiediElencoDaSeminare()) == "ok"
    with pytest.raises(InvalidPianificazioneSeminaLetturaQueryError):
        service.elenco(object())
