from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime, time

import pytest

from src.tpo_core.domain.entities.programma_fornitura import (
    ConfigurazioneTemporale,
    ProgrammaFornitura,
    RigaProgrammaFornitura,
    TipoRicorrenza,
)
from src.tpo_core.domain.errors import InvalidQuantityError, InvariantViolationError
from src.tpo_core.domain.identifiers import (
    ClienteId,
    ProgrammaFornituraId,
    VarietaId,
)
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import ProgrammaFornituraState


def configurazione_settimanale() -> ConfigurazioneTemporale:
    return ConfigurazioneTemporale(TipoRicorrenza.SETTIMANALE)


def build_riga(**overrides) -> RigaProgrammaFornitura:
    data = {
        "varieta_id": VarietaId("VAR-000001"),
        "quantita": Quantity(10, UnitOfMeasure.SET),
        "configurazione_temporale": configurazione_settimanale(),
    }
    data.update(overrides)
    return RigaProgrammaFornitura(**data)


def build_programma(**overrides) -> ProgrammaFornitura:
    data = {
        "id": ProgrammaFornituraId("PF-000001"),
        "cliente_id": ClienteId("CLI-000001"),
        "righe": (build_riga(),),
        "data_inizio": date(2026, 7, 1),
        "stato": ProgrammaFornituraState.ATTIVO,
        "finestra_operativa_giorni": 2,
    }
    data.update(overrides)
    return ProgrammaFornitura(**data)


def test_creazione_programma_valida() -> None:
    programma = build_programma()
    assert programma.id == ProgrammaFornituraId("PF-000001")
    assert programma.cliente_id == ClienteId("CLI-000001")
    assert programma.orario_generazione == time(5, 0)


@pytest.mark.parametrize("identifier", [None, "PF-000001", ClienteId("CLI-000001")])
def test_programma_id_obbligatorio_e_tipizzato(identifier) -> None:
    with pytest.raises(InvariantViolationError, match="ProgrammaFornituraId"):
        build_programma(id=identifier)


@pytest.mark.parametrize("cliente_id", [None, "CLI-000001", VarietaId("VAR-000001")])
def test_cliente_id_obbligatorio_e_tipizzato(cliente_id) -> None:
    with pytest.raises(InvariantViolationError, match="ClienteId"):
        build_programma(cliente_id=cliente_id)


@pytest.mark.parametrize("righe", [(), [], None])
def test_almeno_una_riga_in_tuple_obbligatoria(righe) -> None:
    with pytest.raises(InvariantViolationError, match="almeno una riga"):
        build_programma(righe=righe)


def test_righe_devono_essere_value_object_validi() -> None:
    with pytest.raises(InvariantViolationError, match="righe valide"):
        build_programma(righe=("riga",))


def test_righe_sono_una_tuple_immutabile() -> None:
    programma = build_programma()
    assert isinstance(programma.righe, tuple)
    with pytest.raises(TypeError):
        programma.righe[0] = build_riga()


@pytest.mark.parametrize("data_inizio", [None, "2026-07-01", datetime(2026, 7, 1)])
def test_data_inizio_obbligatoria_e_date(data_inizio) -> None:
    with pytest.raises(InvariantViolationError, match="data_inizio"):
        build_programma(data_inizio=data_inizio)


def test_data_fine_facoltativa() -> None:
    assert build_programma(data_fine=None).data_fine is None


def test_data_fine_precedente_rifiutata() -> None:
    with pytest.raises(InvariantViolationError, match="precedere"):
        build_programma(data_fine=date(2026, 6, 30))


@pytest.mark.parametrize("stato", [None, "ATTIVO"])
def test_stato_ufficiale_obbligatorio(stato) -> None:
    with pytest.raises(InvariantViolationError, match="stato ufficiale"):
        build_programma(stato=stato)


def test_orario_generazione_personalizzato() -> None:
    assert build_programma(orario_generazione=time(6, 15)).orario_generazione == time(6, 15)


def test_orario_generazione_deve_essere_time() -> None:
    with pytest.raises(InvariantViolationError, match="time"):
        build_programma(orario_generazione="05:00")


@pytest.mark.parametrize("finestra", [-1, 1.5, True])
def test_finestra_operativa_non_negativa(finestra) -> None:
    with pytest.raises(InvariantViolationError, match="non negativo"):
        build_programma(finestra_operativa_giorni=finestra)


def test_identita_programma_basata_esclusivamente_sull_id() -> None:
    primo = build_programma()
    secondo = build_programma(
        cliente_id=ClienteId("CLI-000002"),
        righe=(build_riga(varieta_id=VarietaId("VAR-000002")),),
        data_inizio=date(2027, 1, 1),
        stato=ProgrammaFornituraState.TERMINATO,
        finestra_operativa_giorni=10,
    )
    assert primo == secondo
    assert hash(primo) == hash(secondo)


