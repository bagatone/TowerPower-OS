from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.domain.entities.stock import Stock
from src.tpo_core.domain.errors import (
    InvalidQuantityError,
    InvalidTimeReferenceError,
    InvariantViolationError,
)
from src.tpo_core.domain.identifiers import SeminaId, VarietaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.time_reference import OFFICIAL_TIMEZONE_NAME


def build_stock(**overrides) -> Stock:
    data = {
        "varieta_id": VarietaId("VAR-000001"),
        "disponibile": Quantity(Decimal("12"), UnitOfMeasure.SET),
        "ultimo_aggiornamento": datetime(2026, 7, 10, 8, 30, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return Stock(**data)


def test_creazione_valida_con_quantita_positiva() -> None:
    stock = build_stock()
    assert stock.varieta_id == VarietaId("VAR-000001")
    assert stock.disponibile == Quantity(12, UnitOfMeasure.SET)


def test_creazione_valida_con_quantita_zero() -> None:
    stock = build_stock(disponibile=Quantity(0, UnitOfMeasure.SET))
    assert stock.disponibile.value == 0


@pytest.mark.parametrize("varieta_id", [None, "VAR-000001", SeminaId("SEM-000001")])
def test_varieta_id_obbligatorio_e_tipizzato(varieta_id) -> None:
    with pytest.raises(InvariantViolationError, match="VarietaId"):
        build_stock(varieta_id=varieta_id)


@pytest.mark.parametrize("disponibile", [None, Decimal("1")])
def test_disponibile_obbligatorio_e_quantity(disponibile) -> None:
    with pytest.raises(InvalidQuantityError, match="quantità disponibile"):
        build_stock(disponibile=disponibile)


def test_quantita_negativa_rifiutata_da_quantity() -> None:
    with pytest.raises(InvalidQuantityError, match="negativa"):
        Quantity(-1, UnitOfMeasure.SET)


@pytest.mark.parametrize("unit", list(UnitOfMeasure))
def test_tutte_le_unita_ufficiali_sono_accettate(unit) -> None:
    stock = build_stock(disponibile=Quantity(1, unit))
    assert stock.disponibile.unit is unit


def test_ultimo_aggiornamento_e_facoltativo() -> None:
    stock = build_stock(ultimo_aggiornamento=None)
    assert stock.ultimo_aggiornamento is None


def test_ultimo_aggiornamento_naive_rifiutato() -> None:
    with pytest.raises(InvalidTimeReferenceError, match="fuso orario"):
        build_stock(ultimo_aggiornamento=datetime(2026, 7, 10, 8, 30))


def test_ultimo_aggiornamento_deve_essere_datetime() -> None:
    with pytest.raises(InvalidTimeReferenceError, match="datetime"):
        build_stock(ultimo_aggiornamento="2026-07-10")


def test_ultimo_aggiornamento_normalizzato_in_atlantic_canary() -> None:
    stock = build_stock()
    assert stock.ultimo_aggiornamento is not None
    assert getattr(stock.ultimo_aggiornamento.tzinfo, "key", None) == OFFICIAL_TIMEZONE_NAME


def test_identita_determinata_esclusivamente_da_varieta_id() -> None:
    primo = build_stock(
        disponibile=Quantity(1, UnitOfMeasure.SET),
        ultimo_aggiornamento=datetime(2026, 7, 10, tzinfo=timezone.utc),
    )
    secondo = build_stock(
        disponibile=Quantity(99, UnitOfMeasure.GRAM),
        ultimo_aggiornamento=datetime(2026, 7, 11, tzinfo=timezone.utc),
    )
    assert primo == secondo
    assert hash(primo) == hash(secondo)


def test_varieta_differenti_rappresentano_stock_differenti() -> None:
    assert build_stock() != build_stock(varieta_id=VarietaId("VAR-000002"))


@pytest.mark.parametrize(
    "attribute",
    ["varieta_id", "disponibile", "ultimo_aggiornamento"],
)
def test_fotografia_stock_immutabile(attribute) -> None:
    stock = build_stock()
    with pytest.raises(FrozenInstanceError):
        setattr(stock, attribute, getattr(stock, attribute))


def test_modello_contiene_esclusivamente_i_campi_autorizzati() -> None:
    assert [field.name for field in fields(Stock)] == [
        "varieta_id",
        "disponibile",
        "ultimo_aggiornamento",
    ]


def test_non_contiene_prenotato_o_storico_movimenti() -> None:
    stock = build_stock()
    for attribute in ("prenotato", "movimenti", "storico", "saldo_precedente"):
        assert not hasattr(stock, attribute)


def test_non_espone_operazioni_di_modifica_o_prenotazione() -> None:
    stock = build_stock()
    for method_name in (
        "carica",
        "scarica",
        "rettifica",
        "modifica_disponibile",
        "applica_movimento",
        "prenota",
        "libera_prenotazione",
        "aggiorna_timestamp",
    ):
        assert not hasattr(stock, method_name)


def test_non_genera_allarme_rosso() -> None:
    stock = build_stock()
    assert not hasattr(stock, "genera_allarme")
    assert not hasattr(stock, "allarme_rosso")


def test_non_mantiene_relazioni_con_altri_register_produttivi_o_logistici() -> None:
    stock = build_stock()
    for attribute in (
        "semina_id",
        "raccolta_id",
        "consegna_id",
        "movimento_id",
    ):
        assert not hasattr(stock, attribute)


def test_modulo_non_importa_dipendenze_infrastrutturali() -> None:
    module = __import__("src.tpo_core.domain.entities.stock", fromlist=["*"])
    module_names = set(module.__dict__)
    assert "sqlite3" not in module_names
    assert "yaml" not in module_names
    assert "google" not in module_names
    assert "MovimentoMagazzino" not in module_names
