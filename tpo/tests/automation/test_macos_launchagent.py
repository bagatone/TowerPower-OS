from __future__ import annotations

import os
from pathlib import Path
import plistlib
import shutil
import signal
import stat
import subprocess
import time

import pytest


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts/run_operational_schedule.sh"
INSTALLER = ROOT / "scripts/install_operational_launchagent.sh"
UNINSTALLER = ROOT / "scripts/uninstall_operational_launchagent.sh"
PLIST = ROOT / "deploy/macos/com.towerpower.operational-scheduler.plist"
POSTGRESQL_KEYS = (
    "TPO_DATABASE_HOST",
    "TPO_DATABASE_PORT",
    "TPO_DATABASE_NAME",
    "TPO_DATABASE_USER",
    "TPO_DATABASE_PASSWORD",
    "TPO_DATABASE_SSLMODE",
    "TPO_DATABASE_CONNECT_TIMEOUT",
)


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _project(
    tmp_path: Path,
    *,
    cli_exit: int = 0,
    canary_time: str = "06:00",
    settings: bool = True,
    stdout: str = "STATUS: COMMITTED",
    stderr: str = "",
    secrets: bool = True,
    root_name: str = "project",
    cli_delay: str = "0",
) -> tuple[Path, dict[str, str], Path]:
    root = tmp_path / root_name
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(LAUNCHER, scripts / LAUNCHER.name)
    (root / "config").mkdir()
    if settings:
        (root / "config/settings.yaml").write_text("local: true\n", encoding="utf-8")
    if secrets:
        secret_file = root / "runtime/secrets/operational-scheduler.env"
        secret_file.parent.mkdir(parents=True)
        secret_file.write_text(
            "TPO_DATABASE_HOST=localhost\n"
            "TPO_DATABASE_PORT=5432\n"
            "TPO_DATABASE_NAME=tower_test\n"
            "TPO_DATABASE_USER=tower\n"
            "TPO_DATABASE_PASSWORD=local-test-value\n"
            "TPO_DATABASE_SSLMODE=require\n"
            "TPO_DATABASE_CONNECT_TIMEOUT=5\n",
            encoding="utf-8",
        )
        secret_file.chmod(0o600)

    calls = tmp_path / "cli-calls.txt"
    fake_python = root / ".venv/bin/python"
    _write_executable(
        fake_python,
        """#!/bin/bash
printf '%s\n' "$*" >>"$FAKE_CLI_CALLS"
if [ -n "${FAKE_ENV_CALLS:-}" ]; then
  printf '%s\n' \
    "TPO_DATABASE_HOST=$TPO_DATABASE_HOST" \
    "TPO_DATABASE_PORT=$TPO_DATABASE_PORT" \
    "TPO_DATABASE_NAME=$TPO_DATABASE_NAME" \
    "TPO_DATABASE_USER=$TPO_DATABASE_USER" \
    "TPO_DATABASE_PASSWORD=$TPO_DATABASE_PASSWORD" \
    "TPO_DATABASE_SSLMODE=$TPO_DATABASE_SSLMODE" \
    "TPO_DATABASE_CONNECT_TIMEOUT=$TPO_DATABASE_CONNECT_TIMEOUT" \
    >"$FAKE_ENV_CALLS"
fi
sleep "${FAKE_CLI_DELAY:-0}"
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
  +%Y-%m-%d) printf '%s\n' '2026-08-10' ;;
  +%H:%M) printf '%s\n' '{canary_time}' ;;
  +%Y%m%dT%H%M%S) printf '%s\n' '20260810T060000' ;;
  *) printf '%s\n' '2026-08-10T06:00:00+0100' ;;
esac
""",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:/usr/bin:/bin",
            "FAKE_CLI_CALLS": str(calls),
            "FAKE_CLI_EXIT": str(cli_exit),
            "FAKE_CLI_STDOUT": stdout,
            "FAKE_CLI_STDERR": stderr,
            "FAKE_CLI_DELAY": cli_delay,
        }
    )
    return root, environment, calls


def _run_launcher(root: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(root / "scripts/run_operational_schedule.sh")],
        cwd=root.parent,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _logs(root: Path) -> list[Path]:
    return sorted((root / "runtime/logs").glob("operational-scheduler-*.log"))


def test_launcher_esiste_ed_e_eseguibile() -> None:
    assert LAUNCHER.is_file()
    assert os.access(LAUNCHER, os.X_OK)


@pytest.mark.parametrize("exit_code", range(6))
def test_comando_esatto_e_exit_cli_propagato(
    tmp_path: Path, exit_code: int
) -> None:
    root, environment, calls = _project(tmp_path, cli_exit=exit_code)

    result = _run_launcher(root, environment)

    assert result.returncode == exit_code
    recorded = calls.read_text(encoding="utf-8").splitlines()
    assert len(recorded) == 1
    assert recorded[0] == (
        "-m src.tpo_core.cli.main schedule execute "
        f"--settings {root}/config/settings.yaml "
        "--business-date 2026-08-10 --business-time 06:00 "
        "--identity towerpower-scheduler --confirm"
    )
    log = _logs(root)[0].read_text(encoding="utf-8")
    assert "INVOCATION_TIMESTAMP: 2026-08-10T06:00:00+0100" in log
    assert "ADAPTER_IDENTIFIER: com.towerpower.operational-scheduler" in log
    assert "BUSINESS_DATE: 2026-08-10" in log
    assert "BUSINESS_TIME: 06:00" in log
    assert f"EXIT_CODE: {exit_code}" in log
    assert "STATUS: COMMITTED" in log


