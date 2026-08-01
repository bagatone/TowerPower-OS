from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime, timezone

import pytest

from src.tpo_core.domain.entities.consegna import Consegna, RigaConsegna
from src.tpo_core.domain.errors import (
    InvalidQuantityError,
    InvalidTimeReferenceError,
    InvariantViolationError,
)
from src.tpo_core.domain.identifiers import ClienteId, ConsegnaId, OrdineId, VarietaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import ConsegnaState
from src.tpo_core.domain.time_reference import OFFICIAL_TIMEZONE_NAME


def build_riga(**overrides) -> RigaConsegna:
    data = {
        "varieta_id": VarietaId("VAR-000001"),
        "quantita": Quantity(10, UnitOfMeasure.SET),
    }
    data.update(overrides)
    return RigaConsegna(**data)


def build_consegna(**overrides) -> Consegna:
    data = {
        "id": ConsegnaId("CON-000001"),
        "cliente_id": ClienteId("CLI-000001"),
        "ordine_ids": (OrdineId("ORD-000001"),),
        "righe": (build_riga(),),
        "stato": ConsegnaState.PROGRAMMATA,
        "data_prevista": date(2026, 7, 10),
    }
    data.update(overrides)
    return Consegna(**data)


def test_creazione_valida_collegata_a_ordine() -> None:
    consegna = build_consegna()
    assert consegna.id == ConsegnaId("CON-000001")
    assert consegna.ordine_ids == (OrdineId("ORD-000001"),)
    assert consegna.motivazione is None


def test_creazione_valida_con_piu_ordini_e_ordine_preservato() -> None:
    ordine_ids = (OrdineId("ORD-000002"), OrdineId("ORD-000001"))
    consegna = build_consegna(ordine_ids=ordine_ids)
    assert consegna.ordine_ids == ordine_ids


def test_creazione_valida_senza_ordini_con_motivazione() -> None:
    consegna = build_consegna(ordine_ids=(), motivazione="omaggio")
    assert consegna.ordine_ids == ()
    assert consegna.motivazione == "omaggio"


@pytest.mark.parametrize("identifier", [None, "CON-000001", OrdineId("ORD-000001")])
def test_consegna_id_obbligatorio_e_tipizzato(identifier) -> None:
    with pytest.raises(InvariantViolationError, match="ConsegnaId"):
        build_consegna(id=identifier)


@pytest.mark.parametrize("cliente_id", [None, "CLI-000001", VarietaId("VAR-000001")])
def test_cliente_id_obbligatorio_e_tipizzato(cliente_id) -> None:
    with pytest.raises(InvariantViolationError, match="ClienteId"):
        build_consegna(cliente_id=cliente_id)


@pytest.mark.parametrize("ordine_ids", [None, [], [OrdineId("ORD-000001")]])
def test_ordine_ids_deve_essere_tuple(ordine_ids) -> None:
    with pytest.raises(InvariantViolationError, match="tuple"):
        build_consegna(ordine_ids=ordine_ids)


@pytest.mark.parametrize("ordine_id", ["ORD-000001", ClienteId("CLI-000001")])
def test_ogni_ordine_id_deve_essere_tipizzato(ordine_id) -> None:
    with pytest.raises(InvariantViolationError, match="OrdineId"):
        build_consegna(ordine_ids=(ordine_id,))


def test_ordine_ids_duplicati_rifiutati() -> None:
    ordine_id = OrdineId("ORD-000001")
    with pytest.raises(InvariantViolationError, match="duplicati"):
        build_consegna(ordine_ids=(ordine_id, ordine_id))


@pytest.mark.parametrize("motivazione", [None, "", " "])
def test_motivazione_obbligatoria_senza_ordine(motivazione) -> None:
    with pytest.raises(InvariantViolationError, match="motivazione"):
        build_consegna(ordine_ids=(), motivazione=motivazione)


@pytest.mark.parametrize("righe", [None, (), []])
def test_almeno_una_riga_in_tuple_obbligatoria(righe) -> None:
    with pytest.raises(InvariantViolationError, match="almeno una riga"):
        build_consegna(righe=righe)


def test_righe_devono_essere_value_object_validi() -> None:
    with pytest.raises(InvariantViolationError, match="righe valide"):
        build_consegna(righe=("riga",))


def test_righe_conservate_come_tuple() -> None:
    consegna = build_consegna()
    assert isinstance(consegna.righe, tuple)
    with pytest.raises(TypeError):
        consegna.righe[0] = build_riga()


