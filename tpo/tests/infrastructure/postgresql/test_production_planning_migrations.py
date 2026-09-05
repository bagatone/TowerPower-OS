from __future__ import annotations

import importlib.util
from io import StringIO
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
from decimal import Decimal

from alembic import command
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa

from src.tpo_core.infrastructure.postgresql.alembic import make_config

ROOT = Path(__file__).parents[3]
VERSIONS = ROOT / "migrations/versions"
PATHS = [
    VERSIONS / "20260811_0005_production_planning_foundation.py",
    VERSIONS / "20260811_0006_production_planning_plan.py",
    VERSIONS / "20260811_0007_production_planning_allocations.py",
    VERSIONS / "20260811_0008_production_calendar_view.py",
    VERSIONS / "20260814_0010_allocation_quantitative_lifecycle.py",
    VERSIONS / "20260814_0011_replanning_allocation_snapshot_balances.py",
    VERSIONS / "20260814_0012_audit_provenance.py",
    VERSIONS / "20260815_0013_zero_production_planning_lines.py",
    VERSIONS / "20260822_0014_replanning_disposition_authority.py",
]
PLANNING_TABLES = {
    "production_planning_policy_versions", "production_planning_runs",
    "production_planning_run_messaggi", "production_planning_run_log",
    "piani_produzione", "piano_produzione_revisioni", "righe_piano_semina",
    "risorse_seme_pianificate", "allocazioni", "allocazioni_domanda",
    "allocazioni_stock", "allocazioni_produzione_in_corso",
    "allocazioni_raccolta", "righe_piano_semina_semine",
    "replanning_snapshots", "replanning_snapshot_stock",
    "replanning_snapshot_semine", "replanning_snapshot_allocazioni",
    "transizioni_allocazione",
    "replanning_disposition_sets", "replanning_disposition_decisions",
    "replanning_disposition_replacements",
}


def _module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _database(tmp_path: Path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'main.sqlite'}")
    connection = engine.connect()
    connection.connection.driver_connection.create_function("btrim", 1, str.strip)
    schema_path = str(tmp_path / "tpo.sqlite").replace("'", "''")
    connection.exec_driver_sql(f"ATTACH DATABASE '{schema_path}' AS tpo")
    return engine, connection


def _postgresql_ddl(start: str = "base", end: str = "head") -> str:
    output = StringIO()
    config = make_config()
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@invalid/tpo")
    config.output_buffer = output
    target = end if start == "base" else f"{start}:{end}"
    command.upgrade(config, target, sql=True)
    return re.sub(r"\s+", " ", output.getvalue()).strip()


def _free_tcp_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _insert_replanning_snapshot(connection, discriminator: int) -> int:
    return connection.execute(sa.text("""
        INSERT INTO tpo.replanning_snapshots (
          order_line_public_id, order_public_id, order_state, order_version,
          order_line_version, ordered_quantity, delivered_quantity,
          commercial_residual_quantity, delivery_date, variety_public_id,
          protocol_version_public_id, protocol_version_number,
          protocol_valid_from, policy_set_code, planning_policy_version,
          quantitative_buffer_policy_type, temporal_buffer_minutes,
          production_granularity, previous_plan_revision_public_id,
          previous_plan_revision_version, replanning_reason_code,
          canonical_text, canonical_hash, created_by
        ) VALUES (
          :order_line, :order, 'APERTO', 0, 0, 1, 0, 1,
          DATE '2099-01-01', :variety, :protocol, 1, DATE '2098-01-01',
          'TEST-POLICY', 1, 'NONE', 0, 1, :previous_revision, 0,
          'MANUAL_REPLAN_AUTHORIZED', :canonical_text, :canonical_hash, 'test-suite'
        ) RETURNING id
    """), {
        "order_line": f"TEST-RO-{discriminator}",
        "order": f"TEST-ORDER-{discriminator}",
        "variety": f"TEST-VARIETY-{discriminator}",
        "protocol": f"TEST-PROTOCOL-{discriminator}",
        "previous_revision": f"TEST-REVISION-{discriminator}",
        "canonical_text": f"test-snapshot-{discriminator}",
        "canonical_hash": f"{discriminator:064x}",
    }).scalar_one()


def _set_constraints(connection, mode: str) -> None:
    assert mode in {"DEFERRED", "IMMEDIATE"}
    connection.exec_driver_sql(f"SET CONSTRAINTS ALL {mode}")


def _insert_valid_planning_graph(connection) -> tuple[int, int, int]:
    now = "TIMESTAMPTZ '2098-01-01 10:00:00+00'"
    client_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.clienti
          (public_id, denominazione, created_by, updated_at, updated_by)
        VALUES ('CLI-990001', 'Test-only planning client', 'test-suite', {now}, 'test-suite')
        RETURNING id
    """).scalar_one()
    variety_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.varieta
          (public_id, denominazione, stato, created_by, updated_at, updated_by)
        VALUES ('VAR-990001', 'Test-only planning variety', 'ATTIVA', 'test-suite', {now}, 'test-suite')
        RETURNING id
    """).scalar_one()
    cultivar_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.cultivar
          (varieta_id, denominazione, stato, created_by, updated_at, updated_by)
        VALUES ({variety_id}, 'Test-only cultivar', 'ATTIVA', 'test-suite', {now}, 'test-suite')
        RETURNING id
    """).scalar_one()
    use_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.usi_produttivi
          (codice, denominazione, created_by, updated_at, updated_by)
        VALUES ('TEST-PLANNING', 'Test-only planning use', 'test-suite', {now}, 'test-suite')
        RETURNING id
    """).scalar_one()
    cultivar_use_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.cultivar_usi
          (cultivar_id, uso_produttivo_id, stato_validazione, created_by, updated_at, updated_by)
        VALUES ({cultivar_id}, {use_id}, 'TEST_VALID', 'test-suite', {now}, 'test-suite')
        RETURNING id
    """).scalar_one()
    protocol_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.protocolli
          (cultivar_uso_id, tipo, denominazione, created_by, updated_at, updated_by)
        VALUES ({cultivar_use_id}, 'STANDARD', 'Test-only protocol', 'test-suite', {now}, 'test-suite')
        RETURNING id
    """).scalar_one()
    protocol_version_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.protocollo_versioni
          (protocollo_id, numero_versione, valida_dal, contenuto, motivazione, created_by)
        VALUES ({protocol_id}, 1, DATE '2098-01-01', 'test-only', 'test-only', 'test-suite')
        RETURNING id
    """).scalar_one()
    order_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.ordini
          (public_id, cliente_id, data_ordine, data_consegna_prevista, stato,
           tipo_creazione, created_by)
        VALUES ('ORD-990001', {client_id}, DATE '2098-01-01', DATE '2099-01-01',
                'APERTO', 'MANUALE', 'test-suite')
        RETURNING id
    """).scalar_one()
    order_line_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.righe_ordine
          (ordine_id, posizione, varieta_id, quantita, unita_misura, public_id)
        VALUES ({order_id}, 1, {variety_id}, 1, 'SET', 'RO-990001')
        RETURNING id
    """).scalar_one()
    connection.exec_driver_sql(f"""
        INSERT INTO tpo.stock (varieta_id, disponibile, unita_misura, updated_at)
        VALUES ({variety_id}, 10, 'SET', {now})
    """)
    policy_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.production_planning_policy_versions (
          policy_set_code, numero_versione, harvest_target_strategy,
          buffer_quantitativo_tipo, priority_policy_code,
          planning_algorithm_version, valida_dal, provenance, approved_at,
          approved_by, created_by
        ) VALUES (
          'TEST-PLANNING', 1, 'EARLIEST_APPROVED_WINDOW', 'NONE',
          'TEST-PRIORITY', 'TEST-ALGORITHM', DATE '2098-01-01', 'test-only',
          {now}, 'test-suite', 'test-suite'
        ) RETURNING id
    """).scalar_one()
    run_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.production_planning_runs
          (public_id, policy_version_id, business_at, started_at, created_by)
        VALUES ('RPP-990001', {policy_id}, {now}, {now}, 'test-suite')
        RETURNING id
    """).scalar_one()
    plan_id = connection.exec_driver_sql("""
        INSERT INTO tpo.piani_produzione
          (public_id, stato_complessivo, created_by, updated_by)
        VALUES ('PP-990001', 'TEST_OPEN', 'test-suite', 'test-suite')
        RETURNING id
    """).scalar_one()
    revision_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.piano_produzione_revisioni (
          public_id, piano_produzione_id, planning_run_id, numero_revisione,
          policy_version_id, business_at, revision_request_key, created_by
        ) VALUES (
          'RVP-990001', {plan_id}, {run_id}, 1, {policy_id}, {now},
          '{'a' * 64}', 'test-suite'
        ) RETURNING id
    """).scalar_one()
    planning_row_id = connection.exec_driver_sql(f"""
        INSERT INTO tpo.righe_piano_semina (
          public_id, piano_revisione_id, riga_ordine_id, varieta_id, cultivar_id,
          cultivar_uso_id, protocollo_versione_id, ordine_version_attesa,
          riga_ordine_version_attesa, varieta_public_id_snapshot,
          cultivar_snapshot, uso_produttivo_snapshot, domanda_originaria,
          quantita_consegnata_snapshot, domanda_residua_commerciale,
          copertura_stock, copertura_produzione_in_corso,
          copertura_raccolta_allocata, deficit_produttivo,
          buffer_quantitativo_tipo, buffer_quantitativo_calcolato,
          quantita_pre_granularita, granularita_produttiva,
          quantita_produttiva_autorizzata, quantita_residua_da_avviare,
          resa_attesa, resa_unita_misura, grammi_seme_richiesti, unita_domanda,
          data_consegna, harvest_window_start, harvest_window_end,
          harvest_target_at, sowing_at, light_at, hydration_at, timezone,
          orario_semina_snapshot, orario_raccolta_snapshot,
          buffer_temporale_minuti, stato, planning_key, provenance,
          created_by, updated_by
        ) VALUES (
          'RPS-990001', {revision_id}, {order_line_id}, {variety_id}, {cultivar_id},
          {cultivar_use_id}, {protocol_version_id}, 0, 0, 'VAR-990001',
          'Test-only cultivar', 'TEST-PLANNING', 1, 0, 1, 0, 0, 0, 1,
          'NONE', 0, 1, 1, 1, 1, 1, 'SET', 1, 'SET', DATE '2099-01-01',
          DATE '2098-12-30', DATE '2098-12-31',
          TIMESTAMPTZ '2098-12-30 12:00:00+00',
          TIMESTAMPTZ '2098-12-28 12:00:00+00',
          TIMESTAMPTZ '2098-12-29 12:00:00+00',
          TIMESTAMPTZ '2098-12-28 12:00:00+00', 'Atlantic/Canary',
          TIME '12:00', TIME '12:00', 0, 'PIANIFICATA', '{'b' * 64}',
          'test-only', 'test-suite', 'test-suite'
        ) RETURNING id
    """).scalar_one()
    return planning_row_id, order_line_id, variety_id


