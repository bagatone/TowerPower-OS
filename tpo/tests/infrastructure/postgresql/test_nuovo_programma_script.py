"""Nuovo programma di fornitura ricorrente: anteprima, rifiuti e comando costruito, su PostgreSQL usa-e-getta."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import psycopg

from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    _seed,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-08_nuovo_programma.py"
TODAY = date(2026, 10, 8)


def _module():
    spec = importlib.util.spec_from_file_location("nuovo_programma", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def _count(engine, table):
    with engine.connect() as connection:
        return connection.exec_driver_sql(f"SELECT count(*) FROM tpo.{table}").scalar_one()


def test_preview_writes_nothing_and_execute_builds_the_governed_command(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _seed(engine, 960001)
    module, lines, calls = _module(), [], []

    def runner(args):
        calls.append(args)
        return SimpleNamespace(stdout="STATUS: INSERTED\nENTITY: PROGRAMMA_FORNITURA\n", stderr="", returncode=0)

    conn = _connect(engine)
    assert module.run(conn, "writer client 960001", ["writer variety 960001:2"], date(2026, 10, 20), 14,
                      "ricorrente ogni 2 settimane", False, today=TODAY, out=lines.append, runner=runner) == 0
    text = "\n".join(lines)
    assert "PF-000001" in text and "martedi'" in text and "2026-10-20, 2026-11-03" in text
    assert "ANTEPRIMA: nulla e' stato scritto" in text and calls == [] and _count(engine, "programmi_fornitura") == 0

    assert module.run(conn, "writer client 960001", ["writer variety 960001:2"], date(2026, 10, 20), 14,
                      "ricorrente ogni 2 settimane", True, today=TODAY, out=lines.append, runner=runner) == 0
    conn.close()
    args = calls[0]
    assert args[1:4] == ["onboarding", "supply-program", "--program-id"] and "PF-000001" in args
    assert "CLI-960001" in args and "VAR-960001,2,SET,OGNI_X_GIORNI,14," in args
    assert args[args.index("--start-date") + 1] == "2026-10-20"
    assert args[args.index("--generation-time") + 1] == "05:00"
    assert args[args.index("--operational-window-days") + 1] == "14"


def test_refusals_write_nothing(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _seed(engine, 960002)
    with engine.begin() as connection:                       # un programma ATTIVO corrente gia' esistente
        client = connection.exec_driver_sql("SELECT id FROM tpo.clienti WHERE public_id='CLI-960002'").scalar_one()
        pf = connection.exec_driver_sql(
            "INSERT INTO tpo.programmi_fornitura(public_id,cliente_id,created_by) VALUES ('PF-000007',%s,'test') "
            "RETURNING id", (client,)).scalar_one()
        connection.exec_driver_sql(
            "INSERT INTO tpo.programmi_fornitura_versioni(programma_fornitura_id,cliente_id,numero_versione,stato,"
            "data_inizio,finestra_operativa_giorni,valida_dal,created_by) "
            "VALUES (%s,%s,1,'ATTIVO','2026-08-25',14,'2026-08-24T23:00:00+00:00','test')", (pf, client))
    module, lines, calls = _module(), [], []
    before = _count(engine, "programmi_fornitura")
    cases = [
        ("writer client 960002", ["writer variety 960002:2"], date(2026, 10, 20), 14),   # ha gia' un ATTIVO
        ("Cliente inesistente", ["writer variety 960002:2"], date(2026, 10, 20), 14),
        ("writer client 960002", ["Varieta inesistente:2"], date(2026, 10, 20), 14),
        ("writer client 960002", ["writer variety 960002:0"], date(2026, 10, 20), 14),
        ("writer client 960002", ["writer variety 960002:1", "writer variety 960002:2"], date(2026, 10, 20), 14),
        ("writer client 960002", ["writer variety 960002:2"], date(2026, 10, 1), 14),     # nel passato
        ("writer client 960002", ["writer variety 960002:2"], date(2026, 10, 20), 0),     # intervallo non valido
        ("writer client 960002", [], date(2026, 10, 20), 14),
    ]
    for cliente, righe, prima, ogni in cases:
        conn = _connect(engine)
        assert module.run(conn, cliente, righe, prima, ogni, "x", True, today=TODAY, out=lines.append,
                          runner=lambda a: calls.append(a)) == 2
        conn.close()
    assert "RIFIUTATO" in "\n".join(lines) and "PF-000007" in "\n".join(lines)
    assert calls == [] and _count(engine, "programmi_fornitura") == before
