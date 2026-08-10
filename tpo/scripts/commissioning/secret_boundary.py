"""Secret Boundary condiviso dalle utility di commissioning PostgreSQL."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Final


ROOT: Final = Path(__file__).resolve().parents[2]
SECRET_PATH: Final = ROOT / "runtime" / "secrets" / "operational-scheduler.env"

_ALLOWED_KEYS: Final = frozenset(
    {
        "TPO_DATABASE_HOST",
        "TPO_DATABASE_PORT",
        "TPO_DATABASE_NAME",
        "TPO_DATABASE_USER",
        "TPO_DATABASE_PASSWORD",
        "TPO_DATABASE_SSLMODE",
        "TPO_DATABASE_CONNECT_TIMEOUT",
    }
)


class SecretBoundaryError(RuntimeError):
    """Il Secret Boundary locale non rispetta il contratto congelato."""


def load_postgresql_parameters() -> dict[str, str]:
    """Valida il Secret Boundary e restituisce parametri adatti a psycopg."""

    for key in _ALLOWED_KEYS:
        os.environ.pop(key, None)

    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(SECRET_PATH, flags)
    except OSError as exc:
        raise SecretBoundaryError("operational secrets unavailable") from exc

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise SecretBoundaryError("operational secrets must be a regular file")
        if metadata.st_uid != os.geteuid():
            raise SecretBoundaryError("operational secrets owner invalid")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise SecretBoundaryError("operational secrets mode must be 0600")

        with os.fdopen(descriptor, "r", encoding="utf-8", newline="") as handle:
            descriptor = -1
            content = handle.read()
    except (OSError, UnicodeError) as exc:
        raise SecretBoundaryError("operational secrets unreadable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    values: dict[str, str] = {}
    for line_number, line in enumerate(content.split("\n"), start=1):
        if line == "" or line.startswith("#"):
            continue
        if "=" not in line:
            raise SecretBoundaryError(
                f"operational secrets syntax invalid at line {line_number}"
            )

        key, value = line.split("=", 1)
        if key not in _ALLOWED_KEYS:
            raise SecretBoundaryError(
                f"operational secrets key invalid at line {line_number}"
            )
        if key in values:
            raise SecretBoundaryError(
                f"operational secrets duplicate key at line {line_number}"
            )
        if value == "" or value[0].isspace():
            raise SecretBoundaryError(
                f"operational secrets value invalid at line {line_number}"
            )
        values[key] = value

    if values.keys() != _ALLOWED_KEYS:
        raise SecretBoundaryError("operational secrets required keys missing")

    return {
        "host": values["TPO_DATABASE_HOST"],
        "port": values["TPO_DATABASE_PORT"],
        "dbname": values["TPO_DATABASE_NAME"],
        "user": values["TPO_DATABASE_USER"],
        "password": values["TPO_DATABASE_PASSWORD"],
        "sslmode": values["TPO_DATABASE_SSLMODE"],
        "connect_timeout": values["TPO_DATABASE_CONNECT_TIMEOUT"],
    }
