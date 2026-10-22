"""Elenco clienti (22/10/2026, sola lettura): conteggi e ultima consegna per cliente, filtro per nome, nulla scritto."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import psycopg

from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-22_elenco_clienti.py"


def _module():
    spec = importlib.util.spec_from_file_location("elenco_clienti", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def _dati(engine):
    with engine.begin() as c:
        ids = {}
        for pid, nome in (("CLI-990004", "Selvaje"), ("CLI-990014", "Salvaje "), ("CLI-990020", "Altro ristorante")):
            ids[pid] = c.exec_driver_sql(
                "INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by) "
                "VALUES (%s,%s,'test',CURRENT_TIMESTAMP,'test') RETURNING id", (pid, nome)).scalar_one()
        c.exec_driver_sql(
            "INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,created_by) "
            "VALUES ('ORD-990001',%s,CURRENT_DATE,CURRENT_DATE,'APERTO','MANUALE','test')", (ids["CLI-990004"],))
        c.exec_driver_sql(
            "INSERT INTO tpo.consegne(public_id,cliente_id,stato,data_prevista,data_effettiva,created_by) "
            "VALUES ('CON-990001',%s,'CONSEGNATA',%s,%s,'test')",
            (ids["CLI-990004"], date(2026, 10, 18), date(2026, 10, 18)))


def test_lists_clients_with_counts_and_filters_by_name(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _dati(engine)
    m, conn = _module(), _connect(engine)
    tutte = []
    assert m.run(conn, "", out=tutte.append) == 0
    testo = "\n".join(tutte)
    assert "CLI-990004 | Selvaje | 1 ordini | 1 consegne (ultima 18/10/2026) | 0 programmi" in testo
    assert "CLI-990014 | Salvaje  | 0 ordini | 0 consegne (ultima -) | 0 programmi" in testo
    solo = []
    assert m.run(conn, "SALVAJE", out=solo.append) == 0
    assert "CLI-990014" in "\n".join(solo) and "CLI-990004" not in "\n".join(solo) and "CLI-990020" not in "\n".join(solo)
    conn.close()
    with engine.connect() as c:
        assert c.exec_driver_sql("SELECT count(*) FROM tpo.clienti").scalar_one() >= 3
