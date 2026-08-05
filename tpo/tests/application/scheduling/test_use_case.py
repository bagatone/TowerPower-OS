from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.ports.repositories import (
    OrdineRepository,
    ProgrammaFornituraRepository,
)
from src.tpo_core.application.scheduling.engine import SchedulingEngine
from src.tpo_core.application.scheduling.models import SchedulingRequest
from src.tpo_core.application.scheduling.provenance import (
    VersionedProgramLine,
    VersionedProgrammaFornitura,
)
from src.tpo_core.application.scheduling.use_case import RunScheduling
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
from src.tpo_core.domain.states import ProgrammaFornituraState
from src.tpo_core.domain.time_reference import CurrentSystemDate


TZ = ZoneInfo("Atlantic/Canary")


class RepositoryError(RuntimeError):
    pass


class FakeProgrammaFornituraRepository:
    def __init__(self, programmi=(), error=None) -> None:
        self.programmi = programmi
        self.error = error
        self.reads = 0

    def list_versioned_for_scheduling(self):
        self.reads += 1
        if self.error is not None:
            raise self.error
        return tuple(versioned(item) for item in self.programmi)


class FakeOrdineRepository:
    def __init__(self, records=(), read_error=None, write_error=None) -> None:
        self.records = records
        self.read_error = read_error
        self.write_error = write_error
        self.reads = 0
        self.writes = 0
        self.received = []

    def list_scheduled_orders(self):
        self.reads += 1
        if self.read_error is not None:
            raise self.read_error
        return self.records

    def add_scheduled_orders(self, records):
        self.writes += 1
        self.received.append(records)
        if self.write_error is not None:
            raise self.write_error


class FakeIdGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def next_id(self, identifier_type):
        self.calls += 1
        return identifier_type(f"ORD-{self.calls:06d}")


class CapturingEngine:
    def __init__(self, delegate=None) -> None:
        self.delegate = delegate or SchedulingEngine()
        self.requests = []
        self.results = []

    def execute(self, request):
        self.requests.append(request)
        result = self.delegate.execute(request)
        self.results.append(result)
        return result


def build_programma(identifier="PF-000001", varieta="VAR-000001"):
    return ProgrammaFornitura(
        id=ProgrammaFornituraId(identifier),
        cliente_id=ClienteId("CLI-000001"),
        righe=(
            RigaProgrammaFornitura(
                VarietaId(varieta),
                Quantity(10, UnitOfMeasure.SET),
                ConfigurazioneTemporale(TipoRicorrenza.SETTIMANALE),
            ),
        ),
        data_inizio=date(2026, 8, 3),
        stato=ProgrammaFornituraState.ATTIVO,
        finestra_operativa_giorni=0,
        orario_generazione=time(5),
    )


def versioned(item, version=3):
    return VersionedProgrammaFornitura(
        programma=item,
        version=version,
        lines=tuple(
            VersionedProgramLine(position, line)
            for position, line in enumerate(item.righe, start=1)
        ),
    )


def current_system_date():
    return CurrentSystemDate(datetime(2026, 8, 3, 5, tzinfo=TZ))


def build_use_case(programmi=(), records=(), **ordine_options):
    programmi_repo = FakeProgrammaFornituraRepository(programmi)
    ordini_repo = FakeOrdineRepository(records, **ordine_options)
    generator = FakeIdGenerator()
    engine = CapturingEngine()
    use_case = RunScheduling(programmi_repo, ordini_repo, generator, engine)
    return use_case, programmi_repo, ordini_repo, generator, engine


def run(use_case, simulation=False, run_id=None, current=None):
    return use_case.execute(
        run_id=run_id or RunId("RUN-000001"),
        current_system_date=current or current_system_date(),
        simulation=simulation,
    )


def test_nessun_programma_legge_una_volta_e_non_scrive() -> None:
    use_case, programmi_repo, ordini_repo, generator, _ = build_use_case()
    result = run(use_case)
    assert result.ordini_generati == ()
    assert programmi_repo.reads == 1
    assert ordini_repo.reads == 1
    assert ordini_repo.writes == 0
    assert generator.calls == 0


def test_programma_attivo_genera_senza_scrittura_diretta() -> None:
    use_case, programmi_repo, ordini_repo, generator, engine = build_use_case(
        (build_programma(),)
    )
    result = run(use_case)
    assert result is engine.results[0]
    assert result.ordini_generati
    assert ordini_repo.received == []
    assert ordini_repo.writes == 0
    assert programmi_repo.reads == ordini_repo.reads == 1
    assert generator.calls == 1


def test_ordine_dei_record_generati_e_preservato() -> None:
    programmi = (
        build_programma("PF-000001", "VAR-000001"),
        build_programma("PF-000002", "VAR-000002"),
    )
    use_case, _, ordini_repo, _, _ = build_use_case(programmi)
    result = run(use_case)
    assert tuple(
        record.ordine.programma_fornitura_id for record in result.ordini_generati
    ) == (ProgrammaFornituraId("PF-000001"), ProgrammaFornituraId("PF-000002"))


