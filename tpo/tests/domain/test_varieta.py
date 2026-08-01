from dataclasses import FrozenInstanceError

import pytest

from src.tpo_core.domain.entities.varieta import Varieta
from src.tpo_core.domain.errors import InvariantViolationError
from src.tpo_core.domain.identifiers import SeminaId, VarietaId
from src.tpo_core.domain.states import VarietaState


def build_varieta(**overrides) -> Varieta:
    data = {
        "id": VarietaId("VAR-000001"),
        "denominazione": "Basilico",
        "stato": VarietaState.ATTIVA,
    }
    data.update(overrides)
    return Varieta(**data)


def test_creazione_valida() -> None:
    varieta = build_varieta()
    assert varieta.id == VarietaId("VAR-000001")
    assert varieta.denominazione == "Basilico"
    assert varieta.stato is VarietaState.ATTIVA


@pytest.mark.parametrize("identifier", [None, "VAR-000001", SeminaId("SEM-000001")])
def test_varieta_id_obbligatorio_e_tipizzato(identifier) -> None:
    with pytest.raises(InvariantViolationError, match="VarietaId"):
        build_varieta(id=identifier)


@pytest.mark.parametrize("denominazione", [None, "", " ", "\t\n"])
def test_denominazione_obbligatoria(denominazione) -> None:
    with pytest.raises(InvariantViolationError, match="denominazione ufficiale"):
        build_varieta(denominazione=denominazione)


def test_denominazione_viene_conservata_senza_normalizzazione_ambigua() -> None:
    varieta = build_varieta(denominazione="  Basilico Genovese  ")
    assert varieta.denominazione == "  Basilico Genovese  "


@pytest.mark.parametrize("stato", [None, "ATTIVA", "ARCHIVIATA"])
def test_stato_obbligatorio_e_ufficiale(stato) -> None:
    with pytest.raises(InvariantViolationError, match="stato ufficiale"):
        build_varieta(stato=stato)


def test_identita_determinata_esclusivamente_da_varieta_id() -> None:
    prima = build_varieta(denominazione="Basilico", stato=VarietaState.ATTIVA)
    seconda = build_varieta(
        denominazione="Denominazione storica differente",
        stato=VarietaState.SOSPESA,
    )
    assert prima == seconda
    assert hash(prima) == hash(seconda)


def test_nomi_uguali_con_id_diversi_rappresentano_entita_differenti() -> None:
    prima = build_varieta(id=VarietaId("VAR-000001"), denominazione="Basilico")
    seconda = build_varieta(id=VarietaId("VAR-000002"), denominazione="Basilico")
    assert prima != seconda


def test_confronto_con_tipo_differente_non_rappresenta_la_stessa_entita() -> None:
    assert build_varieta() != VarietaId("VAR-000001")


@pytest.mark.parametrize("attribute", ["id", "denominazione", "stato"])
def test_attributi_immutabili(attribute) -> None:
    varieta = build_varieta()
    with pytest.raises(FrozenInstanceError):
        setattr(varieta, attribute, getattr(varieta, attribute))


def test_sono_disponibili_esclusivamente_gli_stati_congelati() -> None:
    assert [state.value for state in VarietaState] == [
        "ATTIVA",
        "IN_SPERIMENTAZIONE",
        "SOSPESA",
        "DISMESSA",
    ]


def test_entita_non_espone_transizioni_non_definite_dal_register() -> None:
    varieta = build_varieta()
    assert not hasattr(varieta, "attiva")
    assert not hasattr(varieta, "sospendi")
    assert not hasattr(varieta, "dismetti")
    assert not hasattr(varieta, "aggiorna_denominazione")


def test_modulo_non_importa_dipendenze_infrastrutturali() -> None:
    module_names = set(__import__("src.tpo_core.domain.entities.varieta", fromlist=["*"]).__dict__)
    assert "sqlite3" not in module_names
    assert "yaml" not in module_names
    assert "google" not in module_names
