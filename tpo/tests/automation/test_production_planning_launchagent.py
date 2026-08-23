from __future__ import annotations

from datetime import date, time
import importlib.util
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts/run_production_planning_schedule.sh"
HELPER = ROOT / "scripts/production_planning_occurrence.py"
INSTALLER = ROOT / "scripts/install_production_planning_launchagent.sh"
PLIST = ROOT / "deploy/macos/com.towerpower.production-planning-scheduler.plist"
OPERATIONAL_PLIST = ROOT / "deploy/macos/com.towerpower.operational-scheduler.plist"


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _project(
    tmp_path: Path, *, cli_exit: int = 0, canary_time: str = "06:30",
    stdout: str = "STATUS: COMMITTED", stderr: str = "",
) -> tuple[Path, dict[str, str], Path]:
    root = tmp_path / "project"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(LAUNCHER, scripts / LAUNCHER.name)
    shutil.copy2(HELPER, scripts / HELPER.name)
    secret = root / "runtime/secrets/production-planning-scheduler.env"
    secret.parent.mkdir(parents=True)
    secret.write_text(
        "TPO_DATABASE_HOST=localhost\nTPO_DATABASE_PORT=5432\n"
        "TPO_DATABASE_NAME=tower_test\nTPO_DATABASE_USER=tower\n"
        "TPO_DATABASE_PASSWORD=local-test-value\nTPO_DATABASE_SSLMODE=require\n"
        "TPO_DATABASE_CONNECT_TIMEOUT=5\n",
        encoding="utf-8",
    )
    secret.chmod(0o600)
    calls = tmp_path / "cli-calls.txt"
    _write_executable(
        root / ".venv/bin/python",
        """#!/bin/bash
if [ "$1" = "$FAKE_OCCURRENCE_HELPER" ]; then
  case "$2" in
    2026-01-15) printf '%s\n' '2026-01-15T06:30:00+00:00' ;;
    *) printf '%s\n' '2026-08-23T06:30:00+01:00' ;;
  esac
  exit 0
fi
printf '%s\n' "$*" >>"$FAKE_CLI_CALLS"
printf '%s\n' "$FAKE_CLI_STDOUT"
printf '%s\n' "$FAKE_CLI_STDERR" >&2
exit "$FAKE_CLI_EXIT"
""",
    )
    fake_bin = tmp_path / "fake-bin"
    _write_executable(
        fake_bin / "date",
        f"""#!/bin/bash
case "$1" in
  +%Y-%m-%d) printf '%s\n' '2026-08-23' ;;
  +%H:%M) printf '%s\n' '{canary_time}' ;;
  +%Y%m%dT%H%M%S) printf '%s\n' '20260823T063000' ;;
  *) printf '%s\n' '2026-08-23T06:30:00+0100' ;;
esac
""",
    )
    environment = os.environ.copy()
    environment.update({
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "FAKE_OCCURRENCE_HELPER": str(scripts / HELPER.name),
        "FAKE_CLI_CALLS": str(calls),
        "FAKE_CLI_EXIT": str(cli_exit),
        "FAKE_CLI_STDOUT": stdout,
        "FAKE_CLI_STDERR": stderr,
    })
    return root, environment, calls


def _run(root: Path, environment: dict[str, str]):
    return subprocess.run(
        [str(root / "scripts" / LAUNCHER.name)], env=environment,
        text=True, capture_output=True, check=False,
    )


def _logs(root: Path):
    return sorted((root / "runtime/logs").glob("production-planning-scheduler-*.log"))


@pytest.mark.parametrize("exit_code", range(6))
def test_exact_initial_only_command_once_and_exit_preserved(tmp_path: Path, exit_code: int):
    root, environment, calls = _project(tmp_path, cli_exit=exit_code)
    result = _run(root, environment)
    assert result.returncode == exit_code
    assert calls.read_text(encoding="utf-8").splitlines() == [
        "-m src.tpo_core.cli.main production-planning initial "
        "--business-at 2026-08-23T06:30:00+01:00 "
        "--policy-set-code DEFAULT --policy-version 1 "
        "--actor tpo.production-planning-scheduler "
        "--reason Automated Production Planning V1 "
        "--correlation-id production-planning-auto-v1:2026-08-23T06:30:00+01:00"
    ]
    assert "replan" not in calls.read_text(encoding="utf-8").lower()
    log = _logs(root)[0].read_text(encoding="utf-8")
    assert "ADAPTER_IDENTIFIER: com.towerpower.production-planning-scheduler" in log
    assert "CORRELATION_ID: production-planning-auto-v1:2026-08-23T06:30:00+01:00" in log
    assert f"EXIT_CODE: {exit_code}" in log


def test_overlap_and_missed_occurrence_fail_before_cli(tmp_path: Path):
    root, environment, calls = _project(tmp_path)
    lock = root / "runtime/production-planning-scheduler.lock"
    lock.mkdir()
    assert _run(root, environment).returncode == 1
    assert not calls.exists()
    lock.rmdir()
    environment["PATH"] = environment["PATH"]
    root2, environment2, calls2 = _project(tmp_path / "missed", canary_time="06:31")
    assert _run(root2, environment2).returncode == 1
    assert not calls2.exists()


