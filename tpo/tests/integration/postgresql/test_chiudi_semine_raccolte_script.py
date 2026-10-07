"""Anteprima dello script di chiusura semine gia' raccolte; comandi accettati dal parser CLI reale."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from src.tpo_core.cli import main as main_module
from tests.infrastructure.postgresql.test_production_planning_migrations import (  # noqa: F401
    isolated_postgresql,
)
from tests.integration.postgresql.test_movimento_carico import seeded_raccolta  # noqa: F401
from tests.integration.postgresql.test_raccolta import harvest_environment  # noqa: F401
from tests.integration.postgresql.test_semina_commissioning import environment  # noqa: F401

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-06_chiudi_semine_raccolte.py"
NOW = datetime(2030, 1, 1, 12, tzinfo=timezone(timedelta(hours=1)))


def _module():
    spec = importlib.util.spec_from_file_location("chiudi_semine_raccolte", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username, autocommit=True)


def test_preview_lists_raccolte_writes_nothing_and_command_parses(seeded_raccolta):
    engine, _ = seeded_raccolta
    module, lines = _module(), []
    with engine.connect() as c:
        semina = c.exec_driver_sql("SELECT s.public_id FROM tpo.raccolte r JOIN tpo.semine s ON s.id=r.semina_id "
                                   "LIMIT 1").scalar_one()
        before = c.exec_driver_sql("SELECT stato::text, version FROM tpo.semine ORDER BY id").all()
    conn = _connect(engine)
    assert module.run(conn, [semina], "raccolta completa", NOW, False, out=lines.append) == 0
    text = "\n".join(lines)
    assert "ANTEPRIMA" in text and "raccolta RAC-" in text and "verra' CHIUSA" in text
    with engine.connect() as c:
        assert c.exec_driver_sql("SELECT stato::text, version FROM tpo.semine ORDER BY id").all() == before
    cur = conn.cursor()
    row = module.read_semina(cur, semina)
    reason = module.reason_for(semina, row[4], row[5], module.read_raccolte(cur, row[0]))
    conn.close()
    parsed = main_module._parser().parse_args(module.build_command(semina, row[2], NOW, "raccolta completa", reason)[1:])
    assert parsed.confirm and parsed.target_state == "CHIUSA" and parsed.final_outcome == "raccolta completa"


def test_stops_when_semina_is_not_ready_or_missing(seeded_raccolta):
    engine, _ = seeded_raccolta
    module, lines = _module(), []
    conn = _connect(engine)
    assert module.run(conn, ["SEM-999999"], "raccolta completa", NOW, True, out=lines.append) == 1
    conn.close()
    assert "inesistente" in "\n".join(lines)
