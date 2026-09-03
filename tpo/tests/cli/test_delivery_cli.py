import json
from io import StringIO

from src.tpo_core.application.delivery_fulfilment.errors import DeliveryCommitOutcomeUncertain
from src.tpo_core.application.delivery_fulfilment.models import DeliveryFulfilmentResult
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.delivery import run_delivery_command
from src.tpo_core.domain.identifiers import ConsegnaId, MovimentoId, OrdineId


class _FakeAllocator:
    def __init__(self):
        self._counters = {"ConsegnaId": 0, "MovimentoId": 0}

    def allocate(self, identifier_type):
        self._counters[identifier_type.__name__] += 1
        value = self._counters[identifier_type.__name__]
        identifier = identifier_type(f"{identifier_type.prefix}-{value:06d}")
        return type("Allocated", (), {"identifier": identifier})()


def _lines_file(tmp_path, lines):
    path = tmp_path / "lines.json"
    path.write_text(json.dumps(lines))
    return str(path)


def args(lines_file, *extra):
    return [
        "delivery", "fulfil", "--client", "CLI-000001",
        "--planned-date", "2026-09-03", "--effective-at", "2026-09-03T10:00:00+00:00",
        "--lines-file", lines_file, "--actor", "owner", "--reason", "delivery",
        "--correlation-id", "corr-1", "--confirm", *extra,
    ]


def test_parser_registers_frozen_delivery_command(monkeypatch, tmp_path):
    received = []
    monkeypatch.setattr(main_module, "run_delivery_command", lambda a, **k: received.append(a) or 0)
    lines_file = _lines_file(tmp_path, [{"order_id": "ORD-000001"}])
    assert main_module.main(args(lines_file)) == 0
    assert received[0].delivery_command == "fulfil"
    assert received[0].client == "CLI-000001"
    assert received[0].confirm is True


def test_missing_required_input_fails_before_runtime(monkeypatch):
    monkeypatch.setattr(main_module, "run_delivery_command", lambda *a, **k: 99)
    assert main_module.main(["delivery", "fulfil"]) == 2


def test_cli_happy_path_is_thin(monkeypatch, tmp_path):
    class Service:
        def publish(self, command):
            return DeliveryFulfilmentResult(
                delivery_id=command.delivery_id,
                order_states=((OrdineId("ORD-000001"), "EVASO"),),
                delivery_line_count=len(command.lines),
                movement_count=len(command.lines),
            )
    import src.tpo_core.cli.delivery as module
    monkeypatch.setattr(module, "build_delivery_fulfilment_service", lambda settings: Service())
    monkeypatch.setattr(module, "build_delivery_id_allocator", lambda settings: _FakeAllocator())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    lines_file = _lines_file(tmp_path, [{
        "order_id": "ORD-000001", "order_line_id": "RO-000001", "quantity": "2.5",
        "unit": "GRAM", "expected_order_version": 0, "expected_order_line_version": 0,
    }])
    parser = main_module._parser(); namespace = parser.parse_args(args(lines_file))
    stdout, stderr = StringIO(), StringIO()
    assert run_delivery_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert "CONSEGNA_ID: CON-000001" in stdout.getvalue()
    assert "RIGHE: 1" in stdout.getvalue()
    assert "MOVIMENTI: 1" in stdout.getvalue()
    assert "ORDINE: ORD-000001 -> EVASO" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_cli_reuses_caller_supplied_consegna_and_movement_ids(monkeypatch, tmp_path):
    captured = {}

    class Service:
        def publish(self, command):
            captured["delivery_id"] = command.delivery_id
            captured["movement_id"] = command.lines[0].movement_id
            return DeliveryFulfilmentResult(
                delivery_id=command.delivery_id, order_states=(),
                delivery_line_count=1, movement_count=1,
            )
    import src.tpo_core.cli.delivery as module
    monkeypatch.setattr(module, "build_delivery_fulfilment_service", lambda settings: Service())
    monkeypatch.setattr(module, "build_delivery_id_allocator", lambda settings: _FakeAllocator())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    lines_file = _lines_file(tmp_path, [{
        "order_id": "ORD-000001", "order_line_id": "RO-000001", "quantity": "2.5",
        "unit": "GRAM", "expected_order_version": 0, "expected_order_line_version": 0,
        "movement_id": "MOV-000970",
    }])
    parser = main_module._parser()
    namespace = parser.parse_args(args(lines_file, "--consegna-id", "CON-000970"))
    stdout, stderr = StringIO(), StringIO()
    assert run_delivery_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert captured["delivery_id"] == ConsegnaId("CON-000970")
    assert captured["movement_id"] == MovimentoId("MOV-000970")


def test_cli_invalid_input_returns_input_exit(monkeypatch, tmp_path):
    lines_file = _lines_file(tmp_path, [{
        "order_id": "ORD-000001", "order_line_id": "RO-000001", "quantity": "0",
        "unit": "GRAM", "expected_order_version": 0, "expected_order_line_version": 0,
        "movement_id": "MOV-000001",
    }])
    import src.tpo_core.cli.delivery as module
    monkeypatch.setattr(module, "build_delivery_id_allocator", lambda settings: _FakeAllocator())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args(lines_file))
    stdout, stderr = StringIO(), StringIO()
    assert run_delivery_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "DELIVERY_FULFILMENT_FAILED" in stderr.getvalue()


def test_cli_reconciliation_required_reports_consegna_id_to_reconcile(monkeypatch, tmp_path):
    class Service:
        def publish(self, command):
            raise DeliveryCommitOutcomeUncertain("esito incerto")
    import src.tpo_core.cli.delivery as module
    monkeypatch.setattr(module, "build_delivery_fulfilment_service", lambda settings: Service())
    monkeypatch.setattr(module, "build_delivery_id_allocator", lambda settings: _FakeAllocator())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    lines_file = _lines_file(tmp_path, [{
        "order_id": "ORD-000001", "order_line_id": "RO-000001", "quantity": "2.5",
        "unit": "GRAM", "expected_order_version": 0, "expected_order_line_version": 0,
    }])
    parser = main_module._parser(); namespace = parser.parse_args(args(lines_file))
    stdout, stderr = StringIO(), StringIO()
    assert run_delivery_command(namespace, stdout=stdout, stderr=stderr) == 4
    assert "CONSEGNA_ID_DA_RICONCILIARE: CON-000001" in stderr.getvalue()
