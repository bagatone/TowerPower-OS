from dataclasses import FrozenInstanceError
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.scheduling.engine import SchedulingEngine
from src.tpo_core.application.scheduling.models import (
    ScheduledOrderRecord,
    SchedulingRequest,
)
from src.tpo_core.application.scheduling.provenance import (
    VersionedProgramLine,
    VersionedProgrammaFornitura,
)
from src.tpo_core.domain.entities.ordine import RigaOrdine
from src.tpo_core.domain.errors import InvariantViolationError
from src.tpo_core.domain.entities.programma_fornitura import (
    ConfigurazioneTemporale,
    ProgrammaFornitura,
    RigaProgrammaFornitura,
    TipoRicorrenza,
)
from src.tpo_core.domain.identifiers import (
    ClienteId,
    OrdineId,
    ProgrammaFornituraId,
    RunId,
    VarietaId,
)
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import OrdineState, ProgrammaFornituraState, RunState
from src.tpo_core.domain.time_reference import CurrentSystemDate


TZ = ZoneInfo("Atlantic/Canary")


class FakeIdGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def next_id(self, identifier_type):
        self.calls += 1
        return identifier_type(f"ORD-{self.calls:06d}")


def config(tipo=TipoRicorrenza.SETTIMANALE, **kwargs):
    return ConfigurazioneTemporale(tipo, **kwargs)


def riga(
    varieta="VAR-000001",
    quantita=10,
    configurazione=None,
    unita=UnitOfMeasure.SET,
):
    return RigaProgrammaFornitura(
        VarietaId(varieta),
        Quantity(quantita, unita),
        configurazione or config(),
    )


def programma(**overrides):
    values = {
        "id": ProgrammaFornituraId("PF-000001"),
        "cliente_id": ClienteId("CLI-000001"),
        "righe": (riga(),),
        "data_inizio": date(2026, 7, 6),
        "stato": ProgrammaFornituraState.ATTIVO,
        "finestra_operativa_giorni": 0,
        "orario_generazione": time(5),
    }
    values.update(overrides)
    return ProgrammaFornitura(**values)


def versioned(item, version=3, positions=None):
    positions = positions or tuple(range(1, len(item.righe) + 1))
    return VersionedProgrammaFornitura(
        programma=item,
        version=version,
        lines=tuple(
            VersionedProgramLine(position, line)
            for position, line in zip(positions, item.righe, strict=True)
        ),
    )


def request(giorno=date(2026, 7, 6), ora=time(5), **overrides):
    values = {
        "run_id": RunId("RUN-000001"),
        "current_system_date": CurrentSystemDate(
            datetime.combine(giorno, ora, tzinfo=TZ)
        ),
        "programmi": (versioned(programma()),),
        "id_generator": FakeIdGenerator(),
    }
    values.update(overrides)
    values["programmi"] = tuple(
        versioned(item) if isinstance(item, ProgrammaFornitura) else item
        for item in values["programmi"]
    )
    return SchedulingRequest(**values)


def execute(**kwargs):
    return SchedulingEngine().execute(request(**kwargs))


def test_nessun_programma() -> None:
    result = execute(programmi=())
    assert result.ordini_generati == ()
    assert result.programmi_letti == 0
    assert result.run_id == RunId("RUN-000001")


def test_programma_attivo_genera_ordine_corretto() -> None:
    result = execute()
    record = result.ordini_generati[0]
    assert record.ordine.id == OrdineId("ORD-000001")
    assert record.ordine.cliente_id == ClienteId("CLI-000001")
    assert record.ordine.programma_fornitura_id == ProgrammaFornituraId("PF-000001")
    assert record.ordine.data_ordine == date(2026, 7, 6)
    assert record.ordine.stato is OrdineState.APERTO
    assert record.data_consegna_prevista == date(2026, 7, 6)
    assert record.ordine.prenotazioni[0].quantita == Quantity(10, UnitOfMeasure.SET)
    assert record.provenance[0].programma_fornitura_id == ProgrammaFornituraId("PF-000001")
    assert record.provenance[0].programma_version == 3
    assert record.provenance[0].programma_line_position == 1
    assert record.provenance[0].order_line_position == 1
    assert not hasattr(record, "run_id")


