from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

from src.tpo_core.application.agronomic_commissioning.models import CommissionedAgronomicProtocol
from src.tpo_core.cli import main as main_module
from src.tpo_core.cli.protocollo import run_protocollo_command


def args(*extra):
    return ["protocollo", "commission",
            "--variety-id", "VAR-000007", "--variety-name", "Rucola",
            "--cultivar-name", "Rucola", "--productive-use-code", "MICROGREEN",
            "--productive-use-name", "Microgreens",
            "--protocol-name", "Tower Power standard Rucola",
            "--protocol-version-id", "PV-000008", "--version", "1",
            "--valid-from", "2026-10-01",
            "--hydration-hours", "0", "--planned-sowing-time", "09:00",
            "--target-harvest-time", "09:00", "--germination-days", "5",
            "--light-growth-days", "7", "--seed-grams-per-set", "7",
            "--expected-yield", "1", "--production-granularity", "0.5",
            "--harvest-min-lead-days", "1", "--harvest-max-lead-days", "1",
            "--temporal-buffer-minutes", "0",
            "--content", "Owner-authorized protocol", "--motivation", "Initial commissioning",
            "--provenance", "OWNER_AUTHORIZED_REAL_GROWING_PROTOCOL_2026-10",
            "--actor", "tpo.owner", "--reason", "Initial real agronomic protocol commissioning",
            "--correlation-id", "real-agronomic-protocol-v1:rucola", "--confirm", *extra]


def test_parser_registers_protocollo_commission():
    namespace = main_module._parser().parse_args(args())
    assert namespace.protocollo_command == "commission" and namespace.confirm
    assert namespace.variety_id == "VAR-000007"


def test_happy_path_is_thin(monkeypatch):
    class Service:
        def commission(self, command):
            return CommissionedAgronomicProtocol(
                command, datetime.now(timezone.utc),
                ("CULTIVAR", "CULTIVAR_USO", "PROTOCOLLO", "PROTOCOLLO_VERSIONE"),
            )
    import src.tpo_core.cli.protocollo as module
    monkeypatch.setattr(module, "build_agronomic_protocol_commissioner", lambda settings: Service())
    monkeypatch.setattr(module.PostgreSQLSettings, "from_environment", lambda: object())
    namespace = main_module._parser().parse_args(args())
    stdout, stderr = StringIO(), StringIO()
    assert run_protocollo_command(namespace, stdout=stdout, stderr=stderr) == 0
    out = stdout.getvalue()
    assert "PUBLIC_ID: PV-000008" in out and "INSERTED_ENTITIES: CULTIVAR,CULTIVAR_USO,PROTOCOLLO,PROTOCOLLO_VERSIONE" in out
    assert stderr.getvalue() == ""


def test_invalid_version_fails_before_runtime():
    bad = args(); bad[bad.index("--version") + 1] = "2"
    namespace = main_module._parser().parse_args(bad)
    stdout, stderr = StringIO(), StringIO()
    assert run_protocollo_command(namespace, stdout=stdout, stderr=stderr) == 2
    assert "AGRONOMIC_PROTOCOL_INPUT_INVALID" in stderr.getvalue()
