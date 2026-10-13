"""Spostamento del giorno di un programma di fornitura (12/10/2026, La Jaira martedi' -> lunedi'), su PostgreSQL usa-e-getta."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import psycopg

from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    _seed,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-12_sposta_giorno_programma.py"
TODAY = date(2026, 10, 12)


def _module():
    spec = importlib.util.spec_from_file_location("sposta_giorno", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def _programma(engine, number, *, stato="ATTIVO", tipo="OGNI_X_GIORNI", giorni_iso=None):
    """Programma PF-9xxxxx del cliente seminato, ancora 1/9 (martedi'), 14 giorni, un ordine stantio (13/10) e uno
    coerente col nuovo ritmo (26/10)."""
    _seed(engine, number)
    with engine.begin() as connection:
        client = connection.exec_driver_sql(f"SELECT id FROM tpo.clienti WHERE public_id='CLI-{number:06d}'").scalar_one()
        var = connection.exec_driver_sql(f"SELECT id FROM tpo.varieta WHERE public_id='VAR-{number:06d}'").scalar_one()
        pf = connection.exec_driver_sql(
            "INSERT INTO tpo.programmi_fornitura(public_id,cliente_id,created_by) VALUES (%s,%s,'test') RETURNING id",
            (f"PF-{number:06d}", client)).scalar_one()
        version = connection.exec_driver_sql(
            "INSERT INTO tpo.programmi_fornitura_versioni(programma_fornitura_id,cliente_id,numero_versione,stato,"
            "data_inizio,finestra_operativa_giorni,valida_dal,created_by) "
            "VALUES (%s,%s,2,%s,'2026-09-01',14,'2026-09-01T00:00:00+00:00','test') RETURNING id",
            (pf, client, stato)).scalar_one()
        riga = connection.exec_driver_sql(
            "INSERT INTO tpo.righe_programma_fornitura(programma_versione_id,posizione,varieta_id,quantita,unita_misura,"
            "tipo_ricorrenza,intervallo_giorni) VALUES (%s,1,%s,1,'SET',%s,%s) RETURNING id",
            (version, var, tipo, 14 if tipo == "OGNI_X_GIORNI" else None)).scalar_one()
        if giorni_iso:
            connection.exec_driver_sql("INSERT INTO tpo.righe_programma_giorni(riga_programma_id,giorno_iso) VALUES (%s,%s)",
                                       (riga, giorni_iso))
        run = connection.exec_driver_sql(
            "INSERT INTO tpo.runs(public_id,started_at,completed_at,simulation,state,programmi_letti,righe_valutate,"
            "occorrenze_valutate,ordini_generati,elementi_saltati,created_by) VALUES (%s,now(),now(),false,'SUCCESS',"
            "1,1,1,1,0,'test') RETURNING id", (f"RUN-{number:06d}",)).scalar_one()
        for n, data in ((number + 100, "2026-10-13"), (number + 200, "2026-10-26")):
            connection.exec_driver_sql(
                "INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,"
                "run_id,programma_fornitura_id,chiave_idempotenza,created_by) "
                "VALUES (%s,%s,'2026-10-01',%s,'APERTO','AUTOMATICO',%s,%s,%s,'test')",
                (f"ORD-{n:06d}", client, data, run, pf, f"chiave-{n}"))
    return f"PF-{number:06d}"


def _versions(engine, pf):
    with engine.connect() as connection:
        return connection.exec_driver_sql("""
          SELECT pv.numero_versione, pv.stato::text, pv.data_inizio, pv.valida_al IS NULL, pv.finestra_operativa_giorni
          FROM tpo.programmi_fornitura_versioni pv JOIN tpo.programmi_fornitura p ON p.id=pv.programma_fornitura_id
          WHERE p.public_id=%s ORDER BY pv.numero_versione""", (pf,)).all()


def test_preview_writes_nothing_and_flags_the_stale_order(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960101)
    module, lines = _module(), []
    conn = _connect(engine)
    assert module.run(conn, pf, date(2026, 10, 26), "martedi' -> lunedi'", False, today=TODAY, out=lines.append) == 0
    conn.close()
    text = "\n".join(lines)
    assert "martedi' 2026-09-01" in text and "lunedi' 2026-10-26" in text
    assert "prima: martedi' 2026-10-13, martedi' 2026-10-27" in text
    assert "dopo : lunedi' 2026-10-26, lunedi' 2026-11-09" in text
    assert "ORD-960201" in text and "NON ricorre piu' col nuovo ritmo" in text
    assert "modifica_ordine.py annulla ORD-960201" in text
    assert "ORD-960301" in text and "coerente col nuovo ritmo" in text
    assert "modifica_ordine.py annulla ORD-960301" not in text
    assert "ANTEPRIMA: nulla e' stato scritto" in text
    assert [v[0] for v in _versions(engine, pf)] == [2]


def test_execute_closes_the_old_version_and_opens_the_new_one_with_the_same_lines(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960102)
    module, lines = _module(), []
    conn = _connect(engine)
    assert module.run(conn, pf, date(2026, 10, 26), "La Jaira: da martedi' a lunedi'", True, today=TODAY,
                      out=lines.append) == 0
    conn.close()
    versions = _versions(engine, pf)
    assert [(v[0], v[1], v[2], v[3], v[4]) for v in versions] == [
        (2, "ATTIVO", date(2026, 9, 1), False, 14), (3, "ATTIVO", date(2026, 10, 26), True, 14)]
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("""
          SELECT r.posizione, r.quantita, r.tipo_ricorrenza::text, r.intervallo_giorni
          FROM tpo.righe_programma_fornitura r JOIN tpo.programmi_fornitura_versioni pv ON pv.id=r.programma_versione_id
          JOIN tpo.programmi_fornitura p ON p.id=pv.programma_fornitura_id
          WHERE p.public_id=%s AND pv.numero_versione=3""", (pf,)).all()
        audit = connection.exec_driver_sql(
            "SELECT operation::text, before_data, after_data FROM tpo.audit_eventi WHERE entity_public_id=%s", (pf,)
        ).all()
        orders = connection.exec_driver_sql(
            "SELECT count(*) FROM tpo.ordini WHERE programma_fornitura_id=(SELECT id FROM tpo.programmi_fornitura "
            "WHERE public_id=%s) AND stato='APERTO'", (pf,)).scalar_one()
    assert [(r[0], int(r[1]), r[2], r[3]) for r in rows] == [(1, 1, "OGNI_X_GIORNI", 14)]
    assert len(audit) == 1 and audit[0][0] == "UPDATE"
    assert audit[0][1]["data_inizio"] == "2026-09-01" and audit[0][2]["data_inizio"] == "2026-10-26"
    assert audit[0][2]["prossime_consegne"][:2] == ["2026-10-26", "2026-11-09"]
    assert orders == 2                                         # gli ordini non vengono toccati
    text = "\n".join(lines)
    assert "FATTO:" in text and "--nuova-ancora 2026-09-01" in text   # correttivo pronto

    # rilancio con la stessa ancora: rifiutato (gia' quella corrente)
    again = []
    conn = _connect(engine)
    assert module.run(conn, pf, date(2026, 10, 26), "x", True, today=TODAY, out=again.append) == 2
    conn.close()
    assert "gia' quella della versione corrente" in "\n".join(again) and len(_versions(engine, pf)) == 2


def test_the_corrective_command_restores_the_previous_anchor(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960103)
    module = _module()
    conn = _connect(engine)
    assert module.run(conn, pf, date(2026, 10, 26), "sposta", True, today=TODAY, out=lambda *_: None) == 0
    assert module.run(conn, pf, date(2026, 9, 1), "Ripristino", True, today=TODAY, out=lambda *_: None) == 0
    conn.close()
    assert [(v[0], v[2], v[3]) for v in _versions(engine, pf)] == [
        (2, date(2026, 9, 1), False), (3, date(2026, 10, 26), False), (4, date(2026, 9, 1), True)]


def test_refusals_write_nothing(writer_postgresql_engine):
    engine = writer_postgresql_engine
    module = _module()
    sospeso = _programma(engine, 960104, stato="SOSPESO")
    esplicito = _programma(engine, 960105, tipo="SETTIMANALE", giorni_iso=2)
    normale = _programma(engine, 960106)
    for pf, nuova, atteso in ((sospeso, date(2026, 10, 12), "SOSPESO"),
                              (esplicito, date(2026, 10, 12), "giorni espliciti"),
                              (normale, date(2026, 12, 1), "oltre la finestra"),
                              ("PF-999999", date(2026, 10, 12), "inesistente")):
        lines = []
        conn = _connect(engine)
        assert module.run(conn, pf, nuova, "x", True, today=TODAY, out=lines.append) == 2
        conn.close()
        assert atteso in "\n".join(lines)
    assert all(len(_versions(engine, pf)) == 1 for pf in (sospeso, esplicito, normale))