def test_settings_assenti_non_invocano_cli_o_template(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path, settings=False)
    (root / "config/settings.example.yaml").write_text(
        "template: true\n", encoding="utf-8"
    )

    result = _run_launcher(root, environment)

    assert result.returncode == 2
    assert not calls.exists()
    assert not (root / "config/settings.yaml").exists()
    log = _logs(root)[0].read_text(encoding="utf-8")
    assert "OPERATION_INPUT_INVALID" in log
    assert "settings.example" not in log


def test_virtualenv_assente_non_invoca_cli(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path)
    (root / ".venv/bin/python").unlink()

    result = _run_launcher(root, environment)

    assert result.returncode == 3
    assert not calls.exists()


def test_secrets_assenti_non_invocano_cli(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path, secrets=False)

    result = _run_launcher(root, environment)

    assert result.returncode == 2
    assert not calls.exists()


def test_secrets_con_permessi_non_sicuri_non_invocano_cli(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path)
    (root / "runtime/secrets/operational-scheduler.env").chmod(0o640)

    result = _run_launcher(root, environment)

    assert result.returncode == 2
    assert not calls.exists()


def test_environment_parser_esporta_solo_valori_letterali_autorizzati(
    tmp_path: Path,
) -> None:
    root, environment, _ = _project(tmp_path)
    captured = tmp_path / "environment.txt"
    environment["FAKE_ENV_CALLS"] = str(captured)

    assert _run_launcher(root, environment).returncode == 0
    assert captured.read_text(encoding="utf-8").splitlines() == [
        "TPO_DATABASE_HOST=localhost",
        "TPO_DATABASE_PORT=5432",
        "TPO_DATABASE_NAME=tower_test",
        "TPO_DATABASE_USER=tower",
        "TPO_DATABASE_PASSWORD=local-test-value",
        "TPO_DATABASE_SSLMODE=require",
        "TPO_DATABASE_CONNECT_TIMEOUT=5",
    ]


@pytest.mark.parametrize(
    "invalid_line",
    ("UNAUTHORIZED=value", "export TPO_DATABASE_HOST=localhost"),
)
def test_environment_parser_rifiuta_formato_non_autorizzato(
    tmp_path: Path, invalid_line: str
) -> None:
    root, environment, calls = _project(tmp_path)
    secret_file = root / "runtime/secrets/operational-scheduler.env"
    secret_file.write_text(f"{invalid_line}\n", encoding="utf-8")

    result = _run_launcher(root, environment)

    assert result.returncode == 2
    assert not calls.exists()
    assert not (root / "forbidden").exists()


def test_file_secrets_sostituisce_interamente_environment_ereditato(
    tmp_path: Path,
) -> None:
    root, environment, _ = _project(tmp_path)
    captured = tmp_path / "environment.txt"
    environment["FAKE_ENV_CALLS"] = str(captured)
    for key in POSTGRESQL_KEYS:
        environment[key] = "inherited-value"

    assert _run_launcher(root, environment).returncode == 0

    values = captured.read_text(encoding="utf-8")
    assert "inherited-value" not in values
    assert "TPO_DATABASE_PASSWORD=local-test-value" in values


@pytest.mark.parametrize("missing_key", POSTGRESQL_KEYS)
def test_ogni_chiave_obbligatoria_mancante_blocca_cli(
    tmp_path: Path, missing_key: str
) -> None:
    root, environment, calls = _project(tmp_path)
    secret_file = root / "runtime/secrets/operational-scheduler.env"
    lines = secret_file.read_text(encoding="utf-8").splitlines()
    secret_file.write_text(
        "\n".join(line for line in lines if not line.startswith(f"{missing_key}="))
        + "\n",
        encoding="utf-8",
    )
    environment[missing_key] = "inherited-fallback"

    result = _run_launcher(root, environment)

    assert result.returncode == 2
    assert not calls.exists()


