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
