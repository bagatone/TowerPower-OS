from datetime import datetime, timezone
from io import StringIO
import json

from src.tpo_core.application.semina_lifecycle.models import TransitionSeminaResult
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.semina import run_semina_command
from src.tpo_core.domain.identifiers import SeminaId
from src.tpo_core.domain.states import SeminaState


def args(*extra):
    provenance = {"target_state": "OWNER_AUTHORIZED", "effective_at": "OWNER_AUTHORIZED"}
    return ["semina", "transition", "--semina", "SEM-000001",
            "--expected-semina-version", "0", "--target-state", "GERMINAZIONE",
            "--effective-at", "2026-08-25T09:00:00+01:00",
            "--provenance", json.dumps(provenance), "--actor", "owner",
            "--reason", "physical", "--correlation-id", "corr",
            "--idempotency-key", "idem", "--confirm", *extra]


def test_parser_registers_one_transition_command():
    namespace = main_module._parser().parse_args(args())
    assert namespace.semina_command == "transition" and namespace.confirm


def test_transition_cli_is_thin(monkeypatch):
    class Service:
        def transition(self, command):
            assert command.semina_public_id == SeminaId("SEM-000001")
            return TransitionSeminaResult(
                command.semina_public_id, SeminaState.AVVIATA,
                SeminaState.GERMINAZIONE, None, command.effective_at,
                datetime(2026, 8, 25, 9, 1, tzinfo=timezone.utc), 0, 1, "INSERTED",
            )
    import src.tpo_core.cli.semina as module
    monkeypatch.setattr(module, "build_semina_lifecycle_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    stdout, stderr = StringIO(), StringIO()
    namespace = main_module._parser().parse_args(args())
    assert run_semina_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert "FROM_STATE: AVVIATA" in stdout.getvalue()
    assert "STATE: GERMINAZIONE" in stdout.getvalue() and stderr.getvalue() == ""


def test_closure_without_outcome_fails_before_runtime():
    values = args(); values[values.index("--target-state") + 1] = "CHIUSA"
    stdout, stderr = StringIO(), StringIO()
    namespace = main_module._parser().parse_args(values)
    assert run_semina_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "SEMINA_FINAL_OUTCOME_REQUIRED" in stderr.getvalue()
