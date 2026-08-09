from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.tpo_core.application.identity import IdentifierSequence, PersistentIdAllocator
from src.tpo_core.application.run_tracking import (
    CompletedSchedulingRun,
    InvalidSchedulingRunError,
    OpenSchedulingRun,
    SchedulingRunAlreadyExistsError,
    SchedulingRunConflictError,
    SchedulingRunCompletion,
    SchedulingRunNotFoundError,
    SchedulingRunService,
)
from src.tpo_core.application.scheduling.models import SchedulingResult
from src.tpo_core.domain.identifiers import RunId
from src.tpo_core.domain.states import RunState
from src.tpo_core.domain.time_reference import CurrentSystemDate


TZ = ZoneInfo("Atlantic/Canary")


class FakeSequenceRepository:
    def __init__(self) -> None:
        self.current = IdentifierSequence("RunId", "RUN", 1, 0)

    def get_sequence(self, identifier_type):
        return self.current

    def compare_and_set(self, *, identifier_type, expected_version, expected_next_value, new_next_value):
        if (self.current.version, self.current.next_value) != (expected_version, expected_next_value):
            return False
        self.current = IdentifierSequence("RunId", "RUN", new_next_value, self.current.version + 1)
        return True


class FakeRunRepository:
    def __init__(self, *, add_error=None, complete_error=None) -> None:
        self.runs = {}
        self.add_error = add_error
        self.complete_error = complete_error
        self.complete_calls = 0

    def add_open_run(self, run):
        if self.add_error:
            raise self.add_error
        if run.run_id in self.runs:
            raise SchedulingRunAlreadyExistsError(run.run_id.value)
        self.runs[run.run_id] = run

    def get(self, run_id):
        try:
            return self.runs[run_id]
        except KeyError as exc:
            raise SchedulingRunNotFoundError(run_id.value) from exc

    def complete(self, *, run_id, expected_version, completed_run):
        self.complete_calls += 1
        if self.complete_error:
            raise self.complete_error
        current = self.runs.get(run_id)
        if not isinstance(current, OpenSchedulingRun) or current.version != expected_version:
            return False
        self.runs[run_id] = completed_run
        return True


def instant(hour=5):
    return CurrentSystemDate(datetime(2026, 8, 3, hour, tzinfo=TZ))


def service(run_repository=None):
    repository = run_repository or FakeRunRepository()
    allocator = PersistentIdAllocator(FakeSequenceRepository())
    return SchedulingRunService(allocator, repository), repository


def result(run, *, warnings=(), state=RunState.SUCCESS):
    return SchedulingResult(
        run_id=run.run_id,
        ordini_generati=(),
        anteprime=(),
        programmi_letti=3,
        righe_valutate=4,
        occorrenze_valutate=5,
        occorrenze_generate=2,
        occorrenze_saltate_per_idempotenza=1,
        avvisi=warnings,
        simulation=run.simulation,
        esito=state,
    )


def test_apertura_alloca_run_id_e_preserva_input() -> None:
    target, repository = service()
    started = instant()
    run = target.open_run(started_at=started, simulation=True)
    assert run == OpenSchedulingRun(RunId("RUN-000001"), started, True, 0)
    assert repository.get(run.run_id) is run


def test_apertura_con_run_id_allocato_non_consuma_secondo_identificativo() -> None:
    target, repository = service()
    run = target.open_run(
        run_id=RunId("RUN-000099"),
        started_at=instant(),
        simulation=False,
    )
    assert run.run_id == RunId("RUN-000099")
    assert repository.get(run.run_id) is run
    assert target._id_allocator.allocate(RunId).identifier == RunId("RUN-000001")


def test_get_run_espone_stato_autorevole_del_repository() -> None:
    target, _ = service()
    opened = target.open_run(started_at=instant(), simulation=False)
    assert target.get_run(opened.run_id) is opened


def test_aperture_successive_usano_run_id_distinti() -> None:
    target, _ = service()
    assert target.open_run(started_at=instant(), simulation=False).run_id == RunId("RUN-000001")
    assert target.open_run(started_at=instant(), simulation=False).run_id == RunId("RUN-000002")


def test_completamento_success_deriva_contatori() -> None:
    target, repository = service()
    opened = target.open_run(started_at=instant(), simulation=False)
    completed = target.complete_run(open_run=opened, completed_at=instant(6), scheduling_result=result(opened))
    assert completed.state is RunState.SUCCESS
    assert (completed.programmi_letti, completed.righe_valutate, completed.occorrenze_valutate) == (3, 4, 5)
    assert (completed.ordini_generati, completed.elementi_saltati) == (2, 1)
    assert completed.version == 1
    assert repository.get(opened.run_id) is completed


def test_completamento_success_with_warnings() -> None:
    target, _ = service()
    opened = target.open_run(started_at=instant(), simulation=True)
    completed = target.complete_run(
        open_run=opened,
        completed_at=instant(6),
        scheduling_result=result(opened, warnings=("riga saltata",), state=RunState.SUCCESS_WITH_WARNINGS),
    )
    assert completed.state is RunState.SUCCESS_WITH_WARNINGS
    assert completed.warnings == ("riga saltata",)


def test_proposta_success_non_persiste_e_lascia_run_aperta() -> None:
    target, repository = service()
    open_run = target.open_run(started_at=instant(), simulation=False)
    proposal = target.propose_completion(
        open_run=open_run,
        completed_at=instant(6),
        scheduling_result=result(open_run),
    )
    assert proposal == SchedulingRunCompletion(
        run_id=open_run.run_id,
        started_at=open_run.started_at,
        completed_at=instant(6),
        simulation=False,
        expected_version=0,
        final_state=RunState.SUCCESS,
        programmi_letti=3,
        righe_valutate=4,
        occorrenze_valutate=5,
        ordini_generati=2,
        elementi_saltati=1,
        warnings=(),
        errors=(),
    )
    assert repository.complete_calls == 0
    assert repository.get(open_run.run_id) is open_run