@pytest.mark.parametrize("empty_key", POSTGRESQL_KEYS)
def test_ogni_valore_obbligatorio_vuoto_blocca_cli(
    tmp_path: Path, empty_key: str
) -> None:
    root, environment, calls = _project(tmp_path)
    secret_file = root / "runtime/secrets/operational-scheduler.env"
    lines = secret_file.read_text(encoding="utf-8").splitlines()
    secret_file.write_text(
        "\n".join(
            f"{empty_key}=" if line.startswith(f"{empty_key}=") else line
            for line in lines
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_launcher(root, environment)

    assert result.returncode == 2
    assert not calls.exists()


def test_chiave_duplicata_blocca_cli(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path)
    secret_file = root / "runtime/secrets/operational-scheduler.env"
    with secret_file.open("a", encoding="utf-8") as stream:
        stream.write("TPO_DATABASE_HOST=duplicate.invalid\n")

    assert _run_launcher(root, environment).returncode == 2
    assert not calls.exists()


@pytest.mark.parametrize(
    "invalid_line",
    (
        " TPO_DATABASE_HOST=localhost",
        "TPO_DATABASE_HOST =localhost",
        "TPO_DATABASE_HOST= localhost",
        "TPO_DATABASE_HOST = localhost",
    ),
)
def test_whitespace_sintattico_blocca_cli(
    tmp_path: Path, invalid_line: str
) -> None:
    root, environment, calls = _project(tmp_path)
    secret_file = root / "runtime/secrets/operational-scheduler.env"
    lines = secret_file.read_text(encoding="utf-8").splitlines()
    lines[0] = invalid_line
    secret_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert _run_launcher(root, environment).returncode == 2
    assert not calls.exists()


def test_commenti_e_valori_speciali_restano_letterali(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path)
    captured = tmp_path / "environment.txt"
    environment["FAKE_ENV_CALLS"] = str(captured)
    secret_file = root / "runtime/secrets/operational-scheduler.env"
    special = "$`(){ }#&!*$(touch forbidden)"
    lines = secret_file.read_text(encoding="utf-8").splitlines()
    lines.insert(0, "# full-line comment")
    lines = [
        f"TPO_DATABASE_PASSWORD={special}"
        if line.startswith("TPO_DATABASE_PASSWORD=")
        else line
        for line in lines
    ]
    secret_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert _run_launcher(root, environment).returncode == 0
    assert f"TPO_DATABASE_PASSWORD={special}" in captured.read_text(encoding="utf-8")
    assert not (root / "forbidden").exists()
    assert calls.is_file()


def test_secret_non_regular_blocca_cli(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path)
    secret_file = root / "runtime/secrets/operational-scheduler.env"
    secret_file.unlink()
    secret_file.mkdir()

    assert _run_launcher(root, environment).returncode == 2
    assert not calls.exists()


def test_secret_non_leggibile_blocca_cli(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path)
    (root / "runtime/secrets/operational-scheduler.env").chmod(0o000)

    assert _run_launcher(root, environment).returncode == 2
    assert not calls.exists()


def test_errore_parser_non_espone_linea_o_valore_segreto(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path)
    secret_file = root / "runtime/secrets/operational-scheduler.env"
    forbidden_value = "DO_NOT_LOG_THIS_SECRET"
    with secret_file.open("a", encoding="utf-8") as stream:
        stream.write(f"UNKNOWN_KEY={forbidden_value}\n")

    assert _run_launcher(root, environment).returncode == 2
    assert not calls.exists()
    log = _logs(root)[0].read_text(encoding="utf-8")
    assert forbidden_value not in log
    assert "UNKNOWN_KEY=" not in log


def test_settings_non_leggibili_non_invocano_cli(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path)
    (root / "config/settings.yaml").chmod(0o000)

    assert _run_launcher(root, environment).returncode == 2
    assert not calls.exists()


def test_path_applicativo_con_spazi(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path, root_name="Tower Power OS")

    assert _run_launcher(root, environment).returncode == 0
    assert f"--settings {root}/config/settings.yaml" in calls.read_text(encoding="utf-8")


def test_business_date_usa_timezone_canary_e_nessun_catchup(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path, canary_time="06:01")

    result = _run_launcher(root, environment)

    assert result.returncode != 0
    assert not calls.exists()
    assert "MISSED_EXECUTION" in _logs(root)[0].read_text(encoding="utf-8")
    date_source = (tmp_path / "fake-bin/date").read_text(encoding="utf-8")
    launcher_source = (root / "scripts/run_operational_schedule.sh").read_text(
        encoding="utf-8"
    )
    assert "TZ=Atlantic/Canary date '+%Y-%m-%d'" in launcher_source
    assert "2026-08-10" in date_source
    assert "+00:00" not in launcher_source


def test_lock_esistente_blocca_cli_senza_rimozione(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path)
    lock = root / "runtime/operational-scheduler.lock"
    lock.mkdir(parents=True)

    result = _run_launcher(root, environment)

    assert result.returncode != 0
    assert not calls.exists()
    assert lock.is_dir()
    assert "OVERLAP_BLOCKED" in _logs(root)[0].read_text(encoding="utf-8")


def test_lock_acquisito_viene_rilasciato(tmp_path: Path) -> None:
    root, environment, _ = _project(tmp_path)

    assert _run_launcher(root, environment).returncode == 0

    assert not (root / "runtime/operational-scheduler.lock").exists()


def _wait_for_path(path: Path) -> None:
    deadline = time.monotonic() + 3
    while not path.exists():
        if time.monotonic() >= deadline:
            raise AssertionError(f"Timed out waiting for {path}")
        time.sleep(0.01)


def test_due_processi_concorrenti_invocano_cli_una_sola_volta(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path, cli_delay="0.5")
    first = subprocess.Popen(
        [str(root / "scripts/run_operational_schedule.sh")],
        cwd=root.parent,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _wait_for_path(root / "runtime/operational-scheduler.lock")

    second = _run_launcher(root, environment)
    first_return = first.wait(timeout=3)

    assert first_return == 0
    assert second.returncode != 0
    assert len(calls.read_text(encoding="utf-8").splitlines()) == 1


def test_segnale_gestibile_rilascia_lock(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path, cli_delay="10")
    process = subprocess.Popen(
        [str(root / "scripts/run_operational_schedule.sh")],
        cwd=root.parent,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    lock = root / "runtime/operational-scheduler.lock"
    _wait_for_path(calls)

    os.killpg(process.pid, signal.SIGTERM)
    process.wait(timeout=15)

    assert not lock.exists()


def test_segnale_nella_vera_finestra_mkdir_owner_non_lascia_lock(
    tmp_path: Path,
) -> None:
    root, environment, calls = _project(tmp_path)
    _write_executable(
        tmp_path / "fake-bin/mkdir",
        """#!/bin/bash
last_argument="${!#}"
if [[ "$last_argument" == *operational-scheduler.lock ]]; then
  /bin/mkdir "$@" || exit 1
  kill -TERM "$PPID"
  exit 0
fi
exec /bin/mkdir "$@"
""",
    )

    result = _run_launcher(root, environment)

    assert result.returncode != 0
    assert not calls.exists()
    assert not (root / "runtime/operational-scheduler.lock").exists()


def test_owner_marker_failure_non_lascia_lock(tmp_path: Path) -> None:
    root, environment, calls = _project(tmp_path)
    _write_executable(
        tmp_path / "fake-bin/mkdir",
        """#!/bin/bash
last_argument="${!#}"
/bin/mkdir "$@" || exit 1
if [[ "$last_argument" == *operational-scheduler.lock ]]; then
  /bin/chmod 500 "$last_argument"
fi
""",
    )

    result = _run_launcher(root, environment)

    assert result.returncode != 0
    assert not calls.exists()
    assert not (root / "runtime/operational-scheduler.lock").exists()


def test_lock_preesistente_con_pid_coincidente_non_viene_rimosso(
    tmp_path: Path,
) -> None:
    root, environment, calls = _project(tmp_path)
    wrapper = tmp_path / "launch-with-colliding-owner"
    _write_executable(
        wrapper,
        f"""#!/bin/bash
lock={root}/runtime/operational-scheduler.lock
/bin/mkdir -p "$lock"
printf '%s\n' "$$" >"$lock/owner"
exec {root}/scripts/run_operational_schedule.sh
""",
    )

    result = subprocess.run(
        [str(wrapper)], env=environment, text=True, capture_output=True, check=False
    )

    lock = root / "runtime/operational-scheduler.lock"
    assert result.returncode != 0
    assert not calls.exists()
    assert lock.is_dir()
    assert (lock / "owner").is_file()


def test_log_sanitizzato(tmp_path: Path) -> None:
    sensitive_lines = "\n".join(
        (
            "postgres://user:secret@db.invalid/tower",
            "postgres" + "ql://user:secret@db.invalid/tower",
            "pass" + "word=secret",
            "host=db dbname=tower user=app",
            "isolated local-test-value payload",
            "SELECT * FROM private_table",
            "prefix INSERT INTO private_table",
            "prefix UPDATE private_table",
            "prefix DELETE FROM private_table",
            "prefix WITH private_query",
            "prefix CREATE TABLE private_table",
            "prefix ALTER TABLE private_table",
            "prefix DROP TABLE private_table",
            "prefix TRUNCATE private_table",
            "prefix GRANT SELECT private_table",
            "prefix REVOKE SELECT private_table",
            "technical" + "_cause: private",
            "Trace" + "back: private",
            "postgresql+psycopg://user:VERY_SECRET_VALUE@localhost/test",
        )
    )
    root, environment, _ = _project(
        tmp_path, stdout=sensitive_lines, stderr=sensitive_lines
    )

    assert _run_launcher(root, environment).returncode == 0

    log = _logs(root)[0].read_text(encoding="utf-8")
    assert log.count("[REDACTED]") == len(sensitive_lines.splitlines()) * 2
    for forbidden in (
        "secret", "VERY_SECRET_VALUE", "private_table", "technical_cause",
        "Traceback", "host=db", "local-test-value",
    ):
        assert forbidden not in log


def test_retention_rimuove_solo_log_scheduler_oltre_trenta_giorni(
    tmp_path: Path,
) -> None:
    root, environment, _ = _project(tmp_path)
    log_dir = root / "runtime/logs"
    log_dir.mkdir(parents=True)
    old_scheduler = log_dir / "operational-scheduler-old.log"
    recent_scheduler = log_dir / "operational-scheduler-recent.log"
    unrelated = log_dir / "application-old.log"
    for path in (old_scheduler, recent_scheduler, unrelated):
        path.write_text("keep-or-remove\n", encoding="utf-8")
    old = time.time() - 32 * 24 * 60 * 60
    os.utime(old_scheduler, (old, old))
    os.utime(unrelated, (old, old))

    assert _run_launcher(root, environment).returncode == 0

    assert not old_scheduler.exists()
    assert recent_scheduler.exists()
    assert unrelated.exists()


def test_plist_launchagent_schedule_e_confini() -> None:
    with PLIST.open("rb") as stream:
        plist = plistlib.load(stream)

    assert plist["Label"] == "com.towerpower.operational-scheduler"
    assert plist["ProgramArguments"] == [
        "__TPO_ROOT__/scripts/run_operational_schedule.sh"
    ]
    assert plist["StartCalendarInterval"] == {"Hour": 6, "Minute": 0}
    assert "KeepAlive" not in plist
    assert "StartInterval" not in plist
    assert set(plist) <= {
        "Label",
        "ProgramArguments",
        "StartCalendarInterval",
        "WorkingDirectory",
        "StandardOutPath",
        "StandardErrorPath",
    }


def test_installer_materializza_solo_launchagent_utente(tmp_path: Path) -> None:
    root, environment, _ = _project(tmp_path)
    (root / "deploy/macos").mkdir(parents=True)
    shutil.copy2(PLIST, root / "deploy/macos" / PLIST.name)
    shutil.copy2(INSTALLER, root / "scripts" / INSTALLER.name)
    home = tmp_path / "home"
    home.mkdir()
    launchctl_calls = tmp_path / "launchctl-calls.txt"
    _write_executable(
        tmp_path / "fake-bin/launchctl",
        """#!/bin/bash
printf '%s\n' "$*" >>"$FAKE_LAUNCHCTL_CALLS"
case "$1" in
  print) exit 113 ;;
  bootstrap) exit 0 ;;
esac
""",
    )
    environment.update(
        {"HOME": str(home), "FAKE_LAUNCHCTL_CALLS": str(launchctl_calls)}
    )

    result = subprocess.run(
        [str(root / "scripts" / INSTALLER.name)],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    installed = home / "Library/LaunchAgents" / PLIST.name
    assert installed.is_file()
    installed_text = installed.read_text(encoding="utf-8")
    assert "__TPO_ROOT__" not in installed_text
    assert str(root) in installed_text
    calls_text = launchctl_calls.read_text(encoding="utf-8")
    assert calls_text.count("bootout ") == 0
    assert calls_text.count("bootstrap ") == 1
    assert (root / "runtime/logs").is_dir()


def test_uninstaller_preserva_settings_e_log(tmp_path: Path) -> None:
    root, environment, _ = _project(tmp_path)
    shutil.copy2(UNINSTALLER, root / "scripts" / UNINSTALLER.name)
    home = tmp_path / "home"
    target = home / "Library/LaunchAgents" / PLIST.name
    target.parent.mkdir(parents=True)
    target.write_bytes(PLIST.read_bytes())
    log = root / "runtime/logs/preserved.log"
    log.parent.mkdir(parents=True)
    log.write_text("preserved\n", encoding="utf-8")
    _write_executable(tmp_path / "fake-bin/launchctl", "#!/bin/bash\nexit 0\n")
    environment["HOME"] = str(home)

    result = subprocess.run(
        [str(root / "scripts" / UNINSTALLER.name)],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert not target.exists()
    assert (root / "config/settings.yaml").is_file()
    assert (root / "runtime/secrets/operational-scheduler.env").is_file()
    assert log.is_file()


def _fake_launchctl(
    path: Path,
    *,
    print_exit: int,
    bootout_exit: int = 0,
    bootstrap_exits: tuple[int, ...] = (0,),
) -> None:
    bootstrap_cases = "\n".join(
        f"  {index}) exit {exit_code} ;;"
        for index, exit_code in enumerate(bootstrap_exits, start=1)
    )
    fallback_exit = bootstrap_exits[-1]
    _write_executable(
        path,
        f"""#!/bin/bash
printf '%s\n' "$*" >>"$FAKE_LAUNCHCTL_CALLS"
case "$1" in
  print) exit {print_exit} ;;
  bootout) exit {bootout_exit} ;;
  bootstrap)
    count=0
    if [ -f "$FAKE_BOOTSTRAP_COUNT" ]; then read -r count <"$FAKE_BOOTSTRAP_COUNT"; fi
    count=$((count + 1))
    printf '%s\n' "$count" >"$FAKE_BOOTSTRAP_COUNT"
    case "$count" in
{bootstrap_cases}
      *) exit {fallback_exit} ;;
    esac
    ;;
esac
""",
    )


def _installer_project(tmp_path: Path) -> tuple[Path, dict[str, str], Path, Path]:
    root, environment, _ = _project(tmp_path)
    (root / "deploy/macos").mkdir(parents=True)
    shutil.copy2(PLIST, root / "deploy/macos" / PLIST.name)
    shutil.copy2(INSTALLER, root / "scripts" / INSTALLER.name)
    home = tmp_path / "home"
    target = home / "Library/LaunchAgents" / PLIST.name
    target.parent.mkdir(parents=True)
    calls = tmp_path / "launchctl-calls.txt"
    environment.update(
        {
            "HOME": str(home),
            "FAKE_LAUNCHCTL_CALLS": str(calls),
            "FAKE_BOOTSTRAP_COUNT": str(tmp_path / "bootstrap-count.txt"),
        }
    )
    return root, environment, calls, target


def _run_installer(
    root: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(root / "scripts" / INSTALLER.name)],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _fake_counted_command(
    path: Path,
    *,
    real_command: str,
    counter_variable: str,
    fail_on: tuple[int, ...],
) -> None:
    failure_cases = "\n".join(f"  {count}) exit 9 ;;" for count in fail_on)
    _write_executable(
        path,
        f"""#!/bin/bash
counter_file="${{{counter_variable}}}"
count=0
if [ -f "$counter_file" ]; then read -r count <"$counter_file"; fi
count=$((count + 1))
printf '%s\n' "$count" >"$counter_file"
case "$count" in
{failure_cases}
esac
exec {real_command} "$@"
""",
    )


def _backup_files(target: Path) -> list[Path]:
    return sorted(target.parent.glob(".com.towerpower.operational-scheduler.backup.*"))


@pytest.mark.parametrize(
    "relative_path",
    ("config/settings.yaml", "runtime/secrets/operational-scheduler.env"),
)
def test_installer_rifiuta_file_operativo_non_leggibile(
    tmp_path: Path, relative_path: str
) -> None:
    root, environment, calls, _ = _installer_project(tmp_path)
    (root / relative_path).chmod(0o000)
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=113)

    result = subprocess.run(
        [str(root / "scripts" / INSTALLER.name)], env=environment, check=False
    )

    assert result.returncode == 2
    assert not calls.exists()


def test_candidate_materialization_failure_non_muta_installazione(tmp_path: Path) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    _write_executable(tmp_path / "fake-bin/sed", "#!/bin/bash\nexit 9\n")
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=113)

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert not target.exists()
    assert not calls.exists()


def test_candidate_plutil_failure_non_muta_installazione(tmp_path: Path) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    _write_executable(
        tmp_path / "fake-bin/plutil",
        """#!/bin/bash
if [ "$1" = "-lint" ]; then exit 9; fi
exec /usr/bin/plutil "$@"
""",
    )
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=113)

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert not target.exists()
    assert not calls.exists()


def test_backup_failure_non_muta_installazione(tmp_path: Path) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    old_bytes = PLIST.read_bytes()
    target.write_bytes(old_bytes)
    _write_executable(tmp_path / "fake-bin/cp", "#!/bin/bash\nexit 9\n")
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0)

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert target.read_bytes() == old_bytes
    recorded = calls.read_text(encoding="utf-8")
    assert "bootout " not in recorded
    assert "bootstrap " not in recorded


def test_replacement_failure_ripristina_job_precedentemente_loaded(
    tmp_path: Path,
) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    old_bytes = PLIST.read_bytes()
    target.write_bytes(old_bytes)
    environment["FAKE_MV_COUNT"] = str(tmp_path / "mv-count.txt")
    _fake_counted_command(
        tmp_path / "fake-bin/mv",
        real_command="/bin/mv",
        counter_variable="FAKE_MV_COUNT",
        fail_on=(1,),
    )
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0)

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert target.read_bytes() == old_bytes
    recorded = calls.read_text(encoding="utf-8")
    assert recorded.count("bootout ") == 1
    assert recorded.count("bootstrap ") == 1
    assert "ROLLBACK SUCCESSFUL" in result.stderr
    assert not _backup_files(target)


def test_bootstrap_nuovo_fallito_ripristina_plist_e_job_loaded(
    tmp_path: Path,
) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    old_bytes = PLIST.read_bytes()
    target.write_bytes(old_bytes)
    settings = root / "config/settings.yaml"
    secrets = root / "runtime/secrets/operational-scheduler.env"
    settings_before = settings.read_bytes()
    secrets_before = secrets.read_bytes()
    log = root / "runtime/logs/preserved.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("preserved\n", encoding="utf-8")
    _fake_launchctl(
        tmp_path / "fake-bin/launchctl",
        print_exit=0,
        bootstrap_exits=(9, 0),
    )

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert target.read_bytes() == old_bytes
    assert settings.read_bytes() == settings_before
    assert secrets.read_bytes() == secrets_before
    assert log.read_text(encoding="utf-8") == "preserved\n"
    recorded = calls.read_text(encoding="utf-8")
    assert recorded.count("bootout ") == 1
    assert recorded.count("bootstrap ") == 2
    assert "ROLLBACK SUCCESSFUL" in result.stderr
    assert not _backup_files(target)


def test_bootstrap_nuovo_fallito_non_carica_job_precedentemente_unloaded(
    tmp_path: Path,
) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    old_bytes = PLIST.read_bytes()
    target.write_bytes(old_bytes)
    _fake_launchctl(
        tmp_path / "fake-bin/launchctl", print_exit=113, bootstrap_exits=(9,)
    )

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert target.read_bytes() == old_bytes
    recorded = calls.read_text(encoding="utf-8")
    assert "bootout " not in recorded
    assert recorded.count("bootstrap ") == 1


def test_rollback_restore_failure_richiede_recovery_manuale(tmp_path: Path) -> None:
    root, environment, _, target = _installer_project(tmp_path)
    target.write_bytes(PLIST.read_bytes())
    environment["FAKE_MV_COUNT"] = str(tmp_path / "mv-count.txt")
    _fake_counted_command(
        tmp_path / "fake-bin/mv",
        real_command="/bin/mv",
        counter_variable="FAKE_MV_COUNT",
        fail_on=(2,),
    )
    _fake_launchctl(
        tmp_path / "fake-bin/launchctl", print_exit=0, bootstrap_exits=(9,)
    )

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert "ROLLBACK FAILED" in result.stderr
    assert "MANUAL RECOVERY REQUIRED" in result.stderr
    assert (tmp_path / "mv-count.txt").read_text(encoding="utf-8").strip() == "2"
    assert len(_backup_files(target)) == 1


def test_rollback_rebootstrap_failure_non_viene_ripetuto(tmp_path: Path) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    old_bytes = PLIST.read_bytes()
    target.write_bytes(old_bytes)
    _fake_launchctl(
        tmp_path / "fake-bin/launchctl",
        print_exit=0,
        bootstrap_exits=(9, 8),
    )

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert target.read_bytes() == old_bytes
    assert calls.read_text(encoding="utf-8").count("bootstrap ") == 2
    assert "ROLLBACK FAILED" in result.stderr
    assert "MANUAL RECOVERY REQUIRED" in result.stderr
    assert len(_backup_files(target)) == 1


def test_first_install_bootstrap_failure_rimuove_plist_una_volta(
    tmp_path: Path,
) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    _fake_launchctl(
        tmp_path / "fake-bin/launchctl", print_exit=113, bootstrap_exits=(9,)
    )

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert not target.exists()
    assert calls.read_text(encoding="utf-8").count("bootstrap ") == 1
    assert "state is Not Installed" in result.stderr


def test_first_install_cleanup_failure_non_viene_ripetuta(tmp_path: Path) -> None:
    root, environment, _, target = _installer_project(tmp_path)
    environment["FAKE_RM_COUNT"] = str(tmp_path / "rm-count.txt")
    _fake_counted_command(
        tmp_path / "fake-bin/rm",
        real_command="/bin/rm",
        counter_variable="FAKE_RM_COUNT",
        fail_on=(1,),
    )
    _fake_launchctl(
        tmp_path / "fake-bin/launchctl", print_exit=113, bootstrap_exits=(9,)
    )

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert target.exists()
    assert (tmp_path / "rm-count.txt").read_text(encoding="utf-8").strip() == "1"
    assert "CLEANUP FAILED" in result.stderr
    assert "MANUAL RECOVERY REQUIRED" in result.stderr


def test_reinstall_success_elimina_backup_ed_e_deterministica(tmp_path: Path) -> None:
    root, environment, _, target = _installer_project(tmp_path)
    target.write_bytes(PLIST.read_bytes())
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0)

    first = _run_installer(root, environment)
    first_bytes = target.read_bytes()
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0)
    second = _run_installer(root, environment)

    assert first.returncode == 0
    assert second.returncode == 0
    assert target.read_bytes() == first_bytes
    assert not _backup_files(target)