def test_record_esistente_impedisce_generazione_e_scrittura() -> None:
    first_use_case, _, _, _, _ = build_use_case((build_programma(),))
    existing = run(first_use_case).ordini_generati[0]
    use_case, _, ordini_repo, generator, _ = build_use_case(
        (build_programma(),), (existing,)
    )
    result = run(use_case)
    assert result.ordini_generati == ()
    assert result.occorrenze_saltate_per_idempotenza == 1
    assert ordini_repo.writes == 0
    assert generator.calls == 0
    assert ordini_repo.records == (existing,)


def test_use_case_non_costruisce_chiavi_idempotenti() -> None:
    use_case, _, _, _, _ = build_use_case((build_programma(),))
    assert not hasattr(use_case, "_chiave_idempotenza")
    assert not hasattr(use_case, "chiave_idempotenza")


def test_simulazione_legge_tutto_non_salva_e_non_consuma_id() -> None:
    use_case, programmi_repo, ordini_repo, generator, engine = build_use_case(
        (build_programma(),)
    )
    result = run(use_case, simulation=True)
    assert len(result.anteprime) == 1
    assert result.ordini_generati == ()
    assert programmi_repo.reads == ordini_repo.reads == 1
    assert ordini_repo.writes == 0
    assert generator.calls == 0
    assert engine.requests[0].simulation is True


def test_run_id_current_system_date_e_generator_inoltrati_senza_modifiche() -> None:
    use_case, _, _, generator, engine = build_use_case((build_programma(),))
    run_id = RunId("RUN-000002")
    current = current_system_date()
    result = run(use_case, run_id=run_id, current=current)
    request = engine.requests[0]
    assert request.run_id is run_id
    assert request.current_system_date is current
    assert request.id_generator is generator
    assert result.run_id is run_id


def test_use_case_non_accede_all_orologio_e_non_genera_run_id() -> None:
    import src.tpo_core.application.scheduling.use_case as module

    names = set(module.__dict__)
    assert "datetime" not in names
    assert "date" not in names
    assert "time" not in names
    assert not hasattr(RunScheduling, "next_run_id")


def test_errore_lettura_programmi_propagato_e_blocca_flusso() -> None:
    error = RepositoryError("programmi")
    programmi_repo = FakeProgrammaFornituraRepository(error=error)
    ordini_repo = FakeOrdineRepository()
    use_case = RunScheduling(
        programmi_repo, ordini_repo, FakeIdGenerator(), SchedulingEngine()
    )
    with pytest.raises(RepositoryError) as raised:
        run(use_case)
    assert raised.value is error
    assert ordini_repo.reads == ordini_repo.writes == 0


def test_errore_lettura_ordini_propagato() -> None:
    error = RepositoryError("ordini")
    use_case, _, ordini_repo, _, _ = build_use_case(
        (build_programma(),), read_error=error
    )
    with pytest.raises(RepositoryError) as raised:
        run(use_case)
    assert raised.value is error
    assert ordini_repo.writes == 0


def test_writer_legacy_non_invocato_dal_nuovo_flusso() -> None:
    error = RepositoryError("writer legacy")
    use_case, _, ordini_repo, _, _ = build_use_case(
        (build_programma(),), write_error=error
    )
    result = run(use_case)
    assert result.ordini_generati
    assert ordini_repo.writes == 0


def test_porte_sono_protocol_e_fake_conformi() -> None:
    from src.tpo_core.application.ports.repositories import (
        ScheduledOrderReadRepository,
        VersionedProgrammaFornituraRepository,
    )

    assert getattr(ProgrammaFornituraRepository, "_is_protocol", False)
    assert getattr(OrdineRepository, "_is_protocol", False)
    assert getattr(ScheduledOrderReadRepository, "_is_protocol", False)
    assert getattr(VersionedProgrammaFornituraRepository, "_is_protocol", False)
    assert hasattr(FakeProgrammaFornituraRepository(), "list_versioned_for_scheduling")
    assert hasattr(FakeOrdineRepository(), "list_scheduled_orders")
    assert hasattr(FakeOrdineRepository(), "add_scheduled_orders")


def test_nessuna_dipendenza_infrastrutturale() -> None:
    import src.tpo_core.application.ports.repositories as repositories_module
    import src.tpo_core.application.scheduling.use_case as use_case_module

    for module in (repositories_module, use_case_module):
        names = set(module.__dict__)
        for forbidden in ("sqlite3", "requests", "yaml", "Path", "open"):
            assert forbidden not in names


def test_use_case_delega_la_logica_al_motore() -> None:
    use_case, _, _, _, engine = build_use_case((build_programma(),))
    assert not hasattr(use_case, "_ricorre")
    assert not hasattr(use_case, "_occorrenze_dovute")
    assert not hasattr(use_case, "_chiave_idempotenza")
    run(use_case)
    assert isinstance(engine.requests[0], SchedulingRequest)