def test_id_programma_differenti_rappresentano_accordi_differenti() -> None:
    assert build_programma() != build_programma(
        id=ProgrammaFornituraId("PF-000002")
    )


@pytest.mark.parametrize(
    "attribute",
    [
        "id",
        "cliente_id",
        "righe",
        "data_inizio",
        "stato",
        "finestra_operativa_giorni",
        "data_fine",
        "orario_generazione",
    ],
)
def test_programma_immutabile(attribute) -> None:
    programma = build_programma()
    with pytest.raises(FrozenInstanceError):
        setattr(programma, attribute, getattr(programma, attribute))


def test_programma_non_espone_transizioni_non_storicizzate() -> None:
    programma = build_programma(stato=ProgrammaFornituraState.TERMINATO)
    for metodo in ("sospendi", "riattiva", "termina", "cambia_stato"):
        assert not hasattr(programma, metodo)


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


def test_riga_richiede_configurazione_temporale() -> None:
    with pytest.raises(InvariantViolationError, match="ConfigurazioneTemporale"):
        build_riga(configurazione_temporale=None)


@pytest.mark.parametrize("tipo", list(TipoRicorrenza))
def test_tutti_i_tipi_di_ricorrenza_approvati(tipo) -> None:
    kwargs = {}
    if tipo is TipoRicorrenza.OGNI_X_GIORNI:
        kwargs["intervallo_giorni"] = 3
    if tipo is TipoRicorrenza.GIORNI_SETTIMANA:
        kwargs["giorni_settimana"] = (1, 3, 5)
    configurazione = ConfigurazioneTemporale(tipo, **kwargs)
    assert configurazione.tipo is tipo


@pytest.mark.parametrize("intervallo", [None, 0, -1, 1.5, True])
def test_ogni_x_giorni_richiede_intero_positivo(intervallo) -> None:
    with pytest.raises(InvariantViolationError, match="intero positivo"):
        ConfigurazioneTemporale(
            TipoRicorrenza.OGNI_X_GIORNI,
            intervallo_giorni=intervallo,
        )


def test_intervallo_vietato_per_altri_tipi() -> None:
    with pytest.raises(InvariantViolationError, match="esclusivamente"):
        ConfigurazioneTemporale(
            TipoRicorrenza.SETTIMANALE,
            intervallo_giorni=7,
        )


def test_giorni_settimana_richiede_almeno_un_giorno() -> None:
    with pytest.raises(InvariantViolationError, match="almeno un giorno"):
        ConfigurazioneTemporale(TipoRicorrenza.GIORNI_SETTIMANA)


@pytest.mark.parametrize("giorni", [(1, 1), (0,), (8,), (True,), [1, 2]])
def test_giorni_settimana_validi_unici_e_in_tuple(giorni) -> None:
    with pytest.raises(InvariantViolationError):
        ConfigurazioneTemporale(
            TipoRicorrenza.GIORNI_SETTIMANA,
            giorni_settimana=giorni,
        )


def test_giorni_vietati_per_altri_tipi() -> None:
    with pytest.raises(InvariantViolationError, match="esclusivamente"):
        ConfigurazioneTemporale(
            TipoRicorrenza.MENSILE,
            giorni_settimana=(1,),
        )


def test_configurazione_e_riga_sono_immutabili_e_hashable() -> None:
    configurazione = configurazione_settimanale()
    riga = build_riga(configurazione_temporale=configurazione)
    assert hash(configurazione)
    assert hash(riga)
    with pytest.raises(FrozenInstanceError):
        riga.quantita = Quantity(20, UnitOfMeasure.SET)


def test_righe_uguali_per_valore() -> None:
    assert build_riga() == build_riga()


def test_righe_con_frequenze_e_varieta_differenti_sono_ammesse() -> None:
    righe = (
        build_riga(),
        build_riga(
            varieta_id=VarietaId("VAR-000002"),
            configurazione_temporale=ConfigurazioneTemporale(
                TipoRicorrenza.MENSILE
            ),
        ),
    )
    assert build_programma(righe=righe).righe == righe


def test_riga_non_contiene_responsabilita_estranee() -> None:
    assert [campo.name for campo in fields(RigaProgrammaFornitura)] == [
        "varieta_id",
        "quantita",
        "configurazione_temporale",
    ]


def test_programma_non_genera_ordini_ne_conosce_altri_register() -> None:
    programma = build_programma()
    for nome in (
        "genera_ordini",
        "ordini",
        "stock",
        "semine",
        "raccolte",
        "consegne",
        "fatture",
    ):
        assert not hasattr(programma, nome)


def test_modulo_non_importa_dipendenze_infrastrutturali() -> None:
    module = __import__(
        "src.tpo_core.domain.entities.programma_fornitura",
        fromlist=["*"],
    )
    module_names = set(module.__dict__)
    assert "sqlite3" not in module_names
    assert "yaml" not in module_names
    assert "google" not in module_names
    assert "Stock" not in module_names