def test_launchctl_state_indeterminabile_non_avvia_mutation(tmp_path: Path) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    old_bytes = PLIST.read_bytes()
    target.write_bytes(old_bytes)
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=7)

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert target.read_bytes() == old_bytes
    assert calls.read_text(encoding="utf-8").splitlines() == [
        f"print gui/{os.getuid()}/com.towerpower.operational-scheduler"
    ]
    assert "state query failed" in result.stderr


def test_backup_cleanup_failure_ripristina_intero_stato_loaded(
    tmp_path: Path,
) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    old_bytes = b"<?xml version='1.0'?><plist><dict><key>Label</key><string>com.towerpower.operational-scheduler</string></dict></plist>"
    target.write_bytes(old_bytes)
    environment["FAKE_RM_COUNT"] = str(tmp_path / "rm-count.txt")
    _fake_counted_command(
        tmp_path / "fake-bin/rm",
        real_command="/bin/rm",
        counter_variable="FAKE_RM_COUNT",
        fail_on=(1,),
    )
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0)

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert target.read_bytes() == old_bytes
    recorded = calls.read_text(encoding="utf-8")
    assert recorded.count("bootout ") == 2
    assert recorded.count("bootstrap ") == 2
    assert "ROLLBACK SUCCESSFUL" in result.stderr
    assert not _backup_files(target)


