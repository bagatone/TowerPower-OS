from datetime import datetime, timezone
from io import StringIO
import json

from src.tpo_core.application.seed_lot_commissioning.models import (
    FACT_FIELDS, CommissionSeedLotResult,
)
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.seed_lot import run_seed_lot_command
from src.tpo_core.domain.identifiers import LottoSemeId


def args(*extra):
    provenance = {field: ("UNKNOWN" if field in {"expiry_date", "anomaly"}
                          else "OWNER_AUTHORIZED") for field in FACT_FIELDS}
    return [
        "seed-lot", "commission", "--seed-supplier", "Supplier",
        "--seed-commercial-reference", "REF-1", "--manufacturer-lot-number", "LOT-1",
        "--received-date", "2026-08-24", "--initial-quantity", "10.123456",
        "--unit", "GRAM", "--provenance", json.dumps(provenance),
        "--actor", "owner", "--reason", "commission", "--correlation-id", "corr-1",
        "--idempotency-key", "key-1", "--confirm", *extra,
    ]


def test_parser_registers_frozen_seed_lot_command(monkeypatch):
    received = []
    monkeypatch.setattr(main_module, "run_seed_lot_command", lambda a, **k: received.append(a) or 0)
    assert main_module.main(args()) == 0
    assert received[0].seed_lot_command == "commission"
    assert received[0].unit == "GRAM"
    assert received[0].confirm is True


def test_missing_required_input_fails_before_runtime(monkeypatch):
    monkeypatch.setattr(main_module, "run_seed_lot_command", lambda *a, **k: 99)
    assert main_module.main(["seed-lot", "commission"]) == 2


def test_cli_happy_path_is_thin(monkeypatch):
    class Service:
        def commission(self, command):
            return CommissionSeedLotResult(
                LottoSemeId("LSE-000001"), "INSERTED", command.seed_supplier,
                command.seed_commercial_reference, command.manufacturer_lot_number,
                command.initial_quantity, command.initial_quantity,
                command.received_date, command.expiry_date, datetime.now(timezone.utc),
            )
    import src.tpo_core.cli.seed_lot as module
    monkeypatch.setattr(module, "build_seed_lot_commissioning_service", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    parser = main_module._parser(); namespace = parser.parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_seed_lot_command(namespace, stdout=stdout, stderr=stderr) == 0
    assert "PUBLIC_ID: LSE-000001" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_cli_invalid_provenance_returns_input_exit(monkeypatch):
    parser = main_module._parser(); argv = args()
    argv[argv.index("--provenance") + 1] = "{}"
    namespace = parser.parse_args(argv); stdout, stderr = StringIO(), StringIO()
    assert run_seed_lot_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "SEED_LOT_INPUT_INVALID" in stderr.getvalue()