def test_proposte_warning_e_failed_valide_senza_persistenza() -> None:
    target, repository = service()
    open_run = target.open_run(started_at=instant(), simulation=False)
    warned = target.propose_completion(
        open_run=open_run,
        completed_at=instant(6),
        scheduling_result=result(
            open_run,
            warnings=("warning",),
            state=RunState.SUCCESS_WITH_WARNINGS,
        ),
    )
    failed = target.propose_failure(
        open_run=open_run,
        completed_at=instant(6),
        warnings=("warning",),
        errors=("errore",),
    )
    assert warned.final_state is RunState.SUCCESS_WITH_WARNINGS
    assert failed.final_state is RunState.FAILED
    assert repository.complete_calls == 0


@pytest.mark.parametrize(
    "changes",
    (
        {"simulation": 1},
        {"expected_version": -1},
        {"expected_version": True},
        {"programmi_letti": -1},
        {"programmi_letti": True},
        {"warnings": ("warning",)},
    ),
)
def test_modello_proposta_invalido(changes) -> None:
    values = dict(
        run_id=RunId("RUN-000001"),
        started_at=instant(),
        completed_at=instant(6),
        simulation=False,
        expected_version=0,
        final_state=RunState.SUCCESS,
        programmi_letti=0,
        righe_valutate=0,
        occorrenze_valutate=0,
        ordini_generati=0,
        elementi_saltati=0,
        warnings=(),
        errors=(),
    )
    values.update(changes)
    with pytest.raises(InvalidSchedulingRunError):
        SchedulingRunCompletion(**values)


def test_proposta_immutabile_e_materializza_versione_successiva() -> None:
    proposal = SchedulingRunCompletion(
        RunId("RUN-000001"), instant(), instant(6), False, 2,
        RunState.SUCCESS, 0, 0, 0, 0, 0, (), (),
    )
    assert proposal.to_completed_run().version == 3
    with pytest.raises(FrozenInstanceError):
        proposal.expected_version = 4


def test_fallimento_failed_preserva_errori_e_warning() -> None:
    target, _ = service()
    opened = target.open_run(started_at=instant(), simulation=False)
    completed = target.fail_run(
        open_run=opened,
        completed_at=instant(6),
        errors=("errore",),
        warnings=("warning",),
    )
    assert completed.state is RunState.FAILED
    assert completed.errors == ("errore",)
    assert completed.warnings == ("warning",)


def test_failed_senza_errori_rifiutato() -> None:
    target, _ = service()
    opened = target.open_run(started_at=instant(), simulation=False)
    with pytest.raises(InvalidSchedulingRunError):
        target.fail_run(open_run=opened, completed_at=instant(6), errors=())


def test_completed_at_precedente_rifiutato() -> None:
    target, _ = service()
    opened = target.open_run(started_at=instant(6), simulation=False)
    with pytest.raises(InvalidSchedulingRunError):
        target.fail_run(open_run=opened, completed_at=instant(5), errors=("errore",))


@pytest.mark.parametrize("field", ["programmi_letti", "righe_valutate", "occorrenze_valutate", "ordini_generati", "elementi_saltati"])
def test_contatori_negativi_rifiutati(field) -> None:
    values = dict(
        run_id=RunId("RUN-000001"), started_at=instant(), completed_at=instant(6),
        simulation=False, state=RunState.SUCCESS, programmi_letti=0, righe_valutate=0,
        occorrenze_valutate=0, ordini_generati=0, elementi_saltati=0,
        warnings=(), errors=(), version=1,
    )
    values[field] = -1
    with pytest.raises(InvalidSchedulingRunError):
        CompletedSchedulingRun(**values)


def test_doppio_completamento_e_conflitto_versione_rifiutati() -> None:
    target, _ = service()
    opened = target.open_run(started_at=instant(), simulation=False)
    target.complete_run(open_run=opened, completed_at=instant(6), scheduling_result=result(opened))
    with pytest.raises(SchedulingRunConflictError):
        target.complete_run(open_run=opened, completed_at=instant(7), scheduling_result=result(opened))


def test_run_id_duplicato_rifiutato_dal_repository() -> None:
    repository = FakeRunRepository()
    opened = OpenSchedulingRun(RunId("RUN-000001"), instant(), False)
    repository.add_open_run(opened)
    with pytest.raises(SchedulingRunAlreadyExistsError):
        repository.add_open_run(opened)


def test_repository_error_propagato() -> None:
    expected = RuntimeError("repository indisponibile")
    target, _ = service(FakeRunRepository(add_error=expected))
    with pytest.raises(RuntimeError, match="repository indisponibile"):
        target.open_run(started_at=instant(), simulation=False)


def test_result_di_altra_run_o_modalita_rifiutato() -> None:
    target, _ = service()
    opened = target.open_run(started_at=instant(), simulation=False)
    other = result(opened)
    object.__setattr__(other, "run_id", RunId("RUN-999999"))
    with pytest.raises(InvalidSchedulingRunError):
        target.complete_run(open_run=opened, completed_at=instant(6), scheduling_result=other)


def test_modelli_immutabili() -> None:
    opened = OpenSchedulingRun(RunId("RUN-000001"), instant(), False)
    with pytest.raises(FrozenInstanceError):
        opened.version = 2


def test_servizio_non_usa_clock_filesystem_yaml_o_infrastruttura() -> None:
    import src.tpo_core.application.run_tracking.service as module

    names = set(module.__dict__)
    assert not names.intersection({"datetime", "date", "time", "Path", "yaml", "GoogleApiSheetsGateway"})
