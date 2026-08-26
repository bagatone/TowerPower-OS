from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.domain.entities.semina import Semina
from src.tpo_core.domain.errors import (
    InvalidQuantityError,
    InvalidTimeReferenceError,
    InvariantViolationError,
)
from src.tpo_core.domain.identifiers import LottoSemeId, ProtocolloVersioneId, SeminaId, VarietaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import SeminaState
from src.tpo_core.domain.traceability import SeminaTraceabilityCode
from src.tpo_core.domain.time_reference import OFFICIAL_TIMEZONE_NAME


def build_semina(**overrides) -> Semina:
    data = {
        "id": SeminaId("SEM-000001"),
        "varieta_id": VarietaId("VAR-000001"),
        "stato": SeminaState.AVVIATA,
        "quantita_seme": Quantity(Decimal("12.5"), UnitOfMeasure.GRAM),
        "data_avvio": datetime(2026, 7, 1, 8, 30, tzinfo=timezone.utc),
        "cultivar": "Genovese",
        "uso_produttivo": "Microgreens",
        "lotto_seme": "LOTTO-2026-07",
        "versione_protocollo": "1.0",
        "causa_origine": "produzione pianificata",
        "lotto_seme_id": LottoSemeId("LSE-000001"),
        "protocollo_versione_id": ProtocolloVersioneId("PV-000001"),
        "traceability_code": SeminaTraceabilityCode("AFI-0107-A"),
    }
    data.update(overrides)
    return Semina(**data)


def test_creazione_valida_e_normalizzazione_temporale() -> None:
    semina = build_semina()
    assert semina.id == SeminaId("SEM-000001")
    assert semina.varieta_id == VarietaId("VAR-000001")
    assert semina.stato is SeminaState.AVVIATA
    assert semina.quantita_seme == Quantity(Decimal("12.5"), UnitOfMeasure.GRAM)
    assert semina.data_avvio.tzinfo is not None
    assert getattr(semina.data_avvio.tzinfo, "key", None) == OFFICIAL_TIMEZONE_NAME


@pytest.mark.parametrize("identifier", [None, "SEM-000001", VarietaId("VAR-000001")])
def test_semina_id_obbligatorio_e_tipizzato(identifier) -> None:
    with pytest.raises(InvariantViolationError, match="SeminaId"):
        build_semina(id=identifier)


@pytest.mark.parametrize("varieta_id", [None, "VAR-000001", SeminaId("SEM-000002")])
def test_riferimento_a_varieta_obbligatorio_e_tipizzato(varieta_id) -> None:
    with pytest.raises(InvariantViolationError, match="VarietaId"):
        build_semina(varieta_id=varieta_id)


@pytest.mark.parametrize("stato", [None, "AVVIATA"])
def test_stato_ufficiale_obbligatorio(stato) -> None:
    with pytest.raises(InvariantViolationError, match="SeminaState"):
        build_semina(stato=stato)


@pytest.mark.parametrize("quantita", [None, Decimal("1")])
def test_quantita_di_seme_obbligatoria(quantita) -> None:
    with pytest.raises(InvalidQuantityError, match="quantità di seme"):
        build_semina(quantita_seme=quantita)


@pytest.mark.parametrize("unit", [UnitOfMeasure.SET, UnitOfMeasure.UNIT])
def test_quantita_di_seme_esclusivamente_in_grammi(unit) -> None:
    with pytest.raises(InvalidQuantityError, match="grammi"):
        build_semina(quantita_seme=Quantity(1, unit))


def test_quantita_zero_rifiutata() -> None:
    with pytest.raises(InvalidQuantityError, match="maggiore di zero"):
        build_semina(quantita_seme=Quantity(0, UnitOfMeasure.GRAM))


def test_quantita_negativa_rifiutata_da_quantity() -> None:
    with pytest.raises(InvalidQuantityError, match="negativa"):
        Quantity(-1, UnitOfMeasure.GRAM)


def test_data_avvio_naive_rifiutata() -> None:
    with pytest.raises(InvalidTimeReferenceError, match="fuso orario"):
        build_semina(data_avvio=datetime(2026, 7, 1, 8, 30))


@pytest.mark.parametrize(
    ("campo", "valore"),
    [
        ("cultivar", ""),
        ("uso_produttivo", " "),
        ("lotto_seme", None),
        ("versione_protocollo", ""),
        ("causa_origine", "\t"),
    ],
)
def test_dati_costitutivi_obbligatori(campo, valore) -> None:
    with pytest.raises(InvariantViolationError):
        build_semina(**{campo: valore})


def test_semina_chiusa_richiede_esito_finale_ufficiale() -> None:
    with pytest.raises(InvariantViolationError, match="esito finale ufficiale"):
        build_semina(stato=SeminaState.CHIUSA)


def test_semina_chiusa_conserva_esito_finale() -> None:
    semina = build_semina(stato=SeminaState.CHIUSA, esito_finale="scarto totale")
    assert semina.esito_finale == "scarto totale"


def test_semina_attiva_non_accetta_esito_finale() -> None:
    with pytest.raises(InvariantViolationError, match="esclusivamente"):
        build_semina(esito_finale="interruzione")


def test_identita_determinata_esclusivamente_da_semina_id() -> None:
    prima = build_semina()
    seconda = build_semina(
        varieta_id=VarietaId("VAR-000002"),
        stato=SeminaState.CRESCITA,
        quantita_seme=Quantity(20, UnitOfMeasure.GRAM),
        cultivar="Cultivar differente",
        uso_produttivo="Uso differente",
        lotto_seme="LOTTO-DIFFERENTE",
        versione_protocollo="2.0",
        causa_origine="test",
    )
    assert prima == seconda
    assert hash(prima) == hash(seconda)


def test_id_diversi_rappresentano_semine_distinte() -> None:
    assert build_semina() != build_semina(id=SeminaId("SEM-000002"))


@pytest.mark.parametrize(
    "attribute",
    [
        "id",
        "varieta_id",
        "stato",
        "quantita_seme",
        "data_avvio",
        "cultivar",
        "uso_produttivo",
        "lotto_seme",
        "versione_protocollo",
        "causa_origine",
        "esito_finale",
    ],
)
def test_dati_del_ciclo_immutabili(attribute) -> None:
    semina = build_semina()
    with pytest.raises(FrozenInstanceError):
        setattr(semina, attribute, getattr(semina, attribute))


def test_non_espone_transizioni_non_autorizzate() -> None:
    semina = build_semina()
    for method_name in ("avanza", "cambia_stato", "chiudi", "raccogli"):
        assert not hasattr(semina, method_name)


def test_non_espone_operazioni_di_fusione() -> None:
    semina = build_semina()
    for method_name in ("fondi", "unisci", "merge"):
        assert not hasattr(semina, method_name)


def test_modulo_non_importa_dipendenze_infrastrutturali() -> None:
    module = __import__("src.tpo_core.domain.entities.semina", fromlist=["*"])
    module_names = set(module.__dict__)
    assert "sqlite3" not in module_names
    assert "yaml" not in module_names
    assert "google" not in module_names
