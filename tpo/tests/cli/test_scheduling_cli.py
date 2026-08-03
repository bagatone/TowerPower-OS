from argparse import Namespace
from datetime import date
from io import StringIO
import json

import pytest

from src.tpo_core.application.scheduling.models import GeneratedOrderDraft, SchedulingResult
from src.tpo_core.bootstrap.settings import ApplicationSettings, InvalidSettingsError
from src.tpo_core.cli.scheduling import (
    SchedulingCliDependencies,
    SimulationOnlyIdGenerator,
    run_scheduling_command,
)
from src.tpo_core.domain.entities.ordine import RigaOrdine
from src.tpo_core.domain.identifiers import ClienteId, ProgrammaFornituraId, RunId, VarietaId
from src.tpo_core.domain.quantities import Quantity, UnitOfMeasure
from src.tpo_core.domain.states import RunState
from src.tpo_core.infrastructure.google_sheets.errors import GoogleSheetsRepositoryError


def args(**overrides):
    values = {
        "simulate": True,
        "settings": "settings.yaml",
        "current_system_date": "2026-08-03T12:00:00+01:00",
        "run_id": "RUN-000001",
        "json_output": False,
    }
    values.update(overrides)
    return Namespace(**values)


def settings():
    return ApplicationSettings(
        spreadsheet_id="secret-spreadsheet-id",
        credentials_file="secret-credentials.json",
        scopes=("scope",),
        programmi_fornitura_sheet="PROGRAMMI_FORNITURA",
        ordini_sheet="ORDINI",
    )


def result():
    previews = (
        GeneratedOrderDraft(
            cliente_id=ClienteId("CLI-000001"),
            programma_fornitura_id=ProgrammaFornituraId("PF-000001"),
            data_ordine=date(2026, 8, 3),
            data_consegna_prevista=date(2026, 8, 6),
            righe=(
                RigaOrdine(VarietaId("VAR-000002"), Quantity("12.50", UnitOfMeasure.SET)),
                RigaOrdine(VarietaId("VAR-000001"), Quantity("0.5", UnitOfMeasure.GRAM)),
            ),
            chiave_idempotenza="key-first",
        ),
        GeneratedOrderDraft(
            cliente_id=ClienteId("CLI-000002"),
            programma_fornitura_id=ProgrammaFornituraId("PF-000002"),
            data_ordine=date(2026, 8, 3),
            data_consegna_prevista=date(2026, 8, 7),
            righe=(RigaOrdine(VarietaId("VAR-000003"), Quantity("2", UnitOfMeasure.UNIT)),),
            chiave_idempotenza="key-second",
        ),
    )
    return SchedulingResult(
        run_id=RunId("RUN-000001"),
        ordini_generati=(),
        anteprime=previews,
        programmi_letti=2,
        righe_valutate=3,
        occorrenze_valutate=2,
        occorrenze_generate=2,
        occorrenze_saltate_per_idempotenza=1,
        avvisi=("avviso",),
        simulation=True,
        esito=RunState.SUCCESS_WITH_WARNINGS,
    )


class FakeRunScheduling:
    def __init__(self, returned=None, error=None):
        self.returned = returned or result()
        self.error = error
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.returned


class FakeContainer:
    def __init__(self, use_case):
        self.run_scheduling = use_case


def harness(*, cli_args=None, settings_error=None, service_error=None, run_error=None):
    calls = {"settings": [], "service": [], "application": []}
    use_case = FakeRunScheduling(error=run_error)

    def settings_loader(path):
        calls["settings"].append(path)
        if settings_error:
            raise settings_error
        return settings()

    def service_factory(path, *, scopes):
        calls["service"].append((path, scopes))
        if service_error:
            raise service_error
        return object()

    def application_factory(path, *, google_service, id_generator):
        calls["application"].append((path, google_service, id_generator))
        return FakeContainer(use_case)

    dependencies = SchedulingCliDependencies(
        settings_loader=settings_loader,
        service_factory=service_factory,
        application_factory=application_factory,
    )
    stdout, stderr = StringIO(), StringIO()
    code = run_scheduling_command(
        cli_args or args(), stdout=stdout, stderr=stderr, dependencies=dependencies
    )
    return code, stdout.getvalue(), stderr.getvalue(), calls, use_case


def test_esecuzione_valida_inietta_dipendenze_e_forza_simulazione() -> None:
    code, output, error, calls, use_case = harness()
    assert code == 0
    assert error == ""
    assert calls["settings"] == ["settings.yaml"]
    assert calls["service"] == [("secret-credentials.json", ("scope",))]
    assert len(calls["application"]) == 1
    assert isinstance(calls["application"][0][2], SimulationOnlyIdGenerator)
    assert len(use_case.calls) == 1
    assert use_case.calls[0]["simulation"] is True
    assert use_case.calls[0]["run_id"] == RunId("RUN-000001")
    assert use_case.calls[0]["current_system_date"].datetime.isoformat() == "2026-08-03T12:00:00+01:00"
    assert "secret-spreadsheet-id" not in output
    assert "secret-credentials.json" not in output


