import pytest

from src.tpo_core.cli import main as main_module


def valid_args(*extra: str) -> list[str]:
    return [
        "schedule", "run", "--simulate", "--settings", "settings.yaml",
        "--current-system-date", "2026-08-03T12:00:00+01:00",
        "--run-id", "RUN-000001", *extra,
    ]


def test_parser_valido_e_json(monkeypatch) -> None:
    received = []

    def fake(args, **kwargs):
        received.append(args)
        return 0

    monkeypatch.setattr(main_module, "run_scheduling_command", fake)
    assert main_module.main(valid_args("--json")) == 0
    assert received[0].simulate is True
    assert received[0].json_output is True


def test_parser_execute_registrato_con_soli_argomenti_congelati(monkeypatch) -> None:
    received = []
    monkeypatch.setattr(
        main_module,
        "run_operational_scheduling_command",
        lambda args, **kwargs: received.append(args) or 0,
    )

    code = main_module.main(
        [
            "schedule",
            "execute",
            "--settings",
            "settings.yaml",
            "--business-date",
            "2026-08-10",
            "--business-time",
            "14:35",
            "--identity",
            "operator-1",
            "--confirm",
        ]
    )

    assert code == 0
    assert received[0].business_date == "2026-08-10"
    assert received[0].business_time == "14:35"
    assert received[0].identity == "operator-1"
    assert received[0].confirm is True
    assert not hasattr(received[0], "simulation")
    assert not hasattr(received[0], "run_id")


@pytest.mark.parametrize("operation", ["initial", "replan"])
def test_parser_production_planning_registra_help_e_argomenti_obbligatori(
    monkeypatch, operation,
) -> None:
    received = []
    monkeypatch.setattr(
        main_module, "run_production_planning_command",
        lambda args, **kwargs: received.append(args) or 0,
    )
    argv = [
        "production-planning", operation,
        "--business-at", "2026-08-23T12:00:00+01:00",
        "--policy-set-code", "DEFAULT", "--policy-version", "1",
        "--actor", "planner", "--reason", "planning",
        "--correlation-id", "corr-1",
    ]
    if operation == "replan":
        argv.extend([
            "--previous-revision-public-id", "RVP-000001",
            "--order-line-public-id", "RO-000001",
            "--replanning-reason-code", "STOCK_CHANGED",
        ])
    assert main_module.main(argv) == 0
    assert len(received) == 1
    assert received[0].production_planning_command == operation


def test_production_planning_help_is_stable():
    help_text = main_module._parser().format_help()
    assert "production-planning" in help_text


@pytest.mark.parametrize("operation", ["initial", "replan"])
def test_production_planning_missing_required_argument_fails_closed(
    monkeypatch, operation,
) -> None:
    monkeypatch.setattr(
        main_module,
        "run_production_planning_command",
        lambda *args, **kwargs: pytest.fail("Il runtime non deve essere invocato"),
    )
    assert main_module.main(["production-planning", operation]) == 2


@pytest.mark.parametrize(
    "missing",
    ("--settings", "--business-date", "--business-time", "--identity", "--confirm"),
)
def test_parser_execute_rifiuta_argomento_obbligatorio_mancante(
    monkeypatch, missing
) -> None:
    argv = [
        "schedule",
        "execute",
        "--settings",
        "settings.yaml",
        "--business-date",
        "2026-08-10",
        "--business-time",
        "14:35",
        "--identity",
        "operator-1",
        "--confirm",
    ]
    if missing == "--confirm":
        argv.remove(missing)
    else:
        position = argv.index(missing)
        del argv[position : position + 2]
    monkeypatch.setattr(
        main_module,
        "run_operational_scheduling_command",
        lambda *args, **kwargs: pytest.fail("Entry Point non deve essere invocato"),
    )

    assert main_module.main(argv) == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["schedule", "run", "--settings", "s", "--current-system-date", "2026-08-03T12:00:00+01:00", "--run-id", "RUN-000001"],
        ["unknown"],
        ["schedule", "run", "--simulate", "--current-system-date", "2026-08-03T12:00:00+01:00", "--run-id", "RUN-000001"],
        ["schedule", "run", "--simulate", "--settings", "s", "--run-id", "RUN-000001"],
        ["schedule", "run", "--simulate", "--settings", "s", "--current-system-date", "2026-08-03T12:00:00+01:00"],
        [*valid_args(), "--write"],
        [*valid_args(), "--force"],
    ],
)
def test_argomenti_non_validi_restituiscono_2_senza_eseguire(monkeypatch, argv) -> None:
    monkeypatch.setattr(
        main_module,
        "run_scheduling_command",
        lambda *args, **kwargs: pytest.fail("Il comando non deve essere eseguito"),
    )
    assert main_module.main(argv) == 2