def _resolve_valid_planning_graph(connection) -> tuple[int, int, int]:
    existing = connection.execute(sa.text("""
        SELECT rps.id, ro.id, v.id
        FROM tpo.clienti AS c
        JOIN tpo.ordini AS o ON o.cliente_id=c.id
        JOIN tpo.righe_ordine AS ro ON ro.ordine_id=o.id
        JOIN tpo.varieta AS v ON v.id=ro.varieta_id
        JOIN tpo.stock AS s ON s.varieta_id=v.id
        JOIN tpo.righe_piano_semina AS rps ON rps.riga_ordine_id=ro.id
        JOIN tpo.piano_produzione_revisioni AS r
          ON r.id=rps.piano_revisione_id
        JOIN tpo.piani_produzione AS p ON p.id=r.piano_produzione_id
        JOIN tpo.production_planning_runs AS pr ON pr.id=r.planning_run_id
        JOIN tpo.production_planning_policy_versions AS pv
          ON pv.id=pr.policy_version_id AND pv.id=r.policy_version_id
        WHERE c.public_id='CLI-990001'
          AND c.denominazione='Test-only planning client'
          AND o.public_id='ORD-990001'
          AND o.stato='APERTO'
          AND ro.public_id='RO-990001'
          AND ro.posizione=1
          AND ro.quantita=1
          AND ro.unita_misura='SET'
          AND v.public_id='VAR-990001'
          AND v.denominazione='Test-only planning variety'
          AND v.stato='ATTIVA'
          AND s.disponibile=10
          AND s.unita_misura='SET'
          AND rps.public_id='RPS-990001'
          AND rps.stato='PIANIFICATA'
          AND r.public_id='RVP-990001'
          AND r.numero_revisione=1
          AND p.public_id='PP-990001'
          AND pr.public_id='RPP-990001'
          AND pv.policy_set_code='TEST-PLANNING'
          AND pv.numero_versione=1
    """)).one_or_none()
    if existing is not None:
        return existing
    seed_identifiers_exist = connection.execute(sa.text("""
        SELECT EXISTS (
          SELECT 1 FROM tpo.clienti WHERE public_id='CLI-990001'
          UNION ALL SELECT 1 FROM tpo.varieta WHERE public_id='VAR-990001'
          UNION ALL SELECT 1 FROM tpo.ordini WHERE public_id='ORD-990001'
          UNION ALL SELECT 1 FROM tpo.righe_ordine WHERE public_id='RO-990001'
          UNION ALL SELECT 1 FROM tpo.production_planning_runs WHERE public_id='RPP-990001'
          UNION ALL SELECT 1 FROM tpo.piani_produzione WHERE public_id='PP-990001'
          UNION ALL SELECT 1 FROM tpo.piano_produzione_revisioni WHERE public_id='RVP-990001'
          UNION ALL SELECT 1 FROM tpo.righe_piano_semina WHERE public_id='RPS-990001'
        )
    """)).scalar_one()
    assert not seed_identifiers_exist, (
        "Seed test-only CLI-990001 presente ma semanticamente incompatibile"
    )
    return _insert_valid_planning_graph(connection)


def _setup_allocation(
    connection, public_number: int, allocation_type: str, planning_row_id: int
) -> int:
    return connection.execute(sa.text("""
        INSERT INTO tpo.allocazioni (
          public_id, allocation_type, riga_piano_semina_id, quantity,
          unita_misura, state, created_at, created_by, updated_at, updated_by
        ) VALUES (
          :public_id, CAST(:allocation_type AS tpo.allocation_type), :planning_row_id, 1,
          'SET', 'ATTIVA', CURRENT_TIMESTAMP, 'test-suite',
          CURRENT_TIMESTAMP, 'test-suite'
        ) RETURNING id
    """), {
        "public_id": f"ALL-{public_number:06d}",
        "allocation_type": allocation_type,
        "planning_row_id": planning_row_id,
    }).scalar_one()


