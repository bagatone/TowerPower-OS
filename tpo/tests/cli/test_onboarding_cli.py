from argparse import Namespace
from io import StringIO

import pytest

from src.tpo_core.application.onboarding.models import OnboardingResult
from src.tpo_core.cli.onboarding import run_onboarding_command


def args():
    return Namespace(
        onboarding_command="variety", actor="owner", reason="commission code",
        correlation_id="traceability:test", variety_id="VAR-000001",
        denomination="Cilantro", state="ATTIVA", traceability_code="CIL",
    )


@pytest.mark.parametrize(("result", "expected"), [
    (OnboardingResult("VARIETA", "VAR-000001", True), "STATUS: INSERTED"),
    (OnboardingResult("VARIETA", "VAR-000001", False, True), "STATUS: UPDATED"),
    (OnboardingResult("VARIETA", "VAR-000001", False), "STATUS: COMPATIBLE_REPLAY"),
])
def test_cli_renders_truthful_onboarding_outcome(monkeypatch, result, expected):
    class Service:
        def commission_variety(self, command):
            return result

    monkeypatch.setattr(
        "src.tpo_core.cli.onboarding.build_operational_data_onboarding_service",
        lambda settings: Service(),
    )
    monkeypatch.setattr(
        "src.tpo_core.cli.onboarding.PostgreSQLSettings.from_environment",
        lambda: object(),
    )
    stdout, stderr = StringIO(), StringIO()
    assert run_onboarding_command(args(), stdout=stdout, stderr=stderr) == 0
    assert expected in stdout.getvalue()
    assert stderr.getvalue() == ""
