from __future__ import annotations

import pytest

from src.tpo_core.infrastructure.postgresql.errors import InvalidPostgreSQLSettingsError
from src.tpo_core.infrastructure.postgresql.settings import PostgreSQLSettings


VALID = {
    "host": "db.example.invalid",
    "port": "5432",
    "database": "towerpower",
    "user": "app",
    "password": "super-secret",
    "sslmode": "verify-full",
    "connect_timeout_seconds": "5",
}


def test_mapping_valido_e_immutabile() -> None:
    settings = PostgreSQLSettings.from_mapping(VALID)
    assert settings.port == 5432
    assert settings.connect_timeout_seconds == 5
    with pytest.raises(AttributeError):
        settings.host = "other"  # type: ignore[misc]


def test_environment_valido() -> None:
    environment = {
        "TPO_DATABASE_HOST": "db.example.invalid",
        "TPO_DATABASE_PORT": "5432",
        "TPO_DATABASE_NAME": "towerpower",
        "TPO_DATABASE_USER": "app",
        "TPO_DATABASE_PASSWORD": "super-secret",
        "TPO_DATABASE_SSLMODE": "require",
        "TPO_DATABASE_CONNECT_TIMEOUT": "4",
    }
    assert PostgreSQLSettings.from_environment(environment).database == "towerpower"


@pytest.mark.parametrize("missing", VALID)
def test_campo_obbligatorio_mancante(missing: str) -> None:
    values = dict(VALID)
    del values[missing]
    with pytest.raises(InvalidPostgreSQLSettingsError) as captured:
        PostgreSQLSettings.from_mapping(values)
    assert "super-secret" not in str(captured.value)


@pytest.mark.parametrize("port", [0, 65536, "abc", True])
def test_porta_non_valida(port: object) -> None:
    with pytest.raises(InvalidPostgreSQLSettingsError):
        PostgreSQLSettings.from_mapping({**VALID, "port": port})


@pytest.mark.parametrize("timeout", [0, -1, "abc", True])
def test_timeout_non_valido(timeout: object) -> None:
    with pytest.raises(InvalidPostgreSQLSettingsError):
        PostgreSQLSettings.from_mapping({**VALID, "connect_timeout_seconds": timeout})


def test_sslmode_non_valido() -> None:
    with pytest.raises(InvalidPostgreSQLSettingsError):
        PostgreSQLSettings.from_mapping({**VALID, "sslmode": "disable"})


def test_password_assente_da_repr_e_str() -> None:
    settings = PostgreSQLSettings.from_mapping(VALID)
    assert "super-secret" not in repr(settings)
    assert "super-secret" not in str(settings)