def test_first_install_signal_dopo_bootstrap_esegue_bootout_e_cleanup_una_volta(
    tmp_path: Path,
) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    loaded = tmp_path / "fake-loaded-state"
    environment["FAKE_LOADED_STATE"] = str(loaded)
    _write_executable(
        tmp_path / "fake-bin/launchctl",
        """#!/bin/bash
printf '%s\n' "$*" >>"$FAKE_LAUNCHCTL_CALLS"
case "$1" in
  print) [ -f "$FAKE_LOADED_STATE" ] && exit 0 || exit 113 ;;
  bootstrap) /usr/bin/touch "$FAKE_LOADED_STATE"; kill -TERM "$PPID"; exit 0 ;;
  bootout) /bin/rm -f "$FAKE_LOADED_STATE"; exit 0 ;;
esac
""",
    )

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert not loaded.exists()
    assert not target.exists()
    recorded = calls.read_text(encoding="utf-8")
    assert recorded.count("bootstrap ") == 1
    assert recorded.count("bootout ") == 1
    assert recorded.count("print ") == 2
    assert "LaunchAgent installed" not in result.stdout


def test_signal_dopo_backup_validato_prima_mutation_elimina_backup(
    tmp_path: Path,
) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    old_bytes = PLIST.read_bytes()
    target.write_bytes(old_bytes)
    environment["FAKE_CHMOD_COUNT"] = str(tmp_path / "chmod-count.txt")
    _write_executable(
        tmp_path / "fake-bin/chmod",
        """#!/bin/bash
count=0
if [ -f "$FAKE_CHMOD_COUNT" ]; then read -r count <"$FAKE_CHMOD_COUNT"; fi
count=$((count + 1))
printf '%s\n' "$count" >"$FAKE_CHMOD_COUNT"
/bin/chmod "$@" || exit 1
if [ "$count" -eq 2 ]; then kill -TERM "$PPID"; fi
""",
    )
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0)

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert target.read_bytes() == old_bytes
    assert not _backup_files(target)
    recorded = calls.read_text(encoding="utf-8")
    assert "bootout " not in recorded
    assert "bootstrap " not in recorded