@pytest.mark.parametrize("stato", [None, "PROGRAMMATA", "PARZIALE"])
def test_stato_ufficiale_obbligatorio(stato) -> None:
    with pytest.raises(InvariantViolationError, match="ConsegnaState"):
        build_consegna(stato=stato)


@pytest.mark.parametrize("data_prevista", [None, "2026-07-10", datetime(2026, 7, 10)])
def test_data_prevista_obbligatoria_e_date(data_prevista) -> None:
    with pytest.raises(InvariantViolationError, match="data_prevista"):
        build_consegna(data_prevista=data_prevista)


def test_data_effettiva_facoltativa_per_consegna_programmata() -> None:
    assert build_consegna(data_effettiva=None).data_effettiva is None


def test_data_effettiva_naive_rifiutata() -> None:
    with pytest.raises(InvalidTimeReferenceError, match="fuso orario"):
        build_consegna(data_effettiva=datetime(2026, 7, 10, 12))


def test_data_effettiva_normalizzata_in_atlantic_canary() -> None:
    consegna = build_consegna(
        stato=ConsegnaState.CONSEGNATA,
        data_effettiva=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
    )
    assert consegna.data_effettiva is not None
    assert getattr(consegna.data_effettiva.tzinfo, "key", None) == OFFICIAL_TIMEZONE_NAME


def test_identita_determinata_esclusivamente_da_consegna_id() -> None:
    prima = build_consegna()
    seconda = build_consegna(
        cliente_id=ClienteId("CLI-000002"),
        ordine_ids=(),
        motivazione="campione",
        righe=(build_riga(varieta_id=VarietaId("VAR-000002")),),
        stato=ConsegnaState.CONSEGNATA,
        data_prevista=date(2026, 8, 1),
        data_effettiva=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert prima == seconda
    assert hash(prima) == hash(seconda)


def test_id_differenti_rappresentano_consegne_differenti() -> None:
    assert build_consegna() != build_consegna(id=ConsegnaId("CON-000002"))


@pytest.mark.parametrize(
    "attribute",
    [
        "id",
        "cliente_id",
        "ordine_ids",
        "righe",
        "stato",
        "data_prevista",
        "data_effettiva",
        "motivazione",
    ],
)
def test_consegna_immutabile(attribute) -> None:
    consegna = build_consegna()
    with pytest.raises(FrozenInstanceError):
        setattr(consegna, attribute, getattr(consegna, attribute))


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


def test_riga_contiene_esclusivamente_i_campi_autorizzati() -> None:
    assert [campo.name for campo in fields(RigaConsegna)] == ["varieta_id", "quantita"]


def test_consegna_riferisce_ordini_senza_incorporarli() -> None:
    consegna = build_consegna()
    assert all(isinstance(ordine_id, OrdineId) for ordine_id in consegna.ordine_ids)
    assert not hasattr(consegna, "ordine_id")
    assert not hasattr(consegna, "ordine")
    assert not hasattr(consegna, "riga_ordine_index")


def test_ordine_ids_immutabile() -> None:
    consegna = build_consegna()
    with pytest.raises(TypeError):
        consegna.ordine_ids[0] = OrdineId("ORD-000002")


def test_non_espone_transizioni_o_logica_di_evasione() -> None:
    consegna = build_consegna()
    for nome in ("prepara", "consegna", "annulla", "evadi_ordine", "calcola_residuo"):
        assert not hasattr(consegna, nome)


def test_non_modifica_stock_movimenti_ordini_o_prenotazioni() -> None:
    consegna = build_consegna()
    for nome in (
        "stock",
        "aggiorna_stock",
        "genera_movimento",
        "crea_scarico",
        "aggiorna_ordine",
        "prenotazioni",
    ):
        assert not hasattr(consegna, nome)


def test_non_contiene_responsabilita_amministrative() -> None:
    consegna = build_consegna()
    for nome in ("fattura", "prezzo", "imposta", "pagamento", "iban"):
        assert not hasattr(consegna, nome)


def test_non_conosce_programmi_semine_o_raccolte() -> None:
    consegna = build_consegna()
    for nome in ("programma_fornitura_id", "semina_id", "raccolta_id"):
        assert not hasattr(consegna, nome)


def test_modulo_non_importa_dipendenze_infrastrutturali() -> None:
    module = __import__("src.tpo_core.domain.entities.consegna", fromlist=["*"])
    module_names = set(module.__dict__)
    assert "sqlite3" not in module_names
    assert "yaml" not in module_names
    assert "google" not in module_names
    assert "Stock" not in module_names
    assert "MovimentoMagazzino" not in module_names
    assert "Ordine" not in module_names
