from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.finanze_lettura.errors import InvalidFinanzeLetturaQueryError
from src.tpo_core.application.finanze_lettura.models import (
    ElencoFatture, ElencoIncassi, ElencoUscite, Fattura, Incasso,
    RichiediElencoFatture, RichiediElencoIncassi, RichiediElencoUscite, RigaFattura, Uscita,
)
from src.tpo_core.application.finanze_lettura.service import FinanzeLetturaService
from src.tpo_core.domain.identifiers import ClienteId, IncassoId, NumeroFattura, UscitaId, VarietaId

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)
OGGI = date(2099, 1, 1)


def _fattura(**overrides):
    base = dict(
        numero_fattura=NumeroFattura("2099/0001"), cliente_id=ClienteId("CLI-000001"),
        cliente_denominazione="Ristorante Sole", data_emissione=OGGI, scadenza=OGGI,
        totale_netto=Decimal("100.00"), totale_igic=Decimal("7.00"), totale=Decimal("107.00"),
        rettifica_di=None, consegne_collegate=(), righe=(),
    )
    base.update(overrides)
    return Fattura(**base)


def _incasso(**overrides):
    base = dict(
        incasso_id=IncassoId("INC-000001"), fattura_numero=NumeroFattura("2099/0001"),
        importo=Decimal("107.00"), data_incasso=OGGI, metodo="BONIFICO", note=None,
        rettifica_incasso_id=None, created_at=NOW,
    )
    base.update(overrides)
    return Incasso(**base)


def _uscita(**overrides):
    base = dict(
        uscita_id=UscitaId("USC-000001"), importo=Decimal("50.00"), data_uscita=OGGI,
        categoria="SEMENTI", beneficiario="Vivai Sole", metodo="BONIFICO", note=None,
        rettifica_uscita_id=None, created_at=NOW,
    )
    base.update(overrides)
    return Uscita(**base)


def test_riga_fattura_rejects_invalid_aliquota():
    with pytest.raises(InvalidFinanzeLetturaQueryError):
        RigaFattura(1, VarietaId("VAR-000001"), "Rucola", Decimal("1"), "GRAM",
                    Decimal("2"), Decimal("101"), Decimal("2"), Decimal("0.14"))


def test_fattura_requires_totale_coherent():
    with pytest.raises(InvalidFinanzeLetturaQueryError):
        _fattura(totale=Decimal("999.00"))


def test_fattura_rejects_scadenza_before_emissione():
    with pytest.raises(InvalidFinanzeLetturaQueryError):
        _fattura(scadenza=date(2098, 1, 1))


def test_fattura_rejects_self_rettifica():
    with pytest.raises(InvalidFinanzeLetturaQueryError):
        _fattura(rettifica_di=NumeroFattura("2099/0001"))


def test_incasso_requires_positive_importo_when_ordinary():
    with pytest.raises(InvalidFinanzeLetturaQueryError):
        _incasso(importo=Decimal("0"))


def test_incasso_allows_negative_importo_when_rettifica():
    incasso = _incasso(importo=Decimal("-10"), rettifica_incasso_id=IncassoId("INC-000002"))
    assert incasso.importo == Decimal("-10")


def test_incasso_rejects_invalid_metodo():
    with pytest.raises(InvalidFinanzeLetturaQueryError):
        _incasso(metodo="ASSEGNO")


def test_uscita_rejects_blank_beneficiario():
    with pytest.raises(InvalidFinanzeLetturaQueryError):
        _uscita(beneficiario="   ")


def test_uscita_rejects_invalid_categoria():
    with pytest.raises(InvalidFinanzeLetturaQueryError):
        _uscita(categoria="VARIE")


def test_uscita_rejects_zero_importo_on_rettifica():
    with pytest.raises(InvalidFinanzeLetturaQueryError):
        _uscita(importo=Decimal("0"), rettifica_uscita_id=UscitaId("USC-000002"))


class _FakeReader:
    def __init__(self):
        self.queries = {}

    def fatture(self, query):
        self.queries["fatture"] = query
        return ElencoFatture(())

    def incassi(self, query):
        self.queries["incassi"] = query
        return ElencoIncassi(())

    def uscite(self, query):
        self.queries["uscite"] = query
        return ElencoUscite(())


def test_service_delegates_all_three_queries():
    reader = _FakeReader()
    service = FinanzeLetturaService(reader)
    assert service.fatture(RichiediElencoFatture()) == ElencoFatture(())
    assert service.incassi(RichiediElencoIncassi()) == ElencoIncassi(())
    assert service.uscite(RichiediElencoUscite()) == ElencoUscite(())
    assert set(reader.queries) == {"fatture", "incassi", "uscite"}


def test_service_rejects_invalid_query_types():
    service = FinanzeLetturaService(_FakeReader())
    with pytest.raises(InvalidFinanzeLetturaQueryError):
        service.fatture(object())
    with pytest.raises(InvalidFinanzeLetturaQueryError):
        service.incassi(object())
    with pytest.raises(InvalidFinanzeLetturaQueryError):
        service.uscite(object())
