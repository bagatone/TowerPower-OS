from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.application.magazzino_lettura.errors import (
    InvalidMagazzinoLetturaQueryError,
)
from src.tpo_core.application.magazzino_lettura.models import (
    Articolo, ElencoArticoli, ElencoMovimenti, ElencoStock, MovimentoMagazzino,
    RichiediElencoArticoli, RichiediElencoMovimenti, RichiediElencoStock,
    StockArticolo, StockVarieta,
)
from src.tpo_core.application.magazzino_lettura.service import MagazzinoLetturaService
from src.tpo_core.domain.identifiers import ArticoloId, MovimentoId, VarietaId

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)


def _movimento(**overrides):
    base = dict(
        movimento_id=MovimentoId("MOV-000001"),
        varieta_id=VarietaId("VAR-000001"),
        varieta_denominazione="Rucola",
        articolo_id=None,
        articolo_denominazione=None,
        unita_misura="GRAM",
        tipo="CARICO",
        direzione="POSITIVO",
        quantita=Decimal("10"),
        data_movimento=NOW,
        motivo="raccolta",
        origine_tipo="RACCOLTA",
        origine_riferimento="RAC-000001",
        raccolta_id=None,
        consegna_id=None,
        run_id=None,
        created_at=NOW,
    )
    base.update(overrides)
    return MovimentoMagazzino(**base)


def test_articolo_requires_denominazione_not_blank():
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        Articolo(ArticoloId("ART-000001"), "  ", "UNIT", NOW)


def test_stock_varieta_rejects_negative_disponibile():
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        StockVarieta(VarietaId("VAR-000001"), "Rucola", Decimal("-1"), "GRAM", NOW, 0)


def test_stock_articolo_rejects_negative_version():
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        StockArticolo(ArticoloId("ART-000001"), "Vaschette", Decimal("1"), "UNIT", NOW, -1)


def test_movimento_requires_exactly_one_risorsa():
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        _movimento(varieta_id=None, varieta_denominazione=None)
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        _movimento(
            articolo_id=ArticoloId("ART-000001"),
            articolo_denominazione="Vaschette",
        )


def test_movimento_requires_denominazione_iff_id_present():
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        _movimento(varieta_denominazione=None)


def test_movimento_rejects_invalid_tipo_or_direzione():
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        _movimento(tipo="ALTRO")
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        _movimento(direzione="NEUTRA")


def test_movimento_rejects_non_positive_quantita():
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        _movimento(quantita=Decimal("0"))


def test_elenco_stock_rejects_non_tuple_members():
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        ElencoStock(stock_varieta=[], stock_articoli=())


class _FakeReader:
    def __init__(self):
        self.articoli_query = None
        self.stock_query = None
        self.movimenti_query = None

    def articoli(self, query):
        self.articoli_query = query
        return ElencoArticoli(())

    def stock(self, query):
        self.stock_query = query
        return ElencoStock((), ())

    def movimenti(self, query):
        self.movimenti_query = query
        return ElencoMovimenti(())


def test_service_delegates_articoli_stock_movimenti():
    reader = _FakeReader()
    service = MagazzinoLetturaService(reader)
    articoli_query = RichiediElencoArticoli()
    stock_query = RichiediElencoStock()
    movimenti_query = RichiediElencoMovimenti()
    assert service.articoli(articoli_query) == ElencoArticoli(())
    assert service.stock(stock_query) == ElencoStock((), ())
    assert service.movimenti(movimenti_query) == ElencoMovimenti(())
    assert reader.articoli_query is articoli_query
    assert reader.stock_query is stock_query
    assert reader.movimenti_query is movimenti_query


def test_service_rejects_invalid_query_types():
    service = MagazzinoLetturaService(_FakeReader())
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        service.articoli(object())
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        service.stock(object())
    with pytest.raises(InvalidMagazzinoLetturaQueryError):
        service.movimenti(object())
