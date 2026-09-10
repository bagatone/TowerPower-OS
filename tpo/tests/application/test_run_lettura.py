from datetime import datetime, timedelta, timezone

import pytest

from src.tpo_core.application.run_lettura.errors import InvalidRunLetturaQueryError
from src.tpo_core.application.run_lettura.models import (
    ElencoRun, Run, RunLog, RunLogVoce, RunMessaggio,
)
from src.tpo_core.application.run_lettura.service import RunLetturaService
from src.tpo_core.domain.identifiers import RunId

NOW = datetime(2099, 1, 1, tzinfo=timezone.utc)


def _run(**overrides):
    base = dict(
        run_id=RunId("RUN-000001"), started_at=NOW, completed_at=NOW + timedelta(minutes=2),
        simulation=False, state="SUCCESS", programmi_letti=3, righe_valutate=10,
        occorrenze_valutate=8, ordini_generati=2, elementi_saltati=0, messaggi=(),
    )
    base.update(overrides)
    return Run(**base)


def test_run_requires_state_iff_completed_at():
    with pytest.raises(InvalidRunLetturaQueryError):
        _run(completed_at=None, state="SUCCESS")
    with pytest.raises(InvalidRunLetturaQueryError):
        _run(completed_at=NOW, state=None)


def test_run_rejects_completed_before_started():
    with pytest.raises(InvalidRunLetturaQueryError):
        _run(completed_at=NOW - timedelta(minutes=5))


def test_run_rejects_negative_counters():
    with pytest.raises(InvalidRunLetturaQueryError):
        _run(elementi_saltati=-1)


def test_run_messaggio_rejects_blank_messaggio():
    with pytest.raises(InvalidRunLetturaQueryError):
        RunMessaggio("WARNING", 1, "   ", NOW)


def test_run_log_voce_rejects_invalid_level():
    with pytest.raises(InvalidRunLetturaQueryError):
        RunLogVoce(NOW, "TRACE", "evento", "messaggio", {})


def test_run_log_voce_rejects_non_mapping_context():
    with pytest.raises(InvalidRunLetturaQueryError):
        RunLogVoce(NOW, "INFO", "evento", "messaggio", context=["not", "a", "mapping"])


class _FakeReader:
    def __init__(self):
        self.queries = {}

    def elenco(self, query):
        self.queries["elenco"] = query
        return ElencoRun(())

    def log(self, query):
        self.queries["log"] = query
        return RunLog(query.run_id, ())


def test_service_delegates_elenco_and_log():
    from src.tpo_core.application.run_lettura.models import RichiediElencoRun, RichiediRunLog

    reader = _FakeReader()
    service = RunLetturaService(reader)
    assert service.elenco(RichiediElencoRun()) == ElencoRun(())
    log_query = RichiediRunLog(RunId("RUN-000001"))
    assert service.log(log_query) == RunLog(RunId("RUN-000001"), ())
    assert set(reader.queries) == {"elenco", "log"}


def test_service_rejects_invalid_query_types():
    service = RunLetturaService(_FakeReader())
    with pytest.raises(InvalidRunLetturaQueryError):
        service.elenco(object())
    with pytest.raises(InvalidRunLetturaQueryError):
        service.log(object())
