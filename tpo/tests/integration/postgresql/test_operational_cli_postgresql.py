"""Acceptance reale, opt-in, dell'adapter CLI operativo PostgreSQL."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from zoneinfo import ZoneInfo

from alembic import command
import psycopg
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url

from src.tpo_core.bootstrap import container as container_module
from src.tpo_core.cli import main as main_module
from src.tpo_core.infrastructure.postgresql.alembic import make_config


DATABASE_URL = os.environ.get("TPO_TEST_DATABASE_URL")
TZ = ZoneInfo("Atlantic/Canary")


def _instant(day: int, hour: int) -> datetime:
    return datetime(2026, 8, day, hour, tzinfo=TZ)


def _validated_database_url() -> str:
    assert DATABASE_URL is not None
    parsed = urlparse(DATABASE_URL)
    database_name = unquote(parsed.path.lstrip("/").split("?", 1)[0])
    if not database_name or "test" not in database_name.lower():
        pytest.fail(
            "TPO_TEST_DATABASE_URL deve indicare un database dedicato contenente 'test'."
        )
    return DATABASE_URL


def _sqlalchemy_psycopg_url(url: str) -> URL:
    parsed = make_url(url)
    if parsed.drivername == "postgresql":
        return parsed.set(drivername="postgresql+psycopg")
    if parsed.drivername == "postgresql+psycopg":
        return parsed
    raise ValueError("TPO_TEST_DATABASE_URL usa un dialect PostgreSQL non autorizzato.")


def _postgresql_environment(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if parsed.hostname is None or parsed.username is None or parsed.password is None:
        pytest.fail("TPO_TEST_DATABASE_URL non contiene credenziali PostgreSQL complete.")
    sslmode = query.get("sslmode", ["require"])[0]
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        pytest.fail("Il database test deve usare una modalità SSL supportata dal runtime.")
    return {
        "TPO_DATABASE_HOST": parsed.hostname,
        "TPO_DATABASE_PORT": str(parsed.port or 5432),
        "TPO_DATABASE_NAME": unquote(parsed.path.lstrip("/")),
        "TPO_DATABASE_USER": unquote(parsed.username),
        "TPO_DATABASE_PASSWORD": unquote(parsed.password),
        "TPO_DATABASE_SSLMODE": sslmode,
        "TPO_DATABASE_CONNECT_TIMEOUT": query.get("connect_timeout", ["5"])[0],
    }


def _settings_file(tmp_path: Path) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(
        """google_sheets:
  spreadsheet_id: integration-test
  credentials_file: unused.json
  scopes: [https://www.googleapis.com/auth/spreadsheets]
  sheets: [PROGRAMMI_FORNITURA, ORDINI]
""",
        encoding="utf-8",
    )
    return path


def _seed(connection) -> None:
    created_at = _instant(8, 4)
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO tpo.clienti
               (public_id, denominazione, created_at, created_by, updated_at,
                updated_by, version)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                "CLI-920001",
                "Cliente acceptance CLI",
                created_at,
                "cli-acceptance",
                created_at,
                "cli-acceptance",
                0,
            ),
        )
        cursor.execute(
            """INSERT INTO tpo.varieta
               (public_id, denominazione, stato, created_at, created_by,
                updated_at, updated_by, version)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                "VAR-920001",
                "Varietà acceptance CLI",
                "ATTIVA",
                created_at,
                "cli-acceptance",
                created_at,
                "cli-acceptance",
                0,
            ),
        )
        cursor.execute(
            """INSERT INTO tpo.programmi_fornitura
               (public_id, cliente_id, created_by)
               SELECT %s, id, %s FROM tpo.clienti WHERE public_id = %s
               RETURNING id""",
            ("PF-920001", "cli-acceptance", "CLI-920001"),
        )
        program_id = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO tpo.programmi_fornitura_versioni
               (programma_fornitura_id, cliente_id, numero_versione, stato,
                data_inizio, data_fine, orario_generazione,
                finestra_operativa_giorni, valida_dal, valida_al, created_by)
               SELECT %s, id, %s, %s, %s, NULL, %s, %s, %s, NULL, %s
               FROM tpo.clienti WHERE public_id = %s RETURNING id""",
            (
                program_id,
                1,
                "ATTIVO",
                date(2026, 8, 9),
                "14:00:00",
                0,
                _instant(8, 1),
                "cli-acceptance",
                "CLI-920001",
            ),
        )
        version_id = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO tpo.righe_programma_fornitura
               (programma_versione_id, posizione, varieta_id, quantita,
                unita_misura, tipo_ricorrenza, intervallo_giorni)
               SELECT %s, %s, id, %s, %s, %s, %s FROM tpo.varieta
               WHERE public_id = %s""",
            (
                version_id,
                1,
                Decimal("2.5"),
                "GRAM",
                "OGNI_X_GIORNI",
                1,
                "VAR-920001",
            ),
        )
        for sequence_name, identifier_type, prefix in (
            ("ORDINE_ID", "OrdineId", "ORD"),
            ("RUN_ID", "RunId", "RUN"),
        ):
            cursor.execute(
                """INSERT INTO tpo.id_sequences
                   (sequence_name, identifier_type, prefix, next_value, version,
                    updated_at, updated_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    sequence_name,
                    identifier_type,
                    prefix,
                    920001,
                    0,
                    created_at,
                    "cli-acceptance",
                ),
            )
    connection.commit()


def _execute_arguments(settings: Path) -> list[str]:
    return [
        "schedule",
        "execute",
        "--settings",
        str(settings),
        "--business-date",
        "2026-08-09",
        "--business-time",
        "14:35",
        "--identity",
        "operational-cli-e2e",
        "--confirm",
    ]


def _forbid_google_construction(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def forbidden(*args, **kwargs):
        calls.append("google")
        raise AssertionError("Il runtime operativo non deve costruire Google.")

    for name in (
        "GoogleApiSheetsGateway",
        "GoogleSheetsProgrammaFornituraRepository",
        "GoogleSheetsOrdineRepository",
    ):
        monkeypatch.setattr(container_module, name, forbidden)
    return calls


def _assert_public_output_is_sanitized(
    stdout: str, stderr: str, *, url: str
) -> None:
    password = urlparse(url).password
    combined = stdout + stderr
    assert url not in combined
    if password:
        assert unquote(password) not in combined
    for forbidden in ("Traceback", "technical_cause", "SELECT ", "INSERT INTO"):
        assert forbidden not in combined


@pytest.mark.postgresql_integration
@pytest.mark.skipif(
    not DATABASE_URL,
    reason="TPO_TEST_DATABASE_URL non configurata: PostgreSQL reale non eseguito.",
)
def test_operational_cli_postgresql_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    url = _validated_database_url()
    environment = _postgresql_environment(url)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    google_calls = _forbid_google_construction(monkeypatch)
    settings = _settings_file(tmp_path)
    engine = sa.create_engine(_sqlalchemy_psycopg_url(url))
    migrated = False
    admin = None
    try:
        with engine.connect() as connection:
            if sa.inspect(connection).has_schema("tpo"):
                pytest.fail("Lo schema tpo esiste già: è richiesto un database test vuoto.")
            command.upgrade(make_config(connection=connection), "head")
            connection.commit()
            migrated = True

        admin = psycopg.connect(url)
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()"
            )
            assert cursor.fetchone() == (True,)
        _seed(admin)

        exit_code = main_module.main(_execute_arguments(settings))
        first = capsys.readouterr()
        assert exit_code == 0
        assert "STATUS: COMMITTED" in first.out
        assert "RUN_ID: RUN-920001" in first.out
        assert "WARNINGS:" in first.out
        assert "OPERATION_COMMITTED" not in first.out
        assert first.err == ""
        _assert_public_output_is_sanitized(first.out, first.err, url=url)

        with admin.cursor() as cursor:
            cursor.execute(
                """SELECT started_at, completed_at, simulation, state,
                          programmi_letti, righe_valutate, occorrenze_valutate,
                          ordini_generati, elementi_saltati, version
                   FROM tpo.runs WHERE public_id = %s""",
                ("RUN-920001",),
            )
            run = cursor.fetchone()
            assert run[0] is not None and run[1] is not None
            assert run[0] <= run[1]
            assert run[2:] == (False, "SUCCESS", 1, 1, 1, 1, 0, 1)

            cursor.execute(
                """SELECT o.public_id, c.public_id, p.public_id, r.public_id,
                          o.data_ordine, o.data_consegna_prevista,
                          o.tipo_creazione, o.created_at, o.created_by,
                          o.chiave_idempotenza
                   FROM tpo.ordini o
                   JOIN tpo.clienti c ON c.id = o.cliente_id
                   JOIN tpo.programmi_fornitura p
                     ON p.id = o.programma_fornitura_id
                   JOIN tpo.runs r ON r.id = o.run_id"""
            )
            order = cursor.fetchone()
            assert order[:7] == (
                "ORD-920001",
                "CLI-920001",
                "PF-920001",
                "RUN-920001",
                date(2026, 8, 9),
                date(2026, 8, 9),
                "AUTOMATICO",
            )
            assert run[0] <= run[1] <= order[7]
            assert order[8] == "operational-cli-e2e"
            assert isinstance(order[9], str) and order[9]

            cursor.execute(
                """SELECT ro.posizione, v.public_id, ro.quantita, ro.unita_misura
                   FROM tpo.righe_ordine ro
                   JOIN tpo.varieta v ON v.id = ro.varieta_id"""
            )
            assert cursor.fetchall() == [
                (1, "VAR-920001", Decimal("2.500000"), "GRAM")
            ]
            cursor.execute(
                """SELECT ro.posizione, pv.numero_versione, rp.posizione
                   FROM tpo.origini_righe_ordine oro
                   JOIN tpo.righe_ordine ro ON ro.id = oro.riga_ordine_id
                   JOIN tpo.righe_programma_fornitura rp
                     ON rp.id = oro.riga_programma_id
                   JOIN tpo.programmi_fornitura_versioni pv
                     ON pv.id = rp.programma_versione_id"""
            )
            assert cursor.fetchall() == [(1, 1, 1)]
            cursor.execute("SELECT tipo, posizione, messaggio FROM tpo.run_messaggi")
            assert cursor.fetchall() == []
            cursor.execute(
                """SELECT entity_type, entity_public_id, operation, actor,
                          reason, correlation_id, before_data, after_data
                   FROM tpo.audit_eventi ORDER BY id"""
            )
            audits = cursor.fetchall()
            assert [row[:3] for row in audits] == [
                ("ORDINE", "ORD-920001", "INSERT"),
                ("RUN", "RUN-920001", "STATE_TRANSITION"),
            ]
            assert all(row[3] == "operational-cli-e2e" for row in audits)
            assert all(row[4] == "operational scheduling" for row in audits)
            correlation_ids = {row[5] for row in audits}
            assert len(correlation_ids) == 1 and next(iter(correlation_ids))
            assert audits[0][6] is None
            assert all("id" not in payload for row in audits for payload in row[6:] if payload)
            cursor.execute(
                """SELECT identifier_type, next_value, version
                   FROM tpo.id_sequences ORDER BY identifier_type"""
            )
            assert cursor.fetchall() == [
                ("OrdineId", 920002, 1),
                ("RunId", 920002, 1),
            ]

        duplicate_exit = main_module.main(_execute_arguments(settings))
        duplicate = capsys.readouterr()
        assert duplicate_exit == 1
        assert "STATUS: FAILED" in duplicate.out
        assert "RUN_ID: RUN-920002" in duplicate.out
        assert duplicate.err == ""
        _assert_public_output_is_sanitized(duplicate.out, duplicate.err, url=url)

        with admin.cursor() as cursor:
            for table, expected in (
                ("ordini", 1),
                ("righe_ordine", 1),
                ("origini_righe_ordine", 1),
                ("audit_eventi", 2),
            ):
                cursor.execute(sa.text(f"SELECT count(*) FROM tpo.{table}").text)
                assert cursor.fetchone() == (expected,)
            cursor.execute(
                """SELECT public_id, state, version FROM tpo.runs
                   ORDER BY public_id"""
            )
            assert cursor.fetchall() == [
                ("RUN-920001", "SUCCESS", 1),
                ("RUN-920002", "FAILED", 1),
            ]
            cursor.execute("SELECT count(*) FROM tpo.runs")
            runs_before_invalid_input = cursor.fetchone()[0]

        invalid_argument_sets = (
            ["--business-time", "24:00"],
            ["--identity", ""],
            ["--confirm"],
        )
        valid_arguments = _execute_arguments(settings)
        for replacement in invalid_argument_sets:
            invalid = list(valid_arguments)
            option = replacement[0]
            index = invalid.index(option)
            if option == "--confirm":
                invalid.pop(index)
            else:
                invalid[index + 1] = replacement[1]
            assert main_module.main(invalid) == 2
            captured = capsys.readouterr()
            assert "COMMITTED" not in captured.out
            _assert_public_output_is_sanitized(captured.out, captured.err, url=url)

        with admin.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM tpo.runs")
            assert cursor.fetchone() == (runs_before_invalid_input,)
        assert google_calls == []
    finally:
        if admin is not None:
            admin.close()
        if migrated:
            with engine.connect() as connection:
                command.downgrade(make_config(connection=connection), "base")
                connection.commit()
        engine.dispose()


@pytest.mark.parametrize(
    "arguments_transform",
    (
        lambda args: args[: args.index("--business-time") + 1]
        + ["24:00"]
        + args[args.index("--business-time") + 2 :],
        lambda args: args[: args.index("--identity") + 1]
        + [""]
        + args[args.index("--identity") + 2 :],
        lambda args: [item for item in args if item != "--confirm"],
    ),
)
def test_operational_cli_input_invalid_offline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    arguments_transform,
) -> None:
    exit_code = main_module.main(arguments_transform(_execute_arguments(_settings_file(tmp_path))))
    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "OPERATION_INPUT_INVALID" in captured.err or "Errore di utilizzo" in captured.err


def test_operational_cli_runtime_unavailable_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for key in (
        "TPO_DATABASE_HOST",
        "TPO_DATABASE_PORT",
        "TPO_DATABASE_NAME",
        "TPO_DATABASE_USER",
        "TPO_DATABASE_PASSWORD",
        "TPO_DATABASE_SSLMODE",
        "TPO_DATABASE_CONNECT_TIMEOUT",
    ):
        monkeypatch.delenv(key, raising=False)
    google_calls = _forbid_google_construction(monkeypatch)

    exit_code = main_module.main(_execute_arguments(_settings_file(tmp_path)))
    captured = capsys.readouterr()

    assert exit_code == 3
    assert captured.out == ""
    assert captured.err.strip() == "OPERATION_RUNTIME_UNAVAILABLE"
    assert google_calls == []
