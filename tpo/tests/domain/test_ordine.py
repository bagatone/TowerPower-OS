from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime

import pytest

from src.tpo_core.domain.entities.ordine import Ordine, PrenotazioneOrdine, RigaOrdine
from src.tpo_core.domain.errors import InvalidQuantityError, InvariantViolationError
from src.tpo_core.domain.identifiers import (
    ClienteId,
    OrdineId,
    ProgrammaFornituraId,
    VarietaId,
)
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import OrdineCreationType, OrdineState


def build_riga(**overrides) -> RigaOrdine:
    data = {
        "varieta_id": VarietaId("VAR-000001"),
        "quantita": Quantity(10, UnitOfMeasure.SET),
    }
    data.update(overrides)
    return RigaOrdine(**data)


def build_ordine(**overrides) -> Ordine:
    data = {
        "id": OrdineId("ORD-000001"),
        "cliente_id": ClienteId("CLI-000001"),
        "data_ordine": date(2026, 7, 1),
        "righe": (build_riga(),),
        "stato": OrdineState.APERTO,
        "tipo_creazione": OrdineCreationType.MANUALE,
    }
    data.update(overrides)
    return Ordine(**data)


def test_creazione_valida_manual() -> None:
    ordine = build_ordine()
    assert ordine.id == OrdineId("ORD-000001")
    assert ordine.cliente_id == ClienteId("CLI-000001")
    assert ordine.programma_fornitura_id is None
    assert ordine.tipo_creazione is OrdineCreationType.MANUALE


def test_creazione_valida_da_programma_fornitura() -> None:
    origine = ProgrammaFornituraId("PF-000001")
    ordine = build_ordine(
        tipo_creazione=OrdineCreationType.AUTOMATICO,
        programma_fornitura_id=origine,
    )
    assert ordine.programma_fornitura_id == origine


def test_tipo_creazione_obbligatorio_e_tipizzato() -> None:
    with pytest.raises(TypeError):
        Ordine(
            id=OrdineId("ORD-000001"),
            cliente_id=ClienteId("CLI-000001"),
            data_ordine=date(2026, 7, 1),
            righe=(build_riga(),),
            stato=OrdineState.APERTO,
        )
    with pytest.raises(InvariantViolationError, match="OrdineCreationType"):
        build_ordine(tipo_creazione="MANUALE")


def test_automatico_richiede_programma() -> None:
    with pytest.raises(InvariantViolationError, match="AUTOMATICO"):
        build_ordine(tipo_creazione=OrdineCreationType.AUTOMATICO)


def test_manuale_vieta_programma() -> None:
    with pytest.raises(InvariantViolationError, match="MANUALE"):
        build_ordine(programma_fornitura_id=ProgrammaFornituraId("PF-000001"))


@pytest.mark.parametrize("identifier", [None, "ORD-000001", ClienteId("CLI-000001")])
def test_ordine_id_obbligatorio_e_tipizzato(identifier) -> None:
    with pytest.raises(InvariantViolationError, match="OrdineId"):
        build_ordine(id=identifier)


@pytest.mark.parametrize("cliente_id", [None, "CLI-000001", VarietaId("VAR-000001")])
def test_cliente_id_obbligatorio_e_tipizzato(cliente_id) -> None:
    with pytest.raises(InvariantViolationError, match="ClienteId"):
        build_ordine(cliente_id=cliente_id)


@pytest.mark.parametrize("data_ordine", [None, "2026-07-01", datetime(2026, 7, 1)])
def test_data_ordine_obbligatoria_e_date(data_ordine) -> None:
    with pytest.raises(InvariantViolationError, match="data_ordine"):
        build_ordine(data_ordine=data_ordine)


@pytest.mark.parametrize("righe", [None, (), []])
def test_almeno_una_riga_in_tuple_obbligatoria(righe) -> None:
    with pytest.raises(InvariantViolationError, match="almeno una riga"):
        build_ordine(righe=righe)


def test_righe_devono_essere_value_object_validi() -> None:
    with pytest.raises(InvariantViolationError, match="righe valide"):
        build_ordine(righe=("riga",))


def test_righe_conservate_come_tuple() -> None:
    ordine = build_ordine()
    assert isinstance(ordine.righe, tuple)
    with pytest.raises(TypeError):
        ordine.righe[0] = build_riga()


@pytest.mark.parametrize("stato", [None, "APERTO"])
def test_stato_ufficiale_obbligatorio(stato) -> None:
    with pytest.raises(InvariantViolationError, match="OrdineState"):
        build_ordine(stato=stato)


@pytest.mark.parametrize("origine", ["PF-000001", ClienteId("CLI-000001")])
def test_programma_fornitura_id_tipizzato_quando_presente(origine) -> None:
    with pytest.raises(InvariantViolationError, match="ProgrammaFornituraId"):
        build_ordine(programma_fornitura_id=origine)