def test_failure_is_not_retried_and_logging_is_sanitized(tmp_path: Path):
    root, environment, calls = _project(
        tmp_path, cli_exit=4,
        stdout="STATUS: RECONCILIATION_REQUIRED",
        stderr="password=secret\nTraceback provider internals\nlocal-test-value",
    )
    assert _run(root, environment).returncode == 4
    assert len(calls.read_text(encoding="utf-8").splitlines()) == 1
    log = _logs(root)[0].read_text(encoding="utf-8")
    assert "STATUS: RECONCILIATION_REQUIRED" in log
    assert "[REDACTED]" in log
    assert "password=secret" not in log and "Traceback" not in log
    assert "local-test-value" not in log


def test_plists_are_independent_and_operational_0600_is_unchanged():
    with PLIST.open("rb") as stream:
        planning = plistlib.load(stream)
    with OPERATIONAL_PLIST.open("rb") as stream:
        operational = plistlib.load(stream)
    assert planning["Label"] == "com.towerpower.production-planning-scheduler"
    assert planning["StartCalendarInterval"] == {"Hour": 6, "Minute": 30}
    assert planning["ProgramArguments"] == [
        "__TPO_ROOT__/scripts/run_production_planning_schedule.sh"
    ]
    assert operational["Label"] == "com.towerpower.operational-scheduler"
    assert operational["StartCalendarInterval"] == {"Hour": 6, "Minute": 0}


def test_occurrence_helper_is_deterministic_and_fails_closed_for_dst_edges():
    spec = importlib.util.spec_from_file_location("occurrence", HELPER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    winter = module.canonical_business_at(date(2026, 1, 15))
    summer = module.canonical_business_at(date(2026, 8, 23))
    assert winter == module.canonical_business_at(date(2026, 1, 15))
    assert winter == "2026-01-15T06:30:00+00:00"
    assert summer == "2026-08-23T06:30:00+01:00"
    assert winter != summer
    with pytest.raises(module.InvalidNominalOccurrenceError):
        module.canonical_business_at(
            date(2026, 3, 8), local_time=time(2, 30),
            timezone_name="America/New_York",
        )
    with pytest.raises(module.InvalidNominalOccurrenceError):
        module.canonical_business_at(
            date(2026, 11, 1), local_time=time(1, 30),
            timezone_name="America/New_York",
        )


def test_launcher_has_independent_boundaries_and_no_forbidden_dependencies():
    source = LAUNCHER.read_text(encoding="utf-8")
    assert "production-planning-scheduler.lock" in source
    assert "operational-scheduler.lock" not in source
    assert "production-planning-scheduler-" in source
    for forbidden in (
        "ProductionPlanningService", "tpo_core.application", "Engine",
        "Assembler", "google", "sheets", "event_engine", "replan",
    ):
        assert forbidden.lower() not in source.lower()


def test_installer_first_install_uses_one_bootstrap_without_host_mutation(tmp_path: Path):
    root, environment, _ = _project(tmp_path)
    (root / "deploy/macos").mkdir(parents=True)
    shutil.copy2(PLIST, root / "deploy/macos" / PLIST.name)
    shutil.copy2(INSTALLER, root / "scripts" / INSTALLER.name)
    home = tmp_path / "home"
    home.mkdir()
    calls = tmp_path / "launchctl-calls.txt"
    _write_executable(
        tmp_path / "fake-bin/launchctl",
        """#!/bin/bash
printf '%s\n' "$*" >>"$FAKE_LAUNCHCTL_CALLS"
case "$1" in print) exit 113 ;; bootstrap) exit 0 ;; esac
""",
    )
    environment.update({"HOME": str(home), "FAKE_LAUNCHCTL_CALLS": str(calls)})
    result = subprocess.run(
        [str(root / "scripts" / INSTALLER.name)], env=environment,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0
    installed = home / "Library/LaunchAgents" / PLIST.name
    assert installed.is_file()
    assert str(root) in installed.read_text(encoding="utf-8")
    recorded = calls.read_text(encoding="utf-8")
    assert recorded.count("bootstrap ") == 1
    assert "bootout " not in recorded


def test_installer_first_bootstrap_failure_restores_not_installed(tmp_path: Path):
    root, environment, _ = _project(tmp_path)
    (root / "deploy/macos").mkdir(parents=True)
    shutil.copy2(PLIST, root / "deploy/macos" / PLIST.name)
    shutil.copy2(INSTALLER, root / "scripts" / INSTALLER.name)
    home = tmp_path / "home"
    home.mkdir()
    calls = tmp_path / "launchctl-calls.txt"
    _write_executable(
        tmp_path / "fake-bin/launchctl",
        """#!/bin/bash
printf '%s\n' "$*" >>"$FAKE_LAUNCHCTL_CALLS"
case "$1" in print) exit 113 ;; bootstrap) exit 9 ;; esac
""",
    )
    environment.update({"HOME": str(home), "FAKE_LAUNCHCTL_CALLS": str(calls)})
    result = subprocess.run(
        [str(root / "scripts" / INSTALLER.name)], env=environment,
        text=True, capture_output=True, check=False,
    )
    assert result.returncode != 0
    assert not (home / "Library/LaunchAgents" / PLIST.name).exists()
    assert calls.read_text(encoding="utf-8").count("bootstrap ") == 1