def test_versione_e_posizione_provengono_dallo_snapshot_versionato() -> None:
    wrapped = versioned(programma(), version=3, positions=(7,))
    record = execute(programmi=(wrapped,)).ordini_generati[0]
    assert (
        record.provenance[0].programma_version,
        record.provenance[0].programma_line_position,
    ) == (3, 7)


def test_stesso_programma_due_versioni_restano_distinguibili() -> None:
    item = programma()
    first = execute(programmi=(versioned(item, version=3),)).ordini_generati[0]
    second = execute(programmi=(versioned(item, version=4),)).ordini_generati[0]
    assert first.provenance[0].programma_version == 3
    assert second.provenance[0].programma_version == 4


def test_input_non_versionato_rifiutato_prima_dello_scheduling() -> None:
    with pytest.raises(InvariantViolationError, match="versionati"):
        SchedulingRequest(
            run_id=RunId("RUN-000001"),
            current_system_date=CurrentSystemDate(
                datetime(2026, 8, 3, 5, tzinfo=TZ)
            ),
            programmi=(programma(),),
            id_generator=FakeIdGenerator(),
        )


def test_engine_non_contiene_default_o_fallback_di_versione() -> None:
    from pathlib import Path

    source = Path("src/tpo_core/application/scheduling/engine.py").read_text()
    assert "programma_version=1" not in source
    assert "programma_version = 1" not in source


@pytest.mark.parametrize(
    "stato",
    [ProgrammaFornituraState.SOSPESO, ProgrammaFornituraState.TERMINATO],
)
def test_programmi_non_attivi_ignorati(stato) -> None:
    assert execute(programmi=(programma(stato=stato),)).ordini_generati == ()


def test_programma_prima_della_data_inizio_ignorato() -> None:
    assert execute(giorno=date(2026, 7, 5)).ordini_generati == ()


def test_programma_dopo_data_fine_ignorato() -> None:
    p = programma(data_fine=date(2026, 7, 6))
    assert execute(giorno=date(2026, 7, 7), programmi=(p,)).ordini_generati == ()


@pytest.mark.parametrize(
    ("tipo", "giorno", "dovuta"),
    [
        (TipoRicorrenza.SETTIMANALE, date(2026, 7, 13), True),
        (TipoRicorrenza.SETTIMANALE, date(2026, 7, 12), False),
        (TipoRicorrenza.QUINDICINALE, date(2026, 7, 20), False),
        (TipoRicorrenza.QUINDICINALE, date(2026, 7, 21), True),
        (TipoRicorrenza.QUINDICINALE, date(2026, 8, 5), True),
        (TipoRicorrenza.MENSILE, date(2026, 8, 6), True),
        (TipoRicorrenza.MENSILE, date(2026, 8, 7), False),
    ],
)
def test_ricorrenze_ancorate(tipo, giorno, dovuta) -> None:
    p = programma(righe=(riga(configurazione=config(tipo)),))
    assert bool(execute(giorno=giorno, programmi=(p,)).ordini_generati) is dovuta


@pytest.mark.parametrize(
    ("giorno", "dovuta"),
    [(date(2026, 7, 6), True), (date(2026, 8, 3), False)],
)
def test_quindicinale_giorno_zero_e_giorno_28(giorno, dovuta) -> None:
    p = programma(righe=(riga(configurazione=config(TipoRicorrenza.QUINDICINALE)),))
    assert bool(execute(giorno=giorno, programmi=(p,)).ordini_generati) is dovuta


def test_mensile_non_corregge_il_giorno_nei_mesi_corti() -> None:
    p = programma(
        data_inizio=date(2026, 1, 31),
        righe=(riga(configurazione=config(TipoRicorrenza.MENSILE)),),
    )
    assert execute(giorno=date(2026, 2, 28), programmi=(p,)).ordini_generati == ()


@pytest.mark.parametrize(("giorno", "dovuta"), [(date(2026, 7, 16), True), (date(2026, 7, 15), False)])
def test_ogni_x_giorni(giorno, dovuta) -> None:
    p = programma(righe=(riga(configurazione=config(TipoRicorrenza.OGNI_X_GIORNI, intervallo_giorni=5)),))
    assert bool(execute(giorno=giorno, programmi=(p,)).ordini_generati) is dovuta


