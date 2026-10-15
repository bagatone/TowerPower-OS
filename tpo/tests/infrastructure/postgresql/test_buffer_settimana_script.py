"""Report del buffer settimanale (16/10/2026): analisi pura e letture su PostgreSQL usa-e-getta. Sola lettura."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg

from tests.infrastructure.postgresql.test_production_planning_commit_writer import (  # noqa: F401
    migration_postgresql, writer_cluster, writer_database,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-16_buffer_settimana.py"
OGGI = date(2026, 10, 15)


def _module():
    spec = importlib.util.spec_from_file_location("buffer_settimana", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username, autocommit=True)


def test_settimana_buckets_past_current_and_beyond_the_horizon():
    m = _module()
    assert m.settimana(date(2026, 9, 1), OGGI, 3) == 1 and m.settimana(OGGI, OGGI, 3) == 1
    assert m.settimana(OGGI + timedelta(days=6), OGGI, 3) == 1 and m.settimana(OGGI + timedelta(days=7), OGGI, 3) == 2
    assert m.settimana(OGGI + timedelta(days=20), OGGI, 3) == 3 and m.settimana(OGGI + timedelta(days=21), OGGI, 3) is None


def test_analysis_adds_the_buffer_once_per_week_and_sizes_the_sowing():
    m = _module()
    proto = {"nome": "Afila", "ciclo": 10, "resa": Decimal("0.8"), "gran": Decimal("0.5")}
    righe, atterra, k, seminare, tardi = m.analizza(
        proto, {1: Decimal(3), 2: Decimal(2)}, Decimal("0.5"), {1: Decimal("4.5"), 2: Decimal(1)}, OGGI, 3, Decimal(1))
    assert [(r["k"], r["serve"], r["manca"]) for r in righe] == [(1, 4, 0), (2, 3, 2), (3, 1, 1)]
    assert atterra == date(2026, 10, 25) and k == 2
    assert seminare == Decimal("2.5")                 # 2 / 0.8 = 2.5 SET da seminare, gia' multiplo di 0.5
    assert tardi == []


def test_shortfall_before_the_landing_week_is_flagged_as_too_late():
    m = _module()
    proto = {"nome": "Cilantro", "ciclo": 15, "resa": Decimal(1), "gran": Decimal("0.5")}
    righe, _, k, seminare, tardi = m.analizza(proto, {1: Decimal(2)}, Decimal(0), {}, OGGI, 3, Decimal(1))
    assert k == 3 and tardi == [1, 2] and seminare == Decimal(1)         # sett. 3: manca solo la scorta
    righe, _, k, seminare, tardi = m.analizza({**proto, "ciclo": 40}, {}, Decimal(0), {}, OGGI, 3, Decimal(1))
    assert k is None and seminare == 0 and tardi == [1, 2, 3]


def test_report_reads_orders_stock_and_semine_from_the_database(writer_database):
    engine = writer_database
    m = _module()
    lines = []
    conn = _connect(engine)
    assert m.run(conn, 3, Decimal(1), scelte=["Writer test variety"], oggi=OGGI, out=lines.append) == 0
    text = "\n".join(lines)
    assert "Alto consumo (scelto da te): Writer test variety" in text and "ALTO CONSUMO" in text
    assert "SOLA LETTURA" in text and "Writer test variety" in text
    # ordine ORD-000001 (1 SET, consegna 15/8, scaduto) -> sett. 1; magazzino 2; scorta 1 -> serve 2, manca 0
    blocco = text[text.index("Writer test variety"):]
    assert "   1 |      1 |      1 = 2      |         2 |     0 |     0" in blocco
    assert "   2 |      0 |      1 = 1      |         0 |     0 |     1" in blocco
    assert "-> SEMINA OGGI: 1 SET (copre la sett. 2: manca 1)" in blocco
    assert "Totale: 1 SET" in blocco
    # una semina in campo con finestra nella sett. 2 copre il buffer: nulla da seminare
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.exec_driver_sql("""
          INSERT INTO tpo.semine
            (public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,protocollo_versione_id,stato,
             quantita_seme,unita_misura,data_avvio,causa_origine,cultivar_snapshot,uso_produttivo_snapshot,
             lotto_seme_snapshot,protocollo_snapshot,created_by,codice_tracciabilita,expected_useful_quantity,
             expected_useful_uom,harvest_window_start,harvest_window_end)
          SELECT 'SEM-000901',v.id,1,1,1,1,'CRESCITA',25,'GRAM','2026-10-10','PIANO_PRODUZIONE','x','x','x','x','test',
                 'TST-1510-A',2,'SET','2026-10-24 06:00+01','2026-10-28 06:00+01'
          FROM tpo.varieta v WHERE v.public_id='VAR-000001'""")
        connection.exec_driver_sql("""
          INSERT INTO tpo.raccolte(public_id,semina_id,data_raccolta,quantita,unita_misura,created_by)
          SELECT 'RAC-000901',id,'2026-10-14 08:00+01',0.5,'SET','test' FROM tpo.semine WHERE public_id='SEM-000901'""")
    lines.clear()
    assert m.run(conn, 3, Decimal(1), scelte=["writer TEST variety"], oggi=OGGI, out=lines.append) == 0
    text = "\n".join(lines)
    assert "   2 |      0 |      1 = 1      |         0 |   1.5 |     0" in text
    assert "niente da seminare oggi per la sett. 2" in text and "Totale:" not in text
    assert "2026-10-12_semine.py --riga" in text
    # senza scelta e senza consumo recente nessuna varieta' e' ad alto consumo: niente scorta, niente semina
    lines.clear()
    assert m.run(conn, 3, Decimal(1), oggi=OGGI, out=lines.append) == 0
    text = "\n".join(lines)
    assert "Alto consumo (>= 2 SET/sett., media delle ultime 4 settimane): nessuna" in text
    assert "senza scorta" in text and "-> SEMINA OGGI" not in text
    # nome sconosciuto: si ferma
    lines.clear()
    assert m.run(conn, 3, Decimal(1), scelte=["Inesistente"], oggi=OGGI, out=lines.append) == 2
    assert "varieta' sconosciute" in "\n".join(lines)
    conn.close()


def test_high_consumption_by_threshold_or_by_choice():
    m = _module()
    protocolli = {1: {"nome": "Afila"}, 2: {"nome": "Cilantro"}, 3: {"nome": "Rábano"}}
    consumo = {1: Decimal("3.5"), 2: Decimal("1.0"), 3: Decimal(2)}
    assert m.alto_consumo(protocolli, consumo, Decimal(2), None) == ({1, 3}, [])
    assert m.alto_consumo(protocolli, consumo, Decimal(0), None) == ({1, 2, 3}, [])
    assert m.alto_consumo(protocolli, consumo, Decimal(2), ["cilantro", "rabano"]) == ({2, 3}, [])
    assert m.alto_consumo(protocolli, consumo, Decimal(2), ["Afila", "Xyz"]) == ({1}, ["xyz"])