def test_identita_determinata_esclusivamente_da_ordine_id() -> None:
    primo = build_ordine()
    secondo = build_ordine(
        cliente_id=ClienteId("CLI-000002"),
        data_ordine=date(2026, 8, 1),
        righe=(build_riga(varieta_id=VarietaId("VAR-000002")),),
        stato=OrdineState.ANNULLATO,
        tipo_creazione=OrdineCreationType.AUTOMATICO,
        programma_fornitura_id=ProgrammaFornituraId("PF-000001"),
    )
    assert primo == secondo
    assert hash(primo) == hash(secondo)


def test_id_differenti_rappresentano_ordini_differenti() -> None:
    assert build_ordine() != build_ordine(id=OrdineId("ORD-000002"))


@pytest.mark.parametrize(
    "attribute",
    [
        "id", "cliente_id", "data_ordine", "righe", "stato",
        "tipo_creazione", "programma_fornitura_id",
    ],
)
def test_ordine_immutabile(attribute) -> None:
    ordine = build_ordine()
    with pytest.raises(FrozenInstanceError):
        setattr(ordine, attribute, getattr(ordine, attribute))


@pytest.mark.parametrize("varieta_id", [None, "VAR-000001", ClienteId("CLI-000001")])
def test_riga_richiede_varieta_id(varieta_id) -> None:
    with pytest.raises(InvariantViolationError, match="VarietaId"):
        build_riga(varieta_id=varieta_id)


@pytest.mark.parametrize("quantita", [None, 1])
def test_riga_richiede_quantity(quantita) -> None:
    with pytest.raises(InvalidQuantityError, match="quantità valida"):
        build_riga(quantita=quantita)


def test_quantita_riga_deve_essere_positiva() -> None:
    with pytest.raises(InvalidQuantityError, match="maggiore di zero"):
        build_riga(quantita=Quantity(0, UnitOfMeasure.SET))


@pytest.mark.parametrize("unit", list(UnitOfMeasure))
def test_riga_ammette_tutte_le_unita_ufficiali(unit) -> None:
    assert build_riga(quantita=Quantity(1, unit)).quantita.unit is unit


def test_riga_immutabile_hashable_e_uguale_per_valore() -> None:
    prima = build_riga()
    seconda = build_riga()
    assert prima == seconda
    assert hash(prima) == hash(seconda)
    with pytest.raises(FrozenInstanceError):
        prima.quantita = Quantity(20, UnitOfMeasure.SET)


def test_riga_non_contiene_responsabilita_estranee() -> None:
    assert [campo.name for campo in fields(RigaOrdine)] == ["varieta_id", "quantita"]


def test_prenotazioni_derivate_una_per_riga() -> None:
    righe = (
        build_riga(),
        build_riga(
            varieta_id=VarietaId("VAR-000002"),
            quantita=Quantity(3, UnitOfMeasure.GRAM),
        ),
    )
    ordine = build_ordine(righe=righe)
    assert ordine.prenotazioni == tuple(
        PrenotazioneOrdine(riga.varieta_id, riga.quantita) for riga in righe
    )


def test_prenotazioni_non_aggregano_righe_identiche() -> None:
    riga = build_riga()
    assert len(build_ordine(righe=(riga, riga)).prenotazioni) == 2


def test_prenotazione_immutabile_senza_identificativo() -> None:
    prenotazione = build_ordine().prenotazioni[0]
    assert [campo.name for campo in fields(PrenotazioneOrdine)] == [
        "varieta_id",
        "quantita",
    ]
    with pytest.raises(FrozenInstanceError):
        prenotazione.quantita = Quantity(1, UnitOfMeasure.SET)


def test_ordine_non_espone_transizioni_o_evasione_automatiche() -> None:
    ordine = build_ordine()
    for nome in (
        "annulla",
        "evadi",
        "consegna",
        "calcola_residuo",
        "aggiorna_stato",
    ):
        assert not hasattr(ordine, nome)


def test_ordine_non_conosce_stock_consegne_o_scheduling_engine() -> None:
    ordine = build_ordine()
    for nome in (
        "stock",
        "disponibile",
        "consegne",
        "genera_consegna",
        "genera_ordini",
        "calcola_ricorrenze",
        "run_id",
    ):
        assert not hasattr(ordine, nome)


def test_modulo_non_importa_dipendenze_infrastrutturali() -> None:
    module = __import__("src.tpo_core.domain.entities.ordine", fromlist=["*"])
    module_names = set(module.__dict__)
    assert "sqlite3" not in module_names
    assert "yaml" not in module_names
    assert "google" not in module_names
    assert "Stock" not in module_names
    assert "ProgrammaFornitura" not in module_names
