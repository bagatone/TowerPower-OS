"""Inventario semi, vaschette e substrato (15/10/2026): sola lettura, su PostgreSQL usa-e-getta."""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import psycopg

from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-15_inventario.py"


def _module():
    spec = importlib.util.spec_from_file_location("inventario", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def _seed(engine):
    with engine.begin() as c:
        seed = c.exec_driver_sql(
            "INSERT INTO tpo.sementi(fornitore,referenza_commerciale,created_by,updated_at,updated_by) "
            "VALUES ('Intersemillas','Rucola coltivata','test',CURRENT_TIMESTAMP,'test') RETURNING id").scalar_one()
        c.exec_driver_sql(
            "INSERT INTO tpo.lotti_seme(public_id,semente_id,numero_lotto_produttore,data_ricezione,quantita_iniziale,"
            "quantita_residua,unita_misura,anomalia,created_by,updated_at,updated_by) "
            "VALUES ('LSE-990001',%s,'L-1',DATE '2026-09-01',100,40.5,'GRAM','umido','test',CURRENT_TIMESTAMP,'test')",
            (seed,))
        c.exec_driver_sql("INSERT INTO tpo.articoli(public_id,denominazione,unita_misura,created_by) VALUES "
                          "('ART-990001','Vaschette','UNIT','test'),('ART-990002','Substrato fibra di cocco','UNIT','test'),"
                          "('ART-990003','Guanti','UNIT','test')")
        for art, qty in (("ART-990001", 2744), ("ART-990002", 2740), ("ART-990003", 10)):
            c.exec_driver_sql(
                "INSERT INTO tpo.stock_articoli(articolo_id,disponibile,unita_misura,updated_at,version) "
                "SELECT id,%s,'UNIT',CURRENT_TIMESTAMP,0 FROM tpo.articoli WHERE public_id=%s", (qty, art))


def test_inventory_lists_lots_and_articles_and_writes_nothing_but_the_csv(writer_postgresql_engine, tmp_path):
    engine = writer_postgresql_engine
    _seed(engine)
    module, lines = _module(), []
    conn = _connect(engine)
    csv_file = tmp_path / "inv.csv"
    assert module.run(conn, str(csv_file), out=lines.append) == 0
    conn.close()
    text = "\n".join(lines)
    assert "LSE-990001 | Intersemillas | Rucola coltivata | L-1 | 01/09/2026 | - | 100 GRAM | 40.5 GRAM" in text
    assert "umido" in text and "TOTALE semi residui a sistema: 40.5 g in 1 lotti" in text
    assert "ART-990001 | Vaschette | 2744 UNIT | - | 686 SET" in text
    assert "ART-990002 | Substrato fibra di cocco | 2740 UNIT | - | 685 SET" in text
    assert "ART-990003 | Guanti | 10 UNIT | - | -" in text
    rows = list(csv.reader(csv_file.open(encoding="utf-8")))
    assert rows[0][0] == "tipo" and sum(1 for r in rows if r[0] == "SEME") == 1
    assert sum(1 for r in rows if r[0] == "MATERIALE") == 3


def test_package_creates_folder_with_report_csv_and_zip(writer_postgresql_engine, tmp_path):
    import zipfile
    from datetime import date
    engine = writer_postgresql_engine
    _seed(engine)
    module, lines = _module(), []
    conn = _connect(engine)
    assert module.pacchetto(conn, str(tmp_path), oggi=date(2026, 10, 15), out=lines.append) == 0
    conn.close()
    cartella = tmp_path / "inventario_2026-10-15"
    assert (cartella / "inventario.txt").read_text(encoding="utf-8").startswith("Tower Power - inventario del 15/10/2026")
    assert "LSE-990001" in (cartella / "inventario.csv").read_text(encoding="utf-8")
    with zipfile.ZipFile(tmp_path / "inventario_2026-10-15.zip") as z:
        assert sorted(z.namelist()) == ["inventario_2026-10-15/inventario.csv", "inventario_2026-10-15/inventario.txt"]
    assert any(l.startswith("ZIP_PER_MAIL:") for l in lines)