@pytest.mark.parametrize("signal_stage", ("validation", "pre_mutation", "mutation"))
def test_installer_signal_termina_senza_continuation_e_compensa_una_volta(
    tmp_path: Path, signal_stage: str
) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    if signal_stage != "validation":
        target.write_bytes(PLIST.read_bytes())
    if signal_stage == "validation":
        _write_executable(
            tmp_path / "fake-bin/sed",
            "#!/bin/bash\n/usr/bin/sed \"$@\"\nkill -TERM \"$PPID\"\n",
        )
        _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0)
    elif signal_stage == "pre_mutation":
        _write_executable(
            tmp_path / "fake-bin/cp",
            "#!/bin/bash\n/bin/cp \"$@\"\nkill -TERM \"$PPID\"\n",
        )
        _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0)
    else:
        _write_executable(
            tmp_path / "fake-bin/launchctl",
            """#!/bin/bash
printf '%s\n' "$*" >>"$FAKE_LAUNCHCTL_CALLS"
case "$1" in
  print) exit 0 ;;
  bootout) kill -TERM "$PPID"; exit 0 ;;
  bootstrap) exit 0 ;;
esac
""",
        )

    result = _run_installer(root, environment)

    assert result.returncode != 0
    recorded = calls.read_text(encoding="utf-8") if calls.exists() else ""
    if signal_stage in ("validation", "pre_mutation"):
        assert "bootout " not in recorded
        assert "bootstrap " not in recorded
    else:
        assert recorded.count("bootout ") == 1
        assert recorded.count("bootstrap ") == 1
        assert not _backup_files(target)
    assert "LaunchAgent installed" not in result.stdout


