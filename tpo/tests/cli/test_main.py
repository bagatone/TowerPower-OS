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
