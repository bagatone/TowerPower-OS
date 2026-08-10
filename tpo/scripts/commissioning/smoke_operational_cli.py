"""Smoke test manuale della CLI operativa durante il commissioning."""

from __future__ import annotations

import os
import subprocess

from secret_boundary import ROOT, load_postgresql_parameters


_TPO_DATABASE_KEYS = (
    "TPO_DATABASE_HOST",
    "TPO_DATABASE_PORT",
    "TPO_DATABASE_NAME",
    "TPO_DATABASE_USER",
    "TPO_DATABASE_PASSWORD",
    "TPO_DATABASE_SSLMODE",
    "TPO_DATABASE_CONNECT_TIMEOUT",
)


def main() -> int:
    parameters = load_postgresql_parameters()

    child_environment = os.environ.copy()
    for key in _TPO_DATABASE_KEYS:
        child_environment.pop(key, None)

    child_environment.update(
        {
            "TPO_DATABASE_HOST": parameters["host"],
            "TPO_DATABASE_PORT": parameters["port"],
            "TPO_DATABASE_NAME": parameters["dbname"],
            "TPO_DATABASE_USER": parameters["user"],
            "TPO_DATABASE_PASSWORD": parameters["password"],
            "TPO_DATABASE_SSLMODE": parameters["sslmode"],
            "TPO_DATABASE_CONNECT_TIMEOUT": parameters["connect_timeout"],
        }
    )

    completed = subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            "-m",
            "src.tpo_core.cli.main",
            "schedule",
            "execute",
            "--settings",
            str(ROOT / "config" / "settings.yaml"),
            "--business-date",
            "2026-08-10",
            "--business-time",
            "06:00",
            "--identity",
            "towerpower-scheduler",
            "--confirm",
        ],
        cwd=ROOT,
        env=child_environment,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