@pytest.mark.parametrize(
    "command", ("sed", "plutil", "cp", "chmod", "mv", "launchctl", "rm")
)
def test_stderr_tecnico_esterno_non_bypassa_diagnostica(
    tmp_path: Path, command: str
) -> None:
    root, environment, _, target = _installer_project(tmp_path)
    raw = "RAW_PRIVATE_postgresql://user:secret@db.invalid/tower"
    if command in ("cp", "mv", "rm"):
        target.write_bytes(PLIST.read_bytes())
    if command == "sed":
        _write_executable(tmp_path / "fake-bin/sed", f"#!/bin/bash\nprintf '%s\\n' '{raw}' >&2\nexit 9\n")
        _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=113)
    elif command == "plutil":
        _write_executable(tmp_path / "fake-bin/plutil", f"#!/bin/bash\nprintf '%s\\n' '{raw}' >&2\nexit 9\n")
        _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=113)
    elif command == "cp":
        _write_executable(tmp_path / "fake-bin/cp", f"#!/bin/bash\nprintf '%s\\n' '{raw}' >&2\nexit 9\n")
        _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0)
    elif command == "chmod":
        _write_executable(tmp_path / "fake-bin/chmod", f"#!/bin/bash\nprintf '%s\\n' '{raw}' >&2\nexit 9\n")
        _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=113)
    elif command == "mv":
        _write_executable(tmp_path / "fake-bin/mv", f"#!/bin/bash\nprintf '%s\\n' '{raw}' >&2\nexit 9\n")
        _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0)
    elif command == "launchctl":
        _write_executable(tmp_path / "fake-bin/launchctl", f"#!/bin/bash\nprintf '%s\\n' '{raw}' >&2\nexit 7\n")
    else:
        environment["FAKE_RM_COUNT"] = str(tmp_path / "rm-count.txt")
        _write_executable(tmp_path / "fake-bin/rm", f"#!/bin/bash\nprintf '%s\\n' '{raw}' >&2\nexit 9\n")
        _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0)

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert raw not in result.stderr
    assert "postgresql://" not in result.stderr
    assert "com.towerpower.operational-scheduler" in result.stderr