@pytest.mark.parametrize(("giorno", "dovuta"), [(date(2026, 7, 8), True), (date(2026, 7, 9), False)])
def test_giorni_settimana(giorno, dovuta) -> None:
    p = programma(righe=(riga(configurazione=config(TipoRicorrenza.GIORNI_SETTIMANA, giorni_settimana=(1, 3))),))
    assert bool(execute(giorno=giorno, programmi=(p,)).ordini_generati) is dovuta


def test_finestra_positiva_genera_nel_giorno_esatto() -> None:
    p = programma(finestra_operativa_giorni=3)
    result = execute(giorno=date(2026, 7, 6), programmi=(p,))
    assert result.ordini_generati[0].data_consegna_prevista == date(2026, 7, 6)


def test_recupera_occorrenza_scaduta_ma_consegna_ancora_operativa() -> None:
    p = programma(data_inizio=date(2026, 7, 2), finestra_operativa_giorni=3)
    result = execute(giorno=date(2026, 7, 7), programmi=(p,))
    assert result.ordini_generati[0].data_consegna_prevista == date(2026, 7, 9)


def test_non_recupera_occorrenza_con_consegna_gia_passata() -> None:
    p = programma(data_inizio=date(2026, 7, 2), finestra_operativa_giorni=3)
    result = execute(giorno=date(2026, 7, 10), programmi=(p,))
    assert all(
        record.data_consegna_prevista >= date(2026, 7, 10)
        for record in result.ordini_generati
    )
    assert date(2026, 7, 9) not in {
        record.data_consegna_prevista for record in result.ordini_generati
    }


def test_recupera_consegna_odierna_dopo_orario() -> None:
    p = programma(data_inizio=date(2026, 7, 2), finestra_operativa_giorni=3)
    result = execute(giorno=date(2026, 7, 9), ora=time(12), programmi=(p,))
    assert result.ordini_generati[0].data_consegna_prevista == date(2026, 7, 9)


def test_non_genera_prima_del_giorno_dovuto() -> None:
    p = programma(data_inizio=date(2026, 7, 9), finestra_operativa_giorni=3)
    assert execute(giorno=date(2026, 7, 5), programmi=(p,)).ordini_generati == ()


def test_non_genera_prima_dell_orario() -> None:
    assert execute(ora=time(4, 59)).ordini_generati == ()


def test_genera_dopo_orario_nello_stesso_giorno() -> None:
    assert len(execute(ora=time(12)).ordini_generati) == 1


def test_rispetta_orario_personalizzato() -> None:
    p = programma(orario_generazione=time(8))
    assert execute(ora=time(7), programmi=(p,)).ordini_generati == ()
    assert len(execute(ora=time(8), programmi=(p,)).ordini_generati) == 1


def test_piu_righe_stessa_data_raggruppate_e_ordine_preservato() -> None:
    p = programma(righe=(riga("VAR-000002"), riga("VAR-000001")))
    righe = execute(programmi=(p,)).ordini_generati[0].ordine.righe
    assert tuple(x.varieta_id.value for x in righe) == ("VAR-000002", "VAR-000001")


def test_programmi_distinti_dello_stesso_cliente_non_sono_raggruppati() -> None:
    primo = programma()
    secondo = programma(id=ProgrammaFornituraId("PF-000002"))
    result = execute(programmi=(primo, secondo))
    assert len(result.ordini_generati) == 2


def test_frequenze_diverse_generano_date_distinte() -> None:
    p = programma(
        finestra_operativa_giorni=1,
        righe=(
            riga("VAR-000001"),
            riga("VAR-000002", configurazione=config(TipoRicorrenza.GIORNI_SETTIMANA, giorni_settimana=(2,))),
        ),
    )
    result = execute(programmi=(p,))
    assert tuple(r.data_consegna_prevista for r in result.ordini_generati) == (
        date(2026, 7, 6), date(2026, 7, 7)
    )


def test_idempotenza_salva_e_confronta_record_applicativo() -> None:
    first = execute().ordini_generati[0]
    result = execute(ordini_esistenti=(first,))
    assert result.ordini_generati == ()
    assert result.occorrenze_saltate_per_idempotenza == 1