@pytest.fixture(scope="module")
def isolated_postgresql(tmp_path_factory):
    """Start a disposable local PostgreSQL, or skip when binaries cannot run."""
    initdb = shutil.which("initdb")
    pg_ctl = shutil.which("pg_ctl")
    if initdb is None or pg_ctl is None:
        pytest.skip("PostgreSQL test binaries are not installed")

    root = tmp_path_factory.mktemp("production-planning-postgresql")
    data = root / "data"
    log_file = root / "postgres.log"
    environment = {**os.environ, "LC_ALL": "C"}
    initialized = subprocess.run(
        [
            initdb,
            "-D",
            str(data),
            "--auth=trust",
            "--username=postgres",
            "--encoding=UTF8",
        ],
        capture_output=True, text=True, env=environment,
    )
    if initialized.returncode:
        pytest.skip(f"isolated PostgreSQL initdb unavailable: {initialized.stderr.strip()}")

    port = _free_tcp_port()
    options = f"-F -p {port} -h 127.0.0.1"
    try:
        started = subprocess.run(
            [pg_ctl, "-D", str(data), "-l", str(log_file), "-o", options, "-w", "start"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            env=environment, timeout=30,
        )
    except subprocess.TimeoutExpired:
        subprocess.run(
            [pg_ctl, "-D", str(data), "-m", "immediate", "stop"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=environment, check=False, timeout=10,
        )
        server_log = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
        pytest.fail(f"isolated PostgreSQL start timed out; postgres.log:\n{server_log}")
    if started.returncode:
        server_log = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
        pytest.skip(
            f"isolated PostgreSQL cannot start: {started.stderr.strip()}; "
            f"postgres.log:\n{server_log}"
        )

    url = f"postgresql+psycopg://postgres@127.0.0.1:{port}/postgres"
    engine = sa.create_engine(url)
    try:
        with engine.connect() as connection:
            yield connection
    finally:
        engine.dispose()
        try:
            subprocess.run(
                [pg_ctl, "-D", str(data), "-m", "fast", "-w", "stop"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                env=environment, check=False, timeout=30,
            )
        except subprocess.TimeoutExpired:
            pytest.fail("isolated PostgreSQL stop timed out")


@pytest.fixture
def upgraded(tmp_path: Path):
    engine, connection = _database(tmp_path)
    command.upgrade(make_config(connection=connection), "head")
    try:
        yield connection
    finally:
        connection.close()
        engine.dispose()


def test_revision_chain_e_nuovo_head() -> None:
    revisions = list(ScriptDirectory.from_config(make_config()).walk_revisions())
    assert [item.revision for item in revisions[:20]] == [
        "20260905_0032", "20260905_0031", "20260905_0030", "20260905_0029", "20260904_0028", "20260903_0027", "20260903_0026", "20260903_0025", "20260903_0024", "20260903_0023", "20260830_0022", "20260826_0021", "20260825_0020",
        "20260825_0019", "20260824_0018", "20260824_0017", "20260823_0016", "20260822_0015", "20260822_0014", "20260815_0013",
    ]
    assert [item.down_revision for item in revisions[:19]] == [
        "20260905_0031", "20260905_0030", "20260905_0029", "20260904_0028", "20260903_0027", "20260903_0026", "20260903_0025", "20260903_0024", "20260903_0023", "20260830_0022", "20260826_0021", "20260825_0020", "20260825_0019",
        "20260824_0018", "20260824_0017", "20260823_0016", "20260822_0015", "20260822_0014", "20260815_0013",
    ]


def test_resource_snapshot_authority_migration_contract() -> None:
    path = VERSIONS / "20260822_0015_resource_snapshot_authority.py"
    migration = _module(path)
    assert migration.revision == "20260822_0015"
    assert migration.down_revision == "20260822_0014"
    source = path.read_text(encoding="utf-8")
    for column in (
        "expected_useful_quantity", "expected_useful_uom",
        "harvest_window_start", "harvest_window_end",
    ):
        assert column in source
    assert re.search(r"\b(?:INSERT\s+INTO|UPDATE\s+tpo\.|DELETE\s+FROM)\b", source, re.I) is None


def test_resource_snapshot_authority_offline_postgresql_ddl() -> None:
    ddl = _postgresql_ddl("20260822_0014", "20260822_0015")
    normalized = ddl.lower()
    for column in (
        "expected_useful_quantity", "expected_useful_uom",
        "harvest_window_start", "harvest_window_end",
    ):
        assert column in normalized
    assert "alter column readiness_code drop not null" in normalized
    assert re.search(r"\b(insert into|update tpo\.|delete from)\b", ddl, re.I) is None


def test_resource_snapshot_authority_columns_and_checks(upgraded) -> None:
    columns = {
        row[1]: row[3]
        for row in upgraded.exec_driver_sql("PRAGMA tpo.table_info('semine')")
    }
    assert columns["expected_useful_quantity"] == 0
    assert columns["expected_useful_uom"] == 0
    assert columns["harvest_window_start"] == 0
    assert columns["harvest_window_end"] == 0
    semine_sql = upgraded.exec_driver_sql(
        "SELECT sql FROM tpo.sqlite_master WHERE type='table' AND name='semine'"
    ).scalar_one()
    assert "ck_semine_expected_useful_pair" in semine_sql
    assert "ck_semine_harvest_window_pair" in semine_sql
    assert "ck_semine_planning_authority_commissioning" in semine_sql
    snapshot_columns = {
        row[1]: row[3]
        for row in upgraded.exec_driver_sql(
            "PRAGMA tpo.table_info('replanning_snapshot_stock')"
        )
    }
    assert snapshot_columns["readiness_code"] == 0


def test_zero_production_planning_line_migration_contract() -> None:
    migration = _module(
        VERSIONS / "20260815_0013_zero_production_planning_lines.py"
    )
    assert migration.revision == "20260815_0013"
    assert migration.down_revision == "20260814_0012"
    assert "quantita_produttiva_autorizzata = 0" in migration.NEW_CHECK
    assert "grammi_seme_richiesti IS NULL" in migration.NEW_CHECK
    assert "quantita_produttiva_autorizzata > 0" in migration.NEW_CHECK
    assert "grammi_seme_richiesti IS NOT NULL" in migration.NEW_CHECK
    assert "grammi_seme_richiesti > 0" in migration.NEW_CHECK
    source = (
        VERSIONS / "20260815_0013_zero_production_planning_lines.py"
    ).read_text(encoding="utf-8")
    assert re.search(r"\b(?:INSERT|UPDATE|DELETE)\s+(?:INTO|tpo\.)", source, re.I) is None


def test_zero_production_planning_line_offline_postgresql_ddl() -> None:
    ddl = _postgresql_ddl("20260814_0012", "20260815_0013")
    normalized = ddl.lower()
    assert "zero-production planning line commissioning required" in normalized
    assert "alter column grammi_seme_richiesti drop not null" in normalized
    assert "quantita_produttiva_autorizzata = 0" in normalized
    assert "grammi_seme_richiesti is null" in normalized
    assert re.search(r"\b(insert into|update tpo\.|delete from)\b", ddl, re.I) is None


def test_replanning_disposition_authority_migration_contract() -> None:
    path = VERSIONS / "20260822_0014_replanning_disposition_authority.py"
    migration = _module(path)
    assert migration.revision == "20260822_0014"
    assert migration.down_revision == "20260815_0013"
    source = path.read_text(encoding="utf-8")
    for table in (
        "replanning_disposition_sets", "replanning_disposition_decisions",
        "replanning_disposition_replacements",
    ):
        assert f'"{table}"' in source
    assert "replacement_allocation_public_id" not in source
    assert "destination_planning_line_public_id" not in source
    assert re.search(r"\b(?:INSERT\s+INTO|UPDATE\s+tpo\.|DELETE\s+FROM)\b", source, re.I) is None


def test_replanning_disposition_authority_offline_postgresql_ddl() -> None:
    ddl = _postgresql_ddl("20260815_0013", "20260822_0014")
    normalized = ddl.lower()
    assert "create table tpo.replanning_disposition_sets" in normalized
    assert "create table tpo.replanning_disposition_decisions" in normalized
    assert "create table tpo.replanning_disposition_replacements" in normalized
    assert "authorized replanning disposition set is immutable" in normalized
    assert "replanning replacement cardinality mismatch" in normalized
    assert "replanning_snapshots_disposition_set_key_fkey" in normalized
    assert "replacement_allocation_public_id" not in normalized
    assert "destination_planning_line_public_id" not in normalized


def test_replanning_disposition_trigger_fix_is_table_shape_safe() -> None:
    migration = _module(
        VERSIONS / "20260824_0018_replanning_disposition_trigger_fix.py"
    )
    assert migration.revision == "20260824_0018"
    assert migration.down_revision == "20260824_0017"
    fixed = migration.FIXED_FUNCTION
    assert "IF TG_TABLE_NAME = 'replanning_disposition_sets'" in fixed
    assert "ELSIF TG_TABLE_NAME = 'replanning_disposition_decisions'" in fixed
    assert "ELSIF TG_TABLE_NAME = 'replanning_disposition_replacements'" in fixed
    assert "set_id := NEW.id;" in fixed
    assert "set_id := OLD.disposition_set_id;" in fixed
    assert "decision_id := OLD.disposition_decision_id;" in fixed
    assert "unsupported replanning disposition trigger table" in fixed


def test_replanning_disposition_tables_and_snapshot_link(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    names = set(inspector.get_table_names(schema="tpo"))
    assert {
        "replanning_disposition_sets", "replanning_disposition_decisions",
        "replanning_disposition_replacements",
    } <= names
    replacement_columns = {
        item["name"] for item in inspector.get_columns(
            "replanning_disposition_replacements", schema="tpo"
        )
    }
    assert "replacement_allocation_slot_key" in replacement_columns
    assert "destination_planning_line_slot_key" in replacement_columns
    assert "replacement_allocation_public_id" not in replacement_columns
    assert "destination_planning_line_public_id" not in replacement_columns
    snapshot_columns = {
        item["name"] for item in inspector.get_columns("replanning_snapshots", schema="tpo")
    }
    assert "disposition_set_key" in snapshot_columns


def test_replanning_disposition_constraints_are_declared() -> None:
    source = (
        VERSIONS / "20260822_0014_replanning_disposition_authority.py"
    ).read_text(encoding="utf-8")
    required = (
        "uq_replanning_disposition_sets_key",
        "uq_replanning_disposition_sets_scope_correlation",
        "uq_replanning_disposition_decisions_allocation",
        "uq_replanning_disposition_decisions_position",
        "ck_replanning_disposition_sets_authorization",
        "ck_replanning_disposition_decisions_combination",
        "ck_replanning_disposition_replacements_quantity",
        "uq_replanning_disposition_replacements_slot",
        "downgrade refused",
    )
    assert all(item in source for item in required)


def test_audit_provenance_migration_contract() -> None:
    migration = _module(VERSIONS / "20260814_0012_audit_provenance.py")
    assert migration.revision == "20260814_0012"
    assert migration.down_revision == "20260814_0011"
    source = (VERSIONS / "20260814_0012_audit_provenance.py").read_text(
        encoding="utf-8"
    )
    assert 'sa.Column("provenance", sa.Text(), nullable=True)' in source
    assert "provenance IS NULL OR btrim(provenance) <> ''" in source
    assert "server_default" not in source
    assert re.search(r"\b(INSERT|UPDATE|DELETE)\b", source) is None


def _insert_test_audit(connection, discriminator: str, provenance_marker="OMIT") -> int:
    columns = [
        "id", "occurred_at", "actor", "entity_type", "entity_public_id",
        "operation", "reason", "after_data", "correlation_id",
    ]
    values = [
        str(9_900_000 + sum((index + 1) * ord(char) for index, char in enumerate(discriminator))),
        "CURRENT_TIMESTAMP", "'test-suite'", "'TEST_ENTITY'",
        f"'TEST-{discriminator}'", "'INSERT'", "'test-only'", "'{}'", "'test-correlation'",
    ]
    if provenance_marker != "OMIT":
        columns.append("provenance")
        values.append("NULL" if provenance_marker is None else f"'{provenance_marker}'")
    return connection.exec_driver_sql(
        f"INSERT INTO tpo.audit_eventi ({','.join(columns)}) "
        f"VALUES ({','.join(values)}) RETURNING id"
    ).scalar_one()


def test_audit_provenance_catalog_nullable_no_default_and_legacy_insert(upgraded) -> None:
    columns = {
        item["name"]: item
        for item in sa.inspect(upgraded).get_columns("audit_eventi", schema="tpo")
    }
    assert columns["provenance"]["nullable"] is True
    assert columns["provenance"]["default"] is None
    legacy_id = _insert_test_audit(upgraded, "LEGACY")
    explicit_id = _insert_test_audit(upgraded, "PROVENANCE", "planning:test")
    rows = upgraded.execute(
        sa.text(
            "SELECT id,provenance FROM tpo.audit_eventi "
            "WHERE id IN (:legacy_id,:explicit_id) ORDER BY id"
        ),
        {"legacy_id": legacy_id, "explicit_id": explicit_id},
    ).all()
    assert rows == [(legacy_id, None), (explicit_id, "planning:test")]


@pytest.mark.parametrize("invalid", ["", "   "])
def test_audit_provenance_rejects_blank(upgraded, invalid: str) -> None:
    with pytest.raises(sa.exc.IntegrityError), upgraded.begin_nested():
        _insert_test_audit(upgraded, f"INVALID-{len(invalid)}", invalid)
    assert upgraded.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_audit_provenance_historical_roundtrip(tmp_path: Path) -> None:
    engine, connection = _database(tmp_path)
    try:
        config = make_config(connection=connection)
        command.upgrade(config, "20260814_0011")
        historical_id = _insert_test_audit(connection, "HISTORICAL")
        command.upgrade(config, "20260814_0012")
        assert connection.exec_driver_sql(
            f"SELECT provenance FROM tpo.audit_eventi WHERE id={historical_id}"
        ).scalar_one() is None
        command.downgrade(config, "20260814_0011")
        assert "provenance" not in {
            item["name"]
            for item in sa.inspect(connection).get_columns("audit_eventi", schema="tpo")
        }
        command.upgrade(config, "20260814_0012")
        assert connection.exec_driver_sql(
            f"SELECT provenance FROM tpo.audit_eventi WHERE id={historical_id}"
        ).scalar_one() is None
    finally:
        connection.close()
        engine.dispose()


def test_audit_provenance_offline_postgresql_ddl_is_schema_only() -> None:
    ddl = _postgresql_ddl("20260814_0011", "20260814_0012")
    assert "add column provenance text" in ddl.lower()
    assert "provenance is null or btrim(provenance) <> ''" in ddl.lower()
    assert re.search(r"\b(insert into|update tpo\.|delete from)\b", ddl, re.I) is None


def test_upgrade_0004_downgrade_e_reupgrade(tmp_path: Path) -> None:
    engine, connection = _database(tmp_path)
    try:
        config = make_config(connection=connection)
        command.upgrade(config, "20260810_0004")
        baseline = set(sa.inspect(connection).get_table_names(schema="tpo"))
        command.upgrade(config, "head")
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260905_0032"
        assert PLANNING_TABLES <= set(sa.inspect(connection).get_table_names(schema="tpo"))
        command.downgrade(config, "20260810_0004")
        assert set(sa.inspect(connection).get_table_names(schema="tpo")) == baseline
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260810_0004"
        command.upgrade(config, "head")
        assert PLANNING_TABLES <= set(sa.inspect(connection).get_table_names(schema="tpo"))
    finally:
        connection.close()
        engine.dispose()


def test_enum_planning_esatti() -> None:
    foundation = _module(PATHS[0])
    assert foundation.production_planning_run_state.enums == ["OPEN", "COMMITTED", "FAILED", "RECONCILIATION_REQUIRED"]
    assert foundation.protocollo_versione_approval_state.enums == ["BOZZA", "APPROVATA", "RITIRATA"]
    assert foundation.planning_allocation_state.enums == ["ATTIVA", "CONSUMATA", "RILASCIATA", "SOSTITUITA", "INVALIDA"]
    assert foundation.allocation_type.enums == ["DOMANDA", "STOCK", "PRODUZIONE_IN_CORSO", "RACCOLTA"]
    transition = _module(PATHS[4])
    assert transition.allocation_transition_type.enums == [
        "CONSUMATA", "RILASCIATA", "SOSTITUITA", "INVALIDA",
    ]


def test_allocation_transition_offline_ddl_e_schema_only() -> None:
    ddl = _postgresql_ddl("20260812_0009")
    assert "CREATE TYPE tpo.allocation_transition_type AS ENUM ('CONSUMATA', 'RILASCIATA', 'SOSTITUITA', 'INVALIDA')" in ddl
    assert "CREATE TABLE tpo.transizioni_allocazione" in ddl
    assert "historical allocation commissioning required" in ddl
    assert "tr_transizioni_allocazione_append_only" in ddl
    assert "fn_transizioni_allocazione_append_only" in ddl
    source = PATHS[4].read_text(encoding="utf-8")
    assert not re.search(r"\b(?:INSERT|UPDATE|DELETE)\s+(?:INTO|tpo\.)", source, re.IGNORECASE)
    assert "remaining_quantity" not in source
    assert "consumed_quantity" not in source


def test_allocation_transition_migration_contract_statico() -> None:
    source = PATHS[4].read_text(encoding="utf-8")
    for name in (
        "transizioni_allocazione_pkey",
        "transizioni_allocazione_allocation_id_fkey",
        "transizioni_allocazione_replacement_allocation_id_fkey",
        "ck_transizioni_allocazione_quantity",
        "ck_transizioni_allocazione_expected_version",
        "ck_transizioni_allocazione_texts",
        "ck_transizioni_allocazione_replacement",
        "ck_transizioni_allocazione_distinct_allocations",
        "uq_transizioni_allocazione_epoch_type",
        "uq_transizioni_allocazione_replacement",
        "ix_transizioni_allocazione_allocation_epoch",
        "ix_transizioni_allocazione_allocation_created",
        "ix_transizioni_allocazione_replacement",
    ):
        assert name in source
    assert source.index("_historical_commissioning_gate(bind)") < source.index(
        "allocation_transition_type.create"
    )
    downgrade = source[source.index("def downgrade()") :]
    assert downgrade.index("DROP TRIGGER") < downgrade.index("op.drop_table")
    assert downgrade.index("DROP FUNCTION") < downgrade.index("op.drop_table")
    assert downgrade.index("op.drop_table") < downgrade.index(
        "allocation_transition_type.drop"
    )


def test_estensioni_staged_senza_dati_inventati(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    protocol = {item["name"]: item for item in inspector.get_columns("protocollo_versioni", schema="tpo")}
    rows = {item["name"]: item for item in inspector.get_columns("righe_ordine", schema="tpo")}
    orders = {item["name"]: item for item in inspector.get_columns("ordini", schema="tpo")}
    sowings = {item["name"]: item for item in inspector.get_columns("semine", schema="tpo")}
    assert protocol["public_id"]["nullable"] is True
    assert protocol["idratazione_ore"]["nullable"] is True
    assert rows["public_id"]["nullable"] is True
    assert rows["version"]["nullable"] is False
    assert orders["version"]["nullable"] is False
    assert sowings["version"]["nullable"] is False
    assert all(connection_default is None for connection_default in (
        protocol["stato_approvazione"]["default"], protocol["idratazione_ore"]["default"],
        protocol["grammi_seme_per_set"]["default"], protocol["granularita_produttiva"]["default"],
    ))


@pytest.fixture
def protocol_lifecycle_table():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = sa.Table(
        "protocol_lifecycle", metadata,
        sa.Column("stato_approvazione", sa.Text(), nullable=False),
        sa.Column("approvata_at", sa.Text()), sa.Column("approvata_by", sa.Text()),
        sa.Column("ritirata_at", sa.Text()), sa.Column("ritirata_by", sa.Text()),
        sa.CheckConstraint("(stato_approvazione='BOZZA' AND approvata_at IS NULL AND approvata_by IS NULL AND ritirata_at IS NULL AND ritirata_by IS NULL) OR (stato_approvazione='APPROVATA' AND approvata_at IS NOT NULL AND approvata_by IS NOT NULL AND ritirata_at IS NULL AND ritirata_by IS NULL) OR (stato_approvazione='RITIRATA' AND ritirata_at IS NOT NULL AND ritirata_by IS NOT NULL AND ((approvata_at IS NULL AND approvata_by IS NULL) OR (approvata_at IS NOT NULL AND approvata_by IS NOT NULL)))", name="ck_protocollo_versioni_lifecycle"),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        yield connection, table
    engine.dispose()


@pytest.mark.parametrize("values", [
    {"stato_approvazione": "BOZZA"},
    {"stato_approvazione": "APPROVATA", "approvata_at": "2026-08-11", "approvata_by": "operator"},
    {"stato_approvazione": "RITIRATA", "ritirata_at": "2026-08-11", "ritirata_by": "operator"},
    {"stato_approvazione": "RITIRATA", "approvata_at": "2026-08-10", "approvata_by": "operator", "ritirata_at": "2026-08-11", "ritirata_by": "operator"},
])
def test_protocol_lifecycle_accetta_transizioni_congelate(protocol_lifecycle_table, values) -> None:
    connection, table = protocol_lifecycle_table
    connection.execute(table.insert().values(**values))


@pytest.mark.parametrize("values", [
    {"stato_approvazione": "BOZZA", "ritirata_at": "2026-08-11", "ritirata_by": "operator"},
    {"stato_approvazione": "APPROVATA", "approvata_at": "2026-08-11"},
    {"stato_approvazione": "RITIRATA", "ritirata_at": "2026-08-11"},
    {"stato_approvazione": "RITIRATA", "approvata_at": "2026-08-10", "ritirata_at": "2026-08-11", "ritirata_by": "operator"},
])
def test_protocol_lifecycle_rifiuta_coppie_incoerenti(protocol_lifecycle_table, values) -> None:
    connection, table = protocol_lifecycle_table
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(table.insert().values(**values))


def test_planning_run_separata_e_audit_owner(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    assert "production_planning_runs" in inspector.get_table_names(schema="tpo")
    audit = {item["name"] for item in inspector.get_columns("audit_eventi", schema="tpo")}
    assert {"run_id", "planning_run_id"} <= audit
    run_columns = {item["name"] for item in inspector.get_columns("production_planning_runs", schema="tpo")}
    assert {"state", "business_at", "completed_at", "version", "ordini_letti", "allocazioni_generate"} <= run_columns


def test_piani_revisioni_rps_hash_e_unicita(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    revision_unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("piano_produzione_revisioni", schema="tpo")}
    rps_unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("righe_piano_semina", schema="tpo")}
    assert ("piano_produzione_id", "numero_revisione") in revision_unique
    assert ("piano_revisione_id", "planning_key") in rps_unique
    assert ("piano_revisione_id", "riga_ordine_id") in rps_unique
    assert ("planning_key",) not in rps_unique
    ddl = _postgresql_ddl("20260810_0004")
    assert "ck_righe_piano_semina_planning_key CHECK (planning_key ~ '^[0-9a-f]{64}$')" in ddl
    assert "DEFERRABLE INITIALLY DEFERRED" in ddl


def test_allocazioni_parent_child_naming_e_indici(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    assert {item["name"] for item in inspector.get_columns("allocazioni", schema="tpo")} == {
        "id", "public_id", "allocation_type", "riga_piano_semina_id", "quantity",
        "unita_misura", "state", "created_at", "created_by", "updated_at",
        "updated_by", "version",
    }
    indexes = {item["name"] for item in inspector.get_indexes("allocazioni", schema="tpo")}
    assert indexes == {"ix_allocazioni_riga_piano_state", "ix_allocazioni_type_state"}
    domanda_unique = inspector.get_unique_constraints("allocazioni_domanda", schema="tpo")
    assert domanda_unique == []
    for table in ("allocazioni_domanda", "allocazioni_stock", "allocazioni_produzione_in_corso", "allocazioni_raccolta"):
        assert inspector.get_pk_constraint(table, schema="tpo")["constrained_columns"] == ["allocation_id"]


def test_structural_triggers_e_snapshot_authority_in_ddl() -> None:
    ddl = _postgresql_ddl("20260810_0004")
    assert "CREATE CONSTRAINT TRIGGER ct_allocazioni_exactly_one_child" in ddl
    assert "DEFERRABLE INITIALLY DEFERRED" in ddl
    assert "canonical_hash" in ddl
    assert ddl.count("canonical_hash") > 0
    sources = "\n".join(path.read_text(encoding="utf-8") for path in PATHS)
    assert sources.count('sa.Column("canonical_hash"') == 1
    for name in ("ct_replanning_snapshot_stock_dense", "ct_replanning_snapshot_semine_dense", "ct_replanning_snapshot_allocazioni_dense"):
        assert name in ddl


def test_plpgsql_function_bodies_have_valid_terminators() -> None:
    source = PATHS[2].read_text(encoding="utf-8")
    bodies = re.findall(
        r"RETURNS trigger LANGUAGE plpgsql AS \$\$(.*?)\$\$",
        source,
        flags=re.DOTALL,
    )
    assert len(bodies) == 2
    assert all(re.search(r"\bBEGIN\b.*\bEND;\s*$", body, re.DOTALL) for body in bodies)


def test_replanning_allocation_snapshot_balance_migration_static_contract() -> None:
    migration = _module(PATHS[5])
    source = PATHS[5].read_text(encoding="utf-8")
    assert migration.revision == "20260814_0011"
    assert migration.down_revision == "20260814_0010"
    assert "historical replanning allocation snapshot commissioning required" in source
    for name in (
        "consumed_quantity", "released_quantity", "transferred_quantity",
        "invalidated_quantity", "remaining_quantity",
    ):
        assert f'"{name}"' in source
        assert name in migration.NEW_CHECK
    assert "remaining_quantity = allocated_quantity" in migration.NEW_CHECK
    assert not re.search(r"\b(?:INSERT|UPDATE|DELETE)\b", source, re.IGNORECASE)
    assert "server_default" not in source


def test_replanning_allocation_snapshot_offline_ddl() -> None:
    ddl = _postgresql_ddl("20260814_0010", "20260814_0011")
    assert "historical replanning allocation snapshot commissioning required" in ddl
    for name in (
        "consumed_quantity", "released_quantity", "transferred_quantity",
        "invalidated_quantity", "remaining_quantity",
    ):
        assert f"ADD COLUMN {name} NUMERIC(20, 6) NOT NULL" in ddl
    assert "remaining_quantity = allocated_quantity" in ddl
    assert "INSERT INTO" not in ddl.upper()
    assert "UPDATE tpo.replanning_snapshot_allocazioni" not in ddl


def test_postgresql_ddl_contains_functions_and_constraint_triggers() -> None:
    ddl = _postgresql_ddl("20260810_0004")
    function_names = (
        "fn_allocazioni_exactly_one_child",
        "fn_replanning_snapshot_stock_dense",
        "fn_replanning_snapshot_semine_dense",
        "fn_replanning_snapshot_allocazioni_dense",
    )
    for name in function_names:
        assert f"CREATE FUNCTION tpo.{name}() RETURNS trigger LANGUAGE plpgsql AS $$" in ddl
        assert f"EXECUTE FUNCTION tpo.{name}()" in ddl
    assert ddl.count("CREATE CONSTRAINT TRIGGER ct_allocazioni_exactly_one_child") == 5
    assert ddl.count("DEFERRABLE INITIALLY DEFERRED") >= 8


def test_isolated_postgresql_upgrade_downgrade_reupgrade_and_catalogs(isolated_postgresql) -> None:
    connection = isolated_postgresql
    assert connection.exec_driver_sql("SHOW server_encoding").scalar_one() == "UTF8"
    assert connection.exec_driver_sql("SHOW client_encoding").scalar_one() == "UTF8"
    connection.commit()
    config = make_config(connection=connection)
    command.upgrade(config, "20260810_0004")
    command.upgrade(config, "head")
    assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260905_0032"
    command.downgrade(config, "20260814_0010")
    columns = {
        item["name"]
        for item in sa.inspect(connection).get_columns(
            "replanning_snapshot_allocazioni", schema="tpo"
        )
    }
    assert "remaining_quantity" not in columns
    checks = {
        item["name"]: item["sqltext"]
        for item in sa.inspect(connection).get_check_constraints(
            "replanning_snapshot_allocazioni", schema="tpo"
        )
    }
    assert "allocated_quantity > 0" in checks["ck_replanning_snapshot_allocazioni_quantity"]
    command.upgrade(config, "head")
    assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260905_0032"
    connection.commit()

    functions = set(connection.exec_driver_sql("""
        SELECT p.proname
        FROM pg_proc AS p
        JOIN pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = 'tpo' AND p.proname IN (
          'fn_allocazioni_exactly_one_child',
          'fn_replanning_snapshot_stock_dense',
          'fn_replanning_snapshot_semine_dense',
          'fn_replanning_snapshot_allocazioni_dense'
        )
    """).scalars())
    assert functions == {
        "fn_allocazioni_exactly_one_child",
        "fn_replanning_snapshot_stock_dense",
        "fn_replanning_snapshot_semine_dense",
        "fn_replanning_snapshot_allocazioni_dense",
    }
    triggers = connection.exec_driver_sql("""
        SELECT t.tgname, t.tgdeferrable, t.tginitdeferred
        FROM pg_trigger AS t
        JOIN pg_class AS c ON c.oid = t.tgrelid
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'tpo' AND NOT t.tgisinternal
          AND (t.tgname = 'ct_allocazioni_exactly_one_child' OR t.tgname LIKE 'ct_replanning_snapshot_%%_dense')
    """).all()
    assert len(triggers) == 8
    assert all(deferrable and initially_deferred for _, deferrable, initially_deferred in triggers)
    assert connection.exec_driver_sql("SELECT to_regclass('tpo.v_calendario_produzione')").scalar_one() == "tpo.v_calendario_produzione"

    connection.commit()
    command.downgrade(config, "20260810_0004")
    assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260810_0004"
    command.upgrade(config, "head")
    assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260905_0032"
    connection.commit()


def test_isolated_postgresql_dense_constraint_behavior(isolated_postgresql) -> None:
    connection = isolated_postgresql
    command.upgrade(make_config(connection=connection), "head")
    connection.execute(sa.text("""
        INSERT INTO tpo.varieta (
          public_id, denominazione, stato, created_by, updated_at, updated_by
        ) VALUES (
          'VAR-900001', 'Test-only dense trigger variety', 'ATTIVA',
          'test-suite', CURRENT_TIMESTAMP, 'test-suite'
        )
    """))
    connection.execute(sa.text("""
        INSERT INTO tpo.varieta (
          public_id, denominazione, stato, created_by, updated_at, updated_by
        )
        SELECT
          'VAR-' || resource_number::text,
          'Test-only dense resource ' || resource_number::text,
          'ATTIVA', 'test-suite', CURRENT_TIMESTAMP, 'test-suite'
        FROM generate_series(900002, 900050) AS resource_number
    """))
    connection.commit()

    discriminator = 100
    resource_number = 900000

    def snapshot() -> int:
        nonlocal discriminator
        discriminator += 1
        return _insert_replanning_snapshot(connection, discriminator)

    def insert_stock(snapshot_id: int, posizione: int) -> None:
        nonlocal resource_number
        resource_number += 1
        connection.execute(sa.text("""
            INSERT INTO tpo.replanning_snapshot_stock (
              snapshot_id, posizione, stock_resource_public_id,
              variety_public_id, eligible_quantity, allocated_quantity,
              allocable_residual, resource_version, readiness_code
            ) VALUES (
              :snapshot_id, :posizione, :stock_resource_public_id, 'VAR-900001',
              1, 0, 1, 0, 'TEST_READY'
            )
        """), {
            "snapshot_id": snapshot_id,
            "posizione": posizione,
            "stock_resource_public_id": f"VAR-{resource_number:06d}",
        })

    for positions in ([1], [1, 2], [1, 2, 3]):
        savepoint = connection.begin_nested()
        try:
            snapshot_id = snapshot()
            for posizione in positions:
                insert_stock(snapshot_id, posizione)
            _set_constraints(connection, "IMMEDIATE")
        finally:
            savepoint.rollback()

    savepoint = connection.begin_nested()
    try:
        snapshot_id = snapshot()
        insert_stock(snapshot_id, 1)
        insert_stock(snapshot_id, 3)
        with pytest.raises(sa.exc.DBAPIError, match="positions must be dense"):
            _set_constraints(connection, "IMMEDIATE")
    finally:
        savepoint.rollback()

    for operation in ("delete", "update"):
        savepoint = connection.begin_nested()
        try:
            snapshot_id = snapshot()
            for posizione in (1, 2, 3):
                insert_stock(snapshot_id, posizione)
            _set_constraints(connection, "IMMEDIATE")
            _set_constraints(connection, "DEFERRED")
            if operation == "delete":
                connection.execute(sa.text("""
                    DELETE FROM tpo.replanning_snapshot_stock
                    WHERE snapshot_id=:snapshot_id AND posizione=2
                """), {"snapshot_id": snapshot_id})
            else:
                connection.execute(sa.text("""
                    UPDATE tpo.replanning_snapshot_stock SET posizione=4
                    WHERE snapshot_id=:snapshot_id AND posizione=2
                """), {"snapshot_id": snapshot_id})
            with pytest.raises(sa.exc.DBAPIError, match="positions must be dense"):
                _set_constraints(connection, "IMMEDIATE")
        finally:
            savepoint.rollback()

    savepoint = connection.begin_nested()
    try:
        old_snapshot = snapshot()
        new_snapshot = snapshot()
        insert_stock(old_snapshot, 1)
        insert_stock(old_snapshot, 2)
        insert_stock(new_snapshot, 1)
        _set_constraints(connection, "IMMEDIATE")
        _set_constraints(connection, "DEFERRED")
        connection.execute(sa.text("""
            UPDATE tpo.replanning_snapshot_stock
            SET snapshot_id=:new_snapshot, posizione=2
            WHERE snapshot_id=:old_snapshot AND posizione=1
        """), {"old_snapshot": old_snapshot, "new_snapshot": new_snapshot})
        with pytest.raises(sa.exc.DBAPIError, match="positions must be dense"):
            _set_constraints(connection, "IMMEDIATE")
    finally:
        savepoint.rollback()
    connection.rollback()


def test_isolated_postgresql_allocation_constraint_behavior(isolated_postgresql) -> None:
    connection = isolated_postgresql
    command.upgrade(make_config(connection=connection), "head")
    planning_row_id, order_line_id, stock_variety_id = _insert_valid_planning_graph(connection)
    public_number = 910000

    def allocation(allocation_type: str = "DOMANDA") -> int:
        nonlocal public_number
        public_number += 1
        return _setup_allocation(
            connection, public_number, allocation_type, planning_row_id
        )

    savepoint = connection.begin_nested()
    try:
        parent = allocation()
        connection.execute(sa.text("""
            INSERT INTO tpo.allocazioni_domanda (allocation_id, riga_ordine_id)
            VALUES (:parent, :order_line_id)
        """), {"parent": parent, "order_line_id": order_line_id})
        _set_constraints(connection, "IMMEDIATE")
    finally:
        savepoint.rollback()

    invalid_cases = ("missing", "two_children", "wrong_type")
    for case in invalid_cases:
        savepoint = connection.begin_nested()
        try:
            parent = allocation()
            if case in {"two_children", "wrong_type"}:
                connection.execute(sa.text("""
                    INSERT INTO tpo.allocazioni_stock (allocation_id, stock_varieta_id)
                    VALUES (:parent, :stock_variety_id)
                """), {"parent": parent, "stock_variety_id": stock_variety_id})
            if case == "two_children":
                connection.execute(sa.text("""
                    INSERT INTO tpo.allocazioni_domanda (allocation_id, riga_ordine_id)
                    VALUES (:parent, :order_line_id)
                """), {"parent": parent, "order_line_id": order_line_id})
            with pytest.raises(sa.exc.DBAPIError, match="ct_allocazioni_exactly_one_child violated"):
                _set_constraints(connection, "IMMEDIATE")
        finally:
            savepoint.rollback()

    savepoint = connection.begin_nested()
    try:
        old_parent = allocation()
        new_parent = allocation()
        connection.execute(sa.text("""
            INSERT INTO tpo.allocazioni_domanda (allocation_id, riga_ordine_id)
            VALUES (:old_parent, :order_line_id)
        """), {"old_parent": old_parent, "order_line_id": order_line_id})
        connection.execute(sa.text("""
            UPDATE tpo.allocazioni_domanda SET allocation_id=:new_parent
            WHERE allocation_id=:old_parent
        """), {"old_parent": old_parent, "new_parent": new_parent})
        with pytest.raises(sa.exc.DBAPIError, match="ct_allocazioni_exactly_one_child violated"):
            _set_constraints(connection, "IMMEDIATE")
    finally:
        savepoint.rollback()
    connection.rollback()


def test_seed_resource_e_plan_to_semina_contract(upgraded) -> None:
    inspector = sa.inspect(upgraded)
    resource_checks = {item["name"] for item in inspector.get_check_constraints("risorse_seme_pianificate", schema="tpo")}
    link_checks = {item["name"] for item in inspector.get_check_constraints("righe_piano_semina_semine", schema="tpo")}
    link_columns = {item["name"]: item for item in inspector.get_columns("righe_piano_semina_semine", schema="tpo")}
    link_unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("righe_piano_semina_semine", schema="tpo")}
    assert "ck_risorse_seme_pianificate_uom" in resource_checks
    assert "ck_righe_piano_semina_semine_uom" in link_checks
    assert isinstance(link_columns["quantita_avviata"]["type"], sa.Numeric)
    assert (link_columns["quantita_avviata"]["type"].precision, link_columns["quantita_avviata"]["type"].scale) == (20, 6)
    assert ("semina_id",) in link_unique

    metadata = sa.MetaData()
    fraction = sa.Table("fractional_link", metadata, sa.Column("quantita_avviata", sa.Numeric(20, 6), nullable=False), sa.Column("unita_misura", sa.Text(), nullable=False), sa.CheckConstraint("quantita_avviata>0 AND unita_misura='SET'"))
    metadata.create_all(upgraded)
    upgraded.execute(fraction.insert().values(quantita_avviata=Decimal("0.5"), unita_misura="SET"))
    assert upgraded.execute(sa.select(fraction.c.quantita_avviata)).scalar_one() == Decimal("0.500000")


def test_germinazione_zero_e_timeline_persistibile(upgraded) -> None:
    checks = {item["name"]: item["sqltext"] for item in sa.inspect(upgraded).get_check_constraints("righe_piano_semina", schema="tpo")}
    assert "ck_righe_piano_semina_timeline" in checks
    timeline = checks["ck_righe_piano_semina_timeline"].replace(" ", "")
    assert "sowing_at<=light_at" in timeline
    assert "sowing_at<light_at" not in timeline


def test_calendar_contract_completo() -> None:
    view = _module(PATHS[3]).VIEW_SQL
    assert len(re.findall(r"(?m)^SELECT$", view)) == 7
    branches = re.findall(r"(?ms)^SELECT\n(.*?)\nFROM ", view)
    assert len(branches) == 7
    assert all(len(branch.split(",\n")) == 18 for branch in branches)
    assert len(re.findall(r"(?m)^UNION ALL$", view)) == 6
    assert not re.search(r"(?m)^UNION$", view)
    assert "ORDER BY" not in view
    assert view.count("AT TIME ZONE 'Atlantic/Canary'") == 7
    assert "WHERE r.hydration_at < r.sowing_at" in view
    assert "FROM tpo.semine AS s\nLEFT JOIN" in view
    assert "FROM tpo.raccolte AS ra\nJOIN tpo.semine" in view
    assert "NULL::text AS source_state" in view
    assert "c.stato = 'CONSEGNATA'" in view and "c.data_effettiva IS NOT NULL" in view
    assert "data_prevista AT TIME ZONE" not in view
    expected = ["IDRATAZIONE_PIANIFICATA", "SEMINA_PIANIFICATA", "LUCE_PIANIFICATA", "RACCOLTA_TARGET", "SEMINA_REALE", "RACCOLTA_REALE", "CONSEGNA_EFFETTIVA"]
    assert [match.group(1) for match in re.finditer(r"'([^']+)'::text AS event_type", view)] == expected


def test_no_dml_identity_seed_o_business_defaults() -> None:
    sources = "\n".join(path.read_text(encoding="utf-8") for path in PATHS)
    assert "op.bulk_insert" not in sources
    assert "INSERT INTO" not in sources.upper()
    assert "id_sequences" not in sources
    assert not re.search(r"(?:RPP|PP|RVP|RPS|ALL|RO|PV)-[0-9]{6}", sources)
    assert "DROP EXTENSION" not in sources.upper()
    assert "GOOGLE" not in sources.upper()


def test_offline_postgresql_ddl_contiene_view_e_nessun_dml() -> None:
    ddl = _postgresql_ddl("20260810_0004", "20260811_0008")
    assert "CREATE VIEW tpo.v_calendario_produzione AS" in ddl
    assert ddl.count("UNION ALL") == 6
    assert "INSERT INTO" not in ddl.upper()
    assert "DROP EXTENSION" not in ddl.upper()


def test_isolated_postgresql_allocation_transition_catalog_and_constraints(isolated_postgresql) -> None:
    connection = isolated_postgresql
    command.upgrade(make_config(connection=connection), "head")
    inspector = sa.inspect(connection)
    columns = {item["name"]: item for item in inspector.get_columns("transizioni_allocazione", schema="tpo")}
    assert list(columns) == [
        "id", "allocation_id", "transition_type", "quantity",
        "replacement_allocation_id", "expected_allocation_version",
        "created_at", "created_by", "reason", "provenance",
    ]
    assert inspector.get_pk_constraint("transizioni_allocazione", schema="tpo")["name"] == "transizioni_allocazione_pkey"
    assert {item["name"] for item in inspector.get_foreign_keys("transizioni_allocazione", schema="tpo")} == {
        "transizioni_allocazione_allocation_id_fkey",
        "transizioni_allocazione_replacement_allocation_id_fkey",
    }
    assert {item["name"] for item in inspector.get_check_constraints("transizioni_allocazione", schema="tpo")} == {
        "ck_transizioni_allocazione_quantity", "ck_transizioni_allocazione_expected_version",
        "ck_transizioni_allocazione_texts", "ck_transizioni_allocazione_replacement",
        "ck_transizioni_allocazione_distinct_allocations",
    }
    assert {item["name"] for item in inspector.get_unique_constraints("transizioni_allocazione", schema="tpo")} == {"uq_transizioni_allocazione_epoch_type"}
    assert {item["name"] for item in inspector.get_indexes("transizioni_allocazione", schema="tpo")} == {
        "uq_transizioni_allocazione_epoch_type",
        "uq_transizioni_allocazione_replacement", "ix_transizioni_allocazione_allocation_epoch",
        "ix_transizioni_allocazione_allocation_created", "ix_transizioni_allocazione_replacement",
    }

    planning_row_id, order_line_id, _ = _insert_valid_planning_graph(connection)
    parent = _setup_allocation(connection, 920001, "DOMANDA", planning_row_id)
    replacement = _setup_allocation(connection, 920002, "DOMANDA", planning_row_id)
    for allocation_id in (parent, replacement):
        connection.execute(sa.text("INSERT INTO tpo.allocazioni_domanda (allocation_id, riga_ordine_id) VALUES (:allocation_id, :order_line_id)"), {"allocation_id": allocation_id, "order_line_id": order_line_id})
    _set_constraints(connection, "IMMEDIATE")

    def insert_transition(**overrides) -> None:
        values = {
            "allocation_id": parent, "transition_type": "CONSUMATA",
            "quantity": Decimal("0.4"), "replacement_allocation_id": None,
            "expected_allocation_version": 0, "created_by": "test-suite",
            "reason": "test transition", "provenance": "test-only",
        }
        values.update(overrides)
        connection.execute(sa.text("""
            INSERT INTO tpo.transizioni_allocazione (
              allocation_id, transition_type, quantity, replacement_allocation_id,
              expected_allocation_version, created_by, reason, provenance
            ) VALUES (
              :allocation_id, CAST(:transition_type AS tpo.allocation_transition_type),
              :quantity, :replacement_allocation_id, :expected_allocation_version,
              :created_by, :reason, :provenance
            )
        """), values)

    insert_transition()
    insert_transition(transition_type="SOSTITUITA", quantity=Decimal("0.6"), replacement_allocation_id=replacement)
    for overrides in (
        {"quantity": Decimal("0"), "expected_allocation_version": 1},
        {"expected_allocation_version": -1},
        {"transition_type": "RILASCIATA", "replacement_allocation_id": replacement},
        {"transition_type": "SOSTITUITA", "replacement_allocation_id": None},
        {"transition_type": "SOSTITUITA", "replacement_allocation_id": parent},
    ):
        savepoint = connection.begin_nested()
        with pytest.raises(sa.exc.DBAPIError):
            insert_transition(**overrides)
        savepoint.rollback()
    for statement in (
        "UPDATE tpo.transizioni_allocazione SET reason='changed' WHERE allocation_id=:parent",
        "DELETE FROM tpo.transizioni_allocazione WHERE allocation_id=:parent",
    ):
        savepoint = connection.begin_nested()
        with pytest.raises(sa.exc.DBAPIError, match="append-only"):
            connection.execute(sa.text(statement), {"parent": parent})
        savepoint.rollback()
    connection.rollback()


def test_isolated_postgresql_allocation_transition_commissioning_and_roundtrip(isolated_postgresql) -> None:
    connection = isolated_postgresql
    config = make_config(connection=connection)
    command.upgrade(config, "head")
    command.downgrade(config, "20260812_0009")
    assert "transizioni_allocazione" not in sa.inspect(connection).get_table_names(schema="tpo")
    command.upgrade(config, "head")
    command.downgrade(config, "20260812_0009")

    planning_row_id, order_line_id, _ = _insert_valid_planning_graph(connection)
    parent = _setup_allocation(connection, 930001, "DOMANDA", planning_row_id)
    connection.execute(sa.text("INSERT INTO tpo.allocazioni_domanda (allocation_id, riga_ordine_id) VALUES (:parent, :order_line_id)"), {"parent": parent, "order_line_id": order_line_id})
    _set_constraints(connection, "IMMEDIATE")
    connection.commit()

    for state in ("CONSUMATA", "RILASCIATA", "SOSTITUITA", "INVALIDA"):
        connection.execute(sa.text("UPDATE tpo.allocazioni SET state=:state WHERE id=:parent"), {"state": state, "parent": parent})
        connection.commit()
        with pytest.raises(RuntimeError, match="historical allocation commissioning required"):
            command.upgrade(config, "head")
        connection.rollback()
        assert "transizioni_allocazione" not in sa.inspect(connection).get_table_names(schema="tpo")

    connection.execute(sa.text("UPDATE tpo.allocazioni SET state='ATTIVA' WHERE id=:parent"), {"parent": parent})
    connection.commit()
    command.upgrade(config, "head")
    assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260905_0032"


def test_isolated_postgresql_replanning_snapshot_balance_catalog_and_checks(
    isolated_postgresql,
) -> None:
    connection = isolated_postgresql
    command.upgrade(make_config(connection=connection), "head")
    inspector = sa.inspect(connection)
    columns = {
        item["name"]: item
        for item in inspector.get_columns("replanning_snapshot_allocazioni", schema="tpo")
    }
    for name in (
        "consumed_quantity", "released_quantity", "transferred_quantity",
        "invalidated_quantity", "remaining_quantity",
    ):
        column = columns[name]
        assert column["nullable"] is False
        assert isinstance(column["type"], sa.Numeric)
        assert (column["type"].precision, column["type"].scale) == (20, 6)
        assert column["default"] is None
    checks = {
        item["name"]: item["sqltext"]
        for item in inspector.get_check_constraints(
            "replanning_snapshot_allocazioni", schema="tpo"
        )
    }
    quantitative = checks["ck_replanning_snapshot_allocazioni_quantity"]
    assert re.search(
        r"remaining_quantity\s*=\s*\(*\s*allocated_quantity"
        r"\s*-\s*consumed_quantity"
        r"\s*-\s*released_quantity"
        r"\s*-\s*transferred_quantity"
        r"\s*-\s*invalidated_quantity\s*\)*",
        quantitative,
    )

    planning_row_id, order_line_id, _ = _resolve_valid_planning_graph(connection)
    allocation_id = _setup_allocation(connection, 940001, "DOMANDA", planning_row_id)
    connection.execute(sa.text(
        "INSERT INTO tpo.allocazioni_domanda (allocation_id,riga_ordine_id) "
        "VALUES (:allocation_id,:order_line_id)"
    ), {"allocation_id": allocation_id, "order_line_id": order_line_id})
    snapshot_id = _insert_replanning_snapshot(connection, 940001)

    def insert_snapshot(*, consumed=Decimal("0.2"), remaining=Decimal("0.8")) -> None:
        connection.execute(sa.text("""
            INSERT INTO tpo.replanning_snapshot_allocazioni (
              snapshot_id,posizione,allocation_public_id,allocation_type,
              source_public_id,destination_order_line_public_id,
              allocated_quantity,consumed_quantity,released_quantity,
              transferred_quantity,invalidated_quantity,remaining_quantity,
              unita_misura,allocation_state,allocation_version
            ) VALUES (
              :snapshot_id,1,'ALL-940001','DOMANDA','RO-990001','RO-990001',
              1,:consumed,0,0,0,:remaining,'SET','ATTIVA',0
            )
        """), {"snapshot_id": snapshot_id, "consumed": consumed, "remaining": remaining})

    insert_snapshot()
    _set_constraints(connection, "IMMEDIATE")
    connection.rollback()

    for consumed, remaining in ((Decimal("-0.1"), Decimal("1.1")),
                                (Decimal("0.2"), Decimal("0.7"))):
        planning_row_id, order_line_id, _ = _resolve_valid_planning_graph(connection)
        allocation_id = _setup_allocation(connection, 940001, "DOMANDA", planning_row_id)
        connection.execute(sa.text(
            "INSERT INTO tpo.allocazioni_domanda (allocation_id,riga_ordine_id) "
            "VALUES (:allocation_id,:order_line_id)"
        ), {"allocation_id": allocation_id, "order_line_id": order_line_id})
        snapshot_id = _insert_replanning_snapshot(connection, 940001)
        with pytest.raises(sa.exc.DBAPIError):
            insert_snapshot(consumed=consumed, remaining=remaining)
        connection.rollback()
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        connection.rollback()


def test_isolated_postgresql_replanning_snapshot_historical_gate_atomic(
    isolated_postgresql,
) -> None:
    connection = isolated_postgresql
    config = make_config(connection=connection)
    command.upgrade(config, "head")
    planning_row_id, order_line_id, _ = _resolve_valid_planning_graph(connection)
    allocation_id = _setup_allocation(connection, 950001, "DOMANDA", planning_row_id)
    connection.execute(sa.text(
        "INSERT INTO tpo.allocazioni_domanda (allocation_id,riga_ordine_id) "
        "VALUES (:allocation_id,:order_line_id)"
    ), {"allocation_id": allocation_id, "order_line_id": order_line_id})
    snapshot_id = _insert_replanning_snapshot(connection, 950001)
    connection.execute(sa.text("""
        INSERT INTO tpo.replanning_snapshot_allocazioni (
          snapshot_id,posizione,allocation_public_id,allocation_type,
          source_public_id,destination_order_line_public_id,allocated_quantity,
          consumed_quantity,released_quantity,transferred_quantity,
          invalidated_quantity,remaining_quantity,
          unita_misura,allocation_state,allocation_version
        ) VALUES (
          :snapshot_id,1,'ALL-950001','DOMANDA','RO-990001','RO-990001',
          1,0,0,0,0,1,'SET','ATTIVA',0
        )
    """), {"snapshot_id": snapshot_id})
    _set_constraints(connection, "IMMEDIATE")
    connection.commit()
    command.downgrade(config, "20260814_0010")
    assert connection.exec_driver_sql(
        "SELECT version_num FROM alembic_version"
    ).scalar_one() == "20260814_0010"
    connection.commit()

    with pytest.raises(
        RuntimeError,
        match="historical replanning allocation snapshot commissioning required",
    ):
        command.upgrade(config, "head")
    connection.rollback()
    assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260814_0010"
    columns = {
        item["name"]
        for item in sa.inspect(connection).get_columns(
            "replanning_snapshot_allocazioni", schema="tpo"
        )
    }
    assert "remaining_quantity" not in columns
    connection.execute(sa.text("""
        DELETE FROM tpo.replanning_snapshot_allocazioni
        WHERE allocation_public_id='ALL-950001'
    """))
    _set_constraints(connection, "IMMEDIATE")
    assert connection.exec_driver_sql("""
        SELECT count(*) FROM tpo.replanning_snapshot_allocazioni
    """).scalar_one() == 0
    connection.commit()
    assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    connection.rollback()


def test_isolated_postgresql_replanning_snapshot_balance_roundtrip(
    isolated_postgresql,
) -> None:
    connection = isolated_postgresql
    config = make_config(connection=connection)
    command.upgrade(config, "head")
    assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "20260905_0032"


def test_isolated_postgresql_zero_production_line_contract(
    isolated_postgresql,
) -> None:
    connection = isolated_postgresql
    config = make_config(connection=connection)
    command.upgrade(config, "head")
    planning_row_id, _, _ = _resolve_valid_planning_graph(connection)
    connection.commit()

    connection.execute(sa.text("""
        UPDATE tpo.righe_piano_semina
        SET copertura_stock=1, deficit_produttivo=0,
            buffer_quantitativo_calcolato=0, quantita_pre_granularita=0,
            quantita_produttiva_autorizzata=0, quantita_avviata=0,
            quantita_residua_da_avviare=0, grammi_seme_richiesti=NULL
        WHERE id=:planning_row_id
    """), {"planning_row_id": planning_row_id})
    connection.commit()

    row = connection.execute(sa.text("""
        SELECT quantita_produttiva_autorizzata,grammi_seme_richiesti
        FROM tpo.righe_piano_semina WHERE id=:planning_row_id
    """), {"planning_row_id": planning_row_id}).one()
    assert row == (Decimal("0.000000"), None)

    invalid_pairs = (
        (Decimal("0"), Decimal("1")),
        (Decimal("1"), None),
        (Decimal("1"), Decimal("0")),
    )
    for productive, grams in invalid_pairs:
        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.execute(sa.text("""
                UPDATE tpo.righe_piano_semina
                SET quantita_produttiva_autorizzata=:productive,
                    quantita_residua_da_avviare=:productive,
                    grammi_seme_richiesti=:grams
                WHERE id=:planning_row_id
            """), {
                "productive": productive,
                "grams": grams,
                "planning_row_id": planning_row_id,
            })
    assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1

    connection.execute(sa.text("""
        UPDATE tpo.righe_piano_semina
        SET copertura_stock=0, deficit_produttivo=1,
            buffer_quantitativo_calcolato=0, quantita_pre_granularita=1,
            quantita_produttiva_autorizzata=1, quantita_avviata=0,
            quantita_residua_da_avviare=1, grammi_seme_richiesti=1
        WHERE id=:planning_row_id
    """), {"planning_row_id": planning_row_id})
    connection.commit()


def test_isolated_postgresql_zero_production_historical_and_downgrade_gates(
    isolated_postgresql,
) -> None:
    connection = isolated_postgresql
    config = make_config(connection=connection)
    command.upgrade(config, "head")
    planning_row_id, _, _ = _resolve_valid_planning_graph(connection)
    connection.commit()
    command.downgrade(config, "20260814_0012")

    connection.execute(sa.text("""
        UPDATE tpo.righe_piano_semina
        SET copertura_stock=1, deficit_produttivo=0,
            buffer_quantitativo_calcolato=0, quantita_pre_granularita=0,
            quantita_produttiva_autorizzata=0, quantita_avviata=0,
            quantita_residua_da_avviare=0, grammi_seme_richiesti=1
        WHERE id=:planning_row_id
    """), {"planning_row_id": planning_row_id})
    connection.commit()
    with pytest.raises(
        RuntimeError,
        match="zero-production planning line commissioning required",
    ):
        command.upgrade(config, "head")
    connection.rollback()
    assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1

    connection.execute(sa.text("""
        UPDATE tpo.righe_piano_semina
        SET copertura_stock=0, deficit_produttivo=1,
            buffer_quantitativo_calcolato=0, quantita_pre_granularita=1,
            quantita_produttiva_autorizzata=1, quantita_avviata=0,
            quantita_residua_da_avviare=1, grammi_seme_richiesti=1
        WHERE id=:planning_row_id
    """), {"planning_row_id": planning_row_id})
    connection.commit()
    command.upgrade(config, "head")

    connection.execute(sa.text("""
        UPDATE tpo.righe_piano_semina
        SET copertura_stock=1, deficit_produttivo=0,
            buffer_quantitativo_calcolato=0, quantita_pre_granularita=0,
            quantita_produttiva_autorizzata=0, quantita_avviata=0,
            quantita_residua_da_avviare=0, grammi_seme_richiesti=NULL
        WHERE id=:planning_row_id
    """), {"planning_row_id": planning_row_id})
    connection.commit()
    with pytest.raises(
        RuntimeError,
        match="zero-production planning line downgrade commissioning required",
    ):
        command.downgrade(config, "20260814_0012")
    connection.rollback()
    assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1

    connection.execute(sa.text("""
        UPDATE tpo.righe_piano_semina
        SET copertura_stock=0, deficit_produttivo=1,
            buffer_quantitativo_calcolato=0, quantita_pre_granularita=1,
            quantita_produttiva_autorizzata=1, quantita_avviata=0,
            quantita_residua_da_avviare=1, grammi_seme_richiesti=1
        WHERE id=:planning_row_id
    """), {"planning_row_id": planning_row_id})
    connection.commit()
    command.downgrade(config, "20260814_0012")
    command.upgrade(config, "head")