def test_installer_failure_diagnostics_non_espongono_secrets_o_dsn(
    tmp_path: Path,
) -> None:
    root, environment, _, target = _installer_project(tmp_path)
    target.write_bytes(PLIST.read_bytes())
    secret_file = root / "runtime/secrets/operational-scheduler.env"
    secret_text = secret_file.read_text(encoding="utf-8").replace(
        "local-test-value", "postgresql://user:DO_NOT_EXPOSE@db.invalid/tower"
    )
    secret_file.write_text(secret_text, encoding="utf-8")
    _fake_launchctl(
        tmp_path / "fake-bin/launchctl", print_exit=0, bootstrap_exits=(9, 0)
    )

    result = _run_installer(root, environment)

    assert result.returncode != 0
    assert "DO_NOT_EXPOSE" not in result.stderr
    assert "postgresql://" not in result.stderr
    assert "com.towerpower.operational-scheduler" in result.stderr


def test_reinstallazione_esegue_un_bootout_e_un_bootstrap(tmp_path: Path) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    target.write_bytes(PLIST.read_bytes())
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0)

    result = subprocess.run([str(root / "scripts" / INSTALLER.name)], env=environment, check=False)

    assert result.returncode == 0
    recorded = calls.read_text(encoding="utf-8")
    assert recorded.count("bootout ") == 1
    assert recorded.count("bootstrap ") == 1


def test_reinstallazione_accetta_job_non_caricato(tmp_path: Path) -> None:
    root, environment, calls, target = _installer_project(tmp_path)
    target.write_bytes(PLIST.read_bytes())
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=113)

    result = subprocess.run([str(root / "scripts" / INSTALLER.name)], env=environment, check=False)

    assert result.returncode == 0
    assert "bootout " not in calls.read_text(encoding="utf-8")


def test_errore_bootout_preserva_file_operativi(tmp_path: Path) -> None:
    root, environment, _, target = _installer_project(tmp_path)
    target.write_bytes(PLIST.read_bytes())
    log = root / "runtime/logs/preserved.log"
    log.parent.mkdir(parents=True)
    log.write_text("preserved\n", encoding="utf-8")
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0, bootout_exit=9)

    result = subprocess.run([str(root / "scripts" / INSTALLER.name)], env=environment, check=False)

    assert result.returncode != 0
    assert (root / "config/settings.yaml").is_file()
    assert (root / "runtime/secrets/operational-scheduler.env").is_file()
    assert log.is_file()
    assert target.is_file()


def test_uninstaller_propaga_errore_bootout_e_preserva_tutto(tmp_path: Path) -> None:
    root, environment, _, target = _installer_project(tmp_path)
    shutil.copy2(UNINSTALLER, root / "scripts" / UNINSTALLER.name)
    target.write_bytes(PLIST.read_bytes())
    log = root / "runtime/logs/preserved.log"
    log.parent.mkdir(parents=True)
    log.write_text("preserved\n", encoding="utf-8")
    _fake_launchctl(tmp_path / "fake-bin/launchctl", print_exit=0, bootout_exit=9)

    result = subprocess.run([str(root / "scripts" / UNINSTALLER.name)], env=environment, check=False)

    assert result.returncode != 0
    assert target.is_file()
    assert (root / "config/settings.yaml").is_file()
    assert (root / "runtime/secrets/operational-scheduler.env").is_file()
    assert log.is_file()


def test_nuovi_adapter_non_conoscono_application_google_o_database() -> None:
    launcher = LAUNCHER.read_text(encoding="utf-8")
    assert "src.tpo_core.cli.main" in launcher
    for forbidden in (
        "tpo_core.application",
        "OperationalSchedulingEntryPoint",
        "OperationalSchedulingOrchestrator",
        "PostgreSQLCommitRepository",
        "Google",
    ):
        assert forbidden not in launcher


def test_script_installazione_e_rimozione_non_elevano_privilegi() -> None:
    forbidden = "su" + "do"
    assert forbidden not in INSTALLER.read_text(encoding="utf-8")
    assert forbidden not in UNINSTALLER.read_text(encoding="utf-8")