def test_chiave_stabile_e_non_dipende_da_ordine_id() -> None:
    first = execute().ordini_generati[0]
    other_generator = FakeIdGenerator()
    other_generator.calls = 99
    second = execute(id_generator=other_generator).ordini_generati[0]
    assert first.ordine.id != second.ordine.id
    assert first.chiave_idempotenza == second.chiave_idempotenza


def test_chiave_indipendente_dall_ordine_ricevuto_delle_righe() -> None:
    prima = riga("VAR-000001", quantita=5)
    seconda = riga("VAR-000002", quantita=7, unita=UnitOfMeasure.GRAM)
    diretto = programma(righe=(prima, seconda))
    inverso = programma(righe=(seconda, prima))
    record_diretto = execute(programmi=(diretto,)).ordini_generati[0]
    record_inverso = execute(programmi=(inverso,)).ordini_generati[0]
    assert record_diretto.chiave_idempotenza == record_inverso.chiave_idempotenza
    assert record_diretto.ordine.righe == (
        RigaOrdine(prima.varieta_id, prima.quantita),
        RigaOrdine(seconda.varieta_id, seconda.quantita),
    )
    assert record_inverso.ordine.righe == (
        RigaOrdine(seconda.varieta_id, seconda.quantita),
        RigaOrdine(prima.varieta_id, prima.quantita),
    )


def test_righe_duplicate_non_sono_eliminate_o_aggregate() -> None:
    duplicata = riga(quantita=5)
    record = execute(programmi=(programma(righe=(duplicata, duplicata)),)).ordini_generati[0]
    assert len(record.ordine.righe) == 2
    assert record.ordine.righe[0] == record.ordine.righe[1]


def test_chiave_cambia_per_data_quantita_varieta_e_unita() -> None:
    base = execute().ordini_generati[0].chiave_idempotenza
    p_quantita = programma(righe=(riga(quantita=11),))
    p_varieta = programma(righe=(riga(varieta="VAR-000002"),))
    p_unita = programma(righe=(riga(unita=UnitOfMeasure.GRAM),))
    p_data = programma(data_inizio=date(2026, 7, 7))
    assert execute(programmi=(p_quantita,)).ordini_generati[0].chiave_idempotenza != base
    assert execute(programmi=(p_varieta,)).ordini_generati[0].chiave_idempotenza != base
    assert execute(programmi=(p_unita,)).ordini_generati[0].chiave_idempotenza != base
    assert execute(giorno=date(2026, 7, 7), programmi=(p_data,)).ordini_generati[0].chiave_idempotenza != base


def test_simulazione_non_consuma_id_e_produce_anteprima() -> None:
    generator = FakeIdGenerator()
    result = execute(simulation=True, id_generator=generator)
    assert result.ordini_generati == ()
    assert len(result.anteprime) == 1
    assert generator.calls == 0
    assert result.simulation is True


def test_determinismo_a_parita_di_input() -> None:
    first = execute(simulation=True, id_generator=None)
    second = execute(simulation=True, id_generator=None)
    assert first == second


def test_input_e_risultato_immutabili() -> None:
    req = request()
    result = SchedulingEngine().execute(req)
    with pytest.raises(FrozenInstanceError):
        req.simulation = True
    with pytest.raises(FrozenInstanceError):
        result.simulation = True


def test_esito_e_conteggi_success() -> None:
    result = execute()
    assert result.esito is RunState.SUCCESS
    assert result.programmi_letti == 1
    assert result.righe_valutate == 1
    assert result.occorrenze_valutate == 1
    assert result.occorrenze_generate == 1


def test_non_modifica_programmi_o_ordini_esistenti() -> None:
    p = programma()
    first = execute(programmi=(p,)).ordini_generati[0]
    before = (p, first)
    execute(programmi=(p,), ordini_esistenti=(first,))
    assert (p, first) == before


def test_engine_non_espone_responsabilita_estranee() -> None:
    engine = SchedulingEngine()
    for name in ("stock", "consegne", "planning", "repository", "persist", "prenotazioni"):
        assert not hasattr(engine, name)


def test_moduli_non_importano_infrastruttura_o_orologio() -> None:
    import src.tpo_core.application.scheduling.engine as module

    names = set(module.__dict__)
    for forbidden in ("sqlite3", "requests", "yaml", "Path", "datetime"):
        assert forbidden not in names
