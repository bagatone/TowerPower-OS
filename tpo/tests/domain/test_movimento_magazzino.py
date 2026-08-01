from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.tpo_core.domain.entities.movimento_magazzino import MovimentoMagazzino
from src.tpo_core.domain.errors import (
    InvalidQuantityError,
    InvalidTimeReferenceError,
    InvariantViolationError,
)
from src.tpo_core.domain.identifiers import MovimentoId, SeminaId, VarietaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import MovimentoDirection, MovimentoType
from src.tpo_core.domain.time_reference import OFFICIAL_TIMEZONE_NAME


def build_movimento(**overrides) -> MovimentoMagazzino:
    data = {
        "id": MovimentoId("MOV-000001"),
        "varieta_id": VarietaId("VAR-000001"),
        "tipo": MovimentoType.CARICO,
        "direzione": MovimentoDirection.POSITIVO,
        "quantita": Quantity(Decimal("12"), UnitOfMeasure.SET),
        "data_movimento": datetime(2026, 7, 10, 8, 30, tzinfo=timezone.utc),
        "motivo": "Prodotto reso disponibile",
        "origine": "RACCOLTA",
    }
    data.update(overrides)
    return MovimentoMagazzino(**data)


def test_creazione_valida() -> None:
    movimento = build_movimento()
    assert movimento.id == MovimentoId("MOV-000001")
    assert movimento.varieta_id == VarietaId("VAR-000001")
    assert movimento.tipo is MovimentoType.CARICO
    assert movimento.direzione is MovimentoDirection.POSITIVO
    assert movimento.quantita == Quantity(12, UnitOfMeasure.SET)


@pytest.mark.parametrize("identifier", [None, "MOV-000001", VarietaId("VAR-000001")])
def test_movimento_id_obbligatorio_e_tipizzato(identifier) -> None:
    with pytest.raises(InvariantViolationError, match="MovimentoId"):
        build_movimento(id=identifier)


@pytest.mark.parametrize("varieta_id", [None, "VAR-000001", SeminaId("SEM-000001")])
def test_varieta_id_obbligatorio_e_tipizzato(varieta_id) -> None:
    with pytest.raises(InvariantViolationError, match="VarietaId"):
        build_movimento(varieta_id=varieta_id)


@pytest.mark.parametrize("tipo", [None, "CARICO", "USCITA_PRODUZIONE"])
def test_tipo_obbligatorio_e_ufficiale(tipo) -> None:
    with pytest.raises(InvariantViolationError, match="MovimentoType"):
        build_movimento(tipo=tipo)


@pytest.mark.parametrize("direzione", [None, "POSITIVO", "+"])
def test_direzione_obbligatoria_e_ufficiale(direzione) -> None:
    with pytest.raises(InvariantViolationError, match="MovimentoDirection"):
        build_movimento(direzione=direzione)


@pytest.mark.parametrize("quantita", [None, Decimal("1")])
def test_quantita_obbligatoria(quantita) -> None:
    with pytest.raises(InvalidQuantityError, match="quantità valida"):
        build_movimento(quantita=quantita)


def test_quantita_deve_essere_maggiore_di_zero() -> None:
    with pytest.raises(InvalidQuantityError, match="maggiore di zero"):
        build_movimento(quantita=Quantity(0, UnitOfMeasure.SET))


def test_quantita_negativa_rifiutata_da_quantity() -> None:
    with pytest.raises(InvalidQuantityError, match="negativa"):
        Quantity(-1, UnitOfMeasure.SET)


@pytest.mark.parametrize("unit", list(UnitOfMeasure))
def test_conserva_ogni_unita_ufficiale_esistente(unit) -> None:
    movimento = build_movimento(quantita=Quantity(1, unit))
    assert movimento.quantita.unit is unit


def test_data_movimento_obbligatoria() -> None:
    with pytest.raises(InvalidTimeReferenceError, match="datetime"):
        build_movimento(data_movimento=None)