def test_simulation_generator_fallisce_se_consumato() -> None:
    with pytest.raises(RuntimeError, match="non deve consumare"):
        SimulationOnlyIdGenerator().next_id(object)


def test_simulate_false_rifiutato_prima_di_ogni_dipendenza() -> None:
    code, _, error, calls, _ = harness(cli_args=args(simulate=False))
    assert code == 2
    assert "--simulate" in error
    assert calls["settings"] == calls["service"] == calls["application"] == []


@pytest.mark.parametrize(
    "cli_args",
    [
        args(run_id="invalid"),
        args(current_system_date="not-a-date"),
        args(current_system_date="2026-08-03T12:00:00"),
    ],
)
def test_validazione_input_fallisce_prima_del_servizio(cli_args) -> None:
    code, _, error, calls, _ = harness(cli_args=cli_args)
    assert code == 2
    assert error
    assert calls["settings"] == calls["service"] == calls["application"] == []


def test_settings_non_valide_exit_3_senza_servizio() -> None:
    code, _, error, calls, _ = harness(settings_error=InvalidSettingsError("bad"))
    assert code == 3
    assert "Configurazione non valida" in error
    assert calls["service"] == calls["application"] == []


def test_servizio_google_fallito_exit_4() -> None:
    code, _, error, calls, _ = harness(
        service_error=GoogleSheetsRepositoryError("auth failed")
    )
    assert code == 4
    assert "Servizio Google Sheets" in error
    assert calls["application"] == []


def test_repository_o_scheduling_fallito_exit_5() -> None:
    code, _, error, _, _ = harness(
        run_error=GoogleSheetsRepositoryError("read failed")
    )
    assert code == 5
    assert "Esecuzione Scheduling" in error


def test_output_testuale_completo_e_ordine_preservato() -> None:
    code, output, _, _, _ = harness()
    assert code == 0
    for expected in (
        "RUN_ID: RUN-000001", "MODALITÀ: SIMULATION", "ESITO: SUCCESS_WITH_WARNINGS",
        "PROGRAMMI LETTI: 2", "RIGHE VALUTATE: 3", "OCCORRENZE VALUTATE: 2",
        "OCCORRENZE GENERATE: 2", "OCCORRENZE SALTATE PER IDEMPOTENZA: 1",
        "ANTEPRIME: 2", "PF-000001", "CLI-000001", "2026-08-06",
        "key-first", "VAR-000002: 12.5 SET", "avviso",
    ):
        assert expected in output
    assert output.index("PF-000001") < output.index("PF-000002")
    assert output.index("VAR-000002") < output.index("VAR-000001")


def test_output_json_valido_deterministico_e_stdout_separato() -> None:
    code, output, error, _, _ = harness(cli_args=args(json_output=True))
    assert code == 0
    assert error == ""
    payload = json.loads(output)
    assert payload["run_id"] == "RUN-000001"
    assert payload["simulation"] is True
    assert payload["anteprime"][0]["righe"][0]["quantita"] == "12.5"
    assert payload["anteprime"][0]["righe"][1]["quantita"] == "0.5"
    assert [item["programma_fornitura_id"] for item in payload["anteprime"]] == ["PF-000001", "PF-000002"]
    assert "secret" not in output


def test_nessun_accesso_al_clock_o_modalita_operativa() -> None:
    import src.tpo_core.cli.scheduling as module

    source_names = set(module.__dict__)
    assert "date" not in source_names
    assert "time" not in source_names
    assert "now" not in source_names
    assert "today" not in source_names


def test_domain_non_importa_la_cli() -> None:
    from pathlib import Path

    domain_root = Path("src/tpo_core/domain")
    for path in domain_root.rglob("*.py"):
        assert "tpo_core.cli" not in path.read_text(encoding="utf-8")


def test_import_cli_non_autentica(monkeypatch) -> None:
    import importlib
    import src.tpo_core.infrastructure.google_sheets.google_api_gateway as gateway_module

    monkeypatch.setattr(
        gateway_module,
        "build_google_sheets_service",
        lambda *args, **kwargs: pytest.fail("autenticazione durante import"),
    )
    importlib.reload(importlib.import_module("src.tpo_core.cli.scheduling"))
    importlib.reload(importlib.import_module("src.tpo_core.cli.main"))
