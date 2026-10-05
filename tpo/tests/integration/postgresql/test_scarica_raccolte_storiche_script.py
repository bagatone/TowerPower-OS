"""Anteprima dello script raccolte storiche vendute su PostgreSQL reale di prova."""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import psycopg

from src.tpo_core.cli import main as main_module
from tests.infrastructure.postgresql.test_production_planning_migrations import (  # noqa: F401
    isolated_postgresql,
)
from tests.integration.postgresql.test_movimento_carico import seeded_raccolta  # noqa: F401
from tests.integration.postgresql.test_raccolta import harvest_environment  # noqa: F401
from tests.integration.postgresql.test_semina_commissioning import environment  # noqa: F401

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-05_scarica_raccolte_storiche.py"


def _module():
    spec = importlib.util.spec_from_file_location("scarica_raccolte_storiche", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module      # le dataclass risolvono le annotazioni da qui
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def _movements(engine) -> int:
    with engine.connect() as connection:
        return connection.exec_driver_sql("SELECT count(*) FROM tpo.movimenti_magazzino").scalar_one()


def _declared(module, engine, quantity: Decimal):
    with engine.connect() as connection:
        name = connection.exec_driver_sql(
            "SELECT v.denominazione FROM tpo.raccolte r JOIN tpo.semine s ON s.id=r.semina_id "
            "JOIN tpo.varieta v ON v.id=s.varieta_id WHERE r.public_id='RAC-000001'").scalar_one()
    module.ATTESE.clear()
    module.ATTESE["RAC-000001"] = (name, quantity)


def test_preview_writes_nothing_and_commands_parse_with_the_real_cli(seeded_raccolta):
    engine, _ = seeded_raccolta
    module, lines = _module(), []
    _declared(module, engine, Decimal("0.5"))
    before = _movements(engine)

    conn = _connect(engine)
    assert module.run(conn, False, out=lines.append) == 0
    conn.close()
    text = "\n".join(lines)
    assert "ANTEPRIMA: nulla scritto" in text and "carica-raccolta" in text and "rettifica-giacenza" in text
    assert _movements(engine) == before

    conn = _connect(engine)
    cursor = conn.cursor()
    found = module._find(cursor, ("RAC-000001",))
    conn.close()
    parser = main_module._parser()
    for _scope, args, _key, _label in module.commands(found["RAC-000001"]):
        parsed = parser.parse_args(args)
        assert parsed.confirm and parsed.idempotency_key and parsed.unita_misura == "SET"


def test_stops_when_database_differs_from_declared(seeded_raccolta):
    engine, _ = seeded_raccolta
    module, lines = _module(), []
    _declared(module, engine, Decimal("7"))
    conn = _connect(engine)
    assert module.run(conn, True, out=lines.append) == 3
    conn.close()
    assert "STOP" in "\n".join(lines) and _movements(engine) == 0