def test_datetime_naive_rifiutato() -> None:
    with pytest.raises(InvalidTimeReferenceError, match="fuso orario"):
        build_movimento(data_movimento=datetime(2026, 7, 10, 8, 30))


def test_data_movimento_normalizzata_in_atlantic_canary() -> None:
    movimento = build_movimento()
    assert movimento.data_movimento.tzinfo is not None
    assert getattr(movimento.data_movimento.tzinfo, "key", None) == OFFICIAL_TIMEZONE_NAME


@pytest.mark.parametrize("motivo", [None, "", " "])
def test_motivo_obbligatorio_e_non_vuoto(motivo) -> None:
    with pytest.raises(InvariantViolationError, match="motivo"):
        build_movimento(motivo=motivo)


@pytest.mark.parametrize("origine", [None, "", " "])
def test_origine_obbligatoria_e_non_vuota(origine) -> None:
    with pytest.raises(InvariantViolationError, match="origine"):
        build_movimento(origine=origine)


def test_origine_non_e_un_tipo_di_movimento() -> None:
    movimento = build_movimento(tipo=MovimentoType.CARICO, origine="RACCOLTA")
    assert movimento.tipo is MovimentoType.CARICO
    assert movimento.origine == "RACCOLTA"


def test_identita_determinata_esclusivamente_da_movimento_id() -> None:
    primo = build_movimento()
    secondo = build_movimento(
        varieta_id=VarietaId("VAR-000002"),
        tipo=MovimentoType.RETTIFICA,
        direzione=MovimentoDirection.NEGATIVO,
        quantita=Quantity(3, UnitOfMeasure.GRAM),
        data_movimento=datetime(2026, 7, 11, 12, tzinfo=timezone.utc),
        motivo="Motivo differente",
        origine="altro evento autorizzato",
    )
    assert primo == secondo
    assert hash(primo) == hash(secondo)


def test_id_differenti_rappresentano_eventi_differenti() -> None:
    assert build_movimento() != build_movimento(id=MovimentoId("MOV-000002"))


@pytest.mark.parametrize(
    "attribute",
    [
        "id",
        "varieta_id",
        "tipo",
        "direzione",
        "quantita",
        "data_movimento",
        "motivo",
        "origine",
    ],
)
def test_attributi_immutabili(attribute) -> None:
    movimento = build_movimento()
    with pytest.raises(FrozenInstanceError):
        setattr(movimento, attribute, getattr(movimento, attribute))


@pytest.mark.parametrize("direzione", list(MovimentoDirection))
def test_rettifica_ammette_entrambi_i_versi(direzione) -> None:
    movimento = build_movimento(tipo=MovimentoType.RETTIFICA, direzione=direzione)
    assert movimento.direzione is direzione


def test_non_espone_metodi_di_modifica_o_correzione() -> None:
    movimento = build_movimento()
    for method_name in ("aggiorna", "correggi", "modifica", "annulla", "elimina"):
        assert not hasattr(movimento, method_name)


def test_non_applica_effetti_sullo_stock() -> None:
    movimento = build_movimento()
    for method_name in ("applica", "modifica_stock", "calcola_saldo", "verifica_saldo"):
        assert not hasattr(movimento, method_name)


def test_non_mantiene_relazione_diretta_con_semina() -> None:
    movimento = build_movimento()
    assert not hasattr(movimento, "semina_id")
    assert not hasattr(movimento, "semina")


def test_vecchi_tipi_legacy_sono_esclusi() -> None:
    assert [tipo.value for tipo in MovimentoType] == ["CARICO", "SCARICO", "RETTIFICA"]
    assert not hasattr(MovimentoType, "USCITA_PRODUZIONE")


def test_modulo_non_importa_dipendenze_infrastrutturali() -> None:
    module = __import__(
        "src.tpo_core.domain.entities.movimento_magazzino",
        fromlist=["*"],
    )
    module_names = set(module.__dict__)
    assert "sqlite3" not in module_names
    assert "yaml" not in module_names
    assert "google" not in module_names
    assert "Stock" not in module_names
