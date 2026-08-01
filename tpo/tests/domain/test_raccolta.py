from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.domain.entities.raccolta import Raccolta
from src.tpo_core.domain.errors import (
    InvalidQuantityError,
    InvalidTimeReferenceError,
    InvariantViolationError,
)
from src.tpo_core.domain.identifiers import RaccoltaId, SeminaId, VarietaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.time_reference import OFFICIAL_TIMEZONE_NAME


def build_raccolta(**overrides) -> Raccolta:
    data = {
        "id": RaccoltaId("RAC-000001"),
        "semina_id": SeminaId("SEM-000001"),
        "data_raccolta": datetime(2026, 7, 10, 8, 30, tzinfo=timezone.utc),
        "quantita": Quantity(Decimal("12"), UnitOfMeasure.SET),
    }
    data.update(overrides)
    return Raccolta(**data)


def test_creazione_valida() -> None:
    raccolta = build_raccolta()
    assert raccolta.id == RaccoltaId("RAC-000001")
    assert raccolta.semina_id == SeminaId("SEM-000001")
    assert raccolta.quantita == Quantity(12, UnitOfMeasure.SET)
    assert raccolta.operatore is None
    assert raccolta.destinazione_prevista is None
    assert raccolta.note is None


@pytest.mark.parametrize("identifier", [None, "RAC-000001", SeminaId("SEM-000001")])
def test_raccolta_id_obbligatorio_e_tipizzato(identifier) -> None:
    with pytest.raises(InvariantViolationError, match="RaccoltaId"):
        build_raccolta(id=identifier)


@pytest.mark.parametrize("semina_id", [None, "SEM-000001", VarietaId("VAR-000001")])
def test_semina_id_obbligatorio_e_tipizzato(semina_id) -> None:
    with pytest.raises(InvariantViolationError, match="SeminaId"):
        build_raccolta(semina_id=semina_id)


def test_data_raccolta_obbligatoria() -> None:
    with pytest.raises(InvalidTimeReferenceError, match="datetime"):
        build_raccolta(data_raccolta=None)


def test_datetime_naive_rifiutato() -> None:
    with pytest.raises(InvalidTimeReferenceError, match="fuso orario"):
        build_raccolta(data_raccolta=datetime(2026, 7, 10, 8, 30))


def test_data_raccolta_normalizzata_in_atlantic_canary() -> None:
    raccolta = build_raccolta()
    assert raccolta.data_raccolta.tzinfo is not None
    assert getattr(raccolta.data_raccolta.tzinfo, "key", None) == OFFICIAL_TIMEZONE_NAME


@pytest.mark.parametrize("quantita", [None, Decimal("1")])
def test_quantita_obbligatoria(quantita) -> None:
    with pytest.raises(InvalidQuantityError, match="quantità valida"):
        build_raccolta(quantita=quantita)


def test_quantita_deve_essere_maggiore_di_zero() -> None:
    with pytest.raises(InvalidQuantityError, match="maggiore di zero"):
        build_raccolta(quantita=Quantity(0, UnitOfMeasure.SET))


@pytest.mark.parametrize("unit", [UnitOfMeasure.GRAM, UnitOfMeasure.UNIT])
def test_unita_ufficiale_e_set(unit) -> None:
    with pytest.raises(InvalidQuantityError, match="SET"):
        build_raccolta(quantita=Quantity(1, unit))


def test_quantita_negativa_rifiutata_da_quantity() -> None:
    with pytest.raises(InvalidQuantityError, match="negativa"):
        Quantity(-1, UnitOfMeasure.SET)


def test_identita_determinata_esclusivamente_da_raccolta_id() -> None:
    prima = build_raccolta()
    seconda = build_raccolta(
        semina_id=SeminaId("SEM-000002"),
        data_raccolta=datetime(2026, 7, 11, 12, tzinfo=timezone.utc),
        quantita=Quantity(20, UnitOfMeasure.SET),
        operatore="Operatore differente",
        destinazione_prevista="Destinazione differente",
        note="Note differenti",
    )
    assert prima == seconda
    assert hash(prima) == hash(seconda)


def test_id_differenti_rappresentano_eventi_differenti() -> None:
    assert build_raccolta() != build_raccolta(id=RaccoltaId("RAC-000002"))


@pytest.mark.parametrize(
    "attribute",
    [
        "id",
        "semina_id",
        "data_raccolta",
        "quantita",
        "operatore",
        "destinazione_prevista",
        "note",
    ],
)
def test_attributi_immutabili(attribute) -> None:
    raccolta = build_raccolta()
    with pytest.raises(FrozenInstanceError):
        setattr(raccolta, attribute, getattr(raccolta, attribute))


def test_riferimento_permanente_a_una_sola_semina() -> None:
    raccolta = build_raccolta()
    assert isinstance(raccolta.semina_id, SeminaId)
    assert not hasattr(raccolta, "semine_ids")


def test_campi_facoltativi_vengono_conservati() -> None:
    raccolta = build_raccolta(
        operatore="Mario Rossi",
        destinazione_prevista="Cliente Alfa",
        note="Prelievo mattutino",
    )
    assert raccolta.operatore == "Mario Rossi"
    assert raccolta.destinazione_prevista == "Cliente Alfa"
    assert raccolta.note == "Prelievo mattutino"


@pytest.mark.parametrize("campo", ["operatore", "destinazione_prevista", "note"])
@pytest.mark.parametrize("valore", ["", " ", 12])
def test_campi_facoltativi_se_presenti_sono_stringhe_non_vuote(campo, valore) -> None:
    with pytest.raises(InvariantViolationError, match="facoltativo"):
        build_raccolta(**{campo: valore})


def test_non_espone_operazioni_su_stock_o_movimenti() -> None:
    raccolta = build_raccolta()
    for method_name in (
        "modifica_stock",
        "aggiorna_stock",
        "crea_movimento",
        "genera_carico",
    ):
        assert not hasattr(raccolta, method_name)


def test_non_chiude_automaticamente_la_semina() -> None:
    raccolta = build_raccolta()
    assert not hasattr(raccolta, "chiudi_semina")
    assert not hasattr(raccolta, "semina")


def test_modulo_non_importa_dipendenze_infrastrutturali() -> None:
    module = __import__("src.tpo_core.domain.entities.raccolta", fromlist=["*"])
    module_names = set(module.__dict__)
    assert "sqlite3" not in module_names
    assert "yaml" not in module_names
    assert "google" not in module_names
    assert "Stock" not in module_names
    assert "Movimento" not in module_names
