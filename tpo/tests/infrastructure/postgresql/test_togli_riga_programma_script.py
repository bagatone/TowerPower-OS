"""Togliere una riga da un programma di fornitura (20/10/2026, Bahia Real senza Rabano), su PostgreSQL usa-e-getta."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)
from tests.infrastructure.postgresql.test_sposta_giorno_programma_script import _connect, _programma, _versions

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-20_togli_riga_programma.py"
TODAY = date(2026, 10, 20)


def _module():
    spec = importlib.util.spec_from_file_location("togli_riga_programma", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _con_seconda_riga(engine, number, *, giorni_iso=None):
    """Aggiunge al programma una seconda varieta' (posizione 2) e righe d'ordine in entrambi gli ordini."""
    with engine.begin() as connection:
        var1 = connection.exec_driver_sql(f"SELECT id FROM tpo.varieta WHERE public_id='VAR-{number:06d}'").scalar_one()
        var2 = connection.exec_driver_sql(
            "INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,updated_at,updated_by) "
            "VALUES (%s,%s,'ATTIVA','test',now(),'test') RETURNING id",
            (f"VAR-{number + 5000:06d}", f"Seconda {number}")).scalar_one()
        version = connection.exec_driver_sql(
            "SELECT pv.id FROM tpo.programmi_fornitura_versioni pv JOIN tpo.programmi_fornitura p "
            "ON p.id=pv.programma_fornitura_id WHERE p.public_id=%s AND pv.valida_al IS NULL",
            (f"PF-{number:06d}",)).scalar_one()
        tipo, iv = ("GIORNI_SETTIMANA", None) if giorni_iso else ("OGNI_X_GIORNI", 14)
        riga = connection.exec_driver_sql(
            "INSERT INTO tpo.righe_programma_fornitura(programma_versione_id,posizione,varieta_id,quantita,unita_misura,"
            "tipo_ricorrenza,intervallo_giorni) VALUES (%s,2,%s,0.5,'SET',%s,%s) RETURNING id",
            (version, var2, tipo, iv)).scalar_one()
        if giorni_iso:
            connection.exec_driver_sql("INSERT INTO tpo.righe_programma_giorni(riga_programma_id,giorno_iso) VALUES (%s,%s)",
                                       (riga, giorni_iso))
        for n in (number + 100, number + 200):
            order = connection.exec_driver_sql(f"SELECT id FROM tpo.ordini WHERE public_id='ORD-{n:06d}'").scalar_one()
            for pos, var in ((1, var1), (2, var2)):
                connection.exec_driver_sql(
                    "INSERT INTO tpo.righe_ordine(public_id,ordine_id,posizione,varieta_id,quantita,unita_misura) "
                    "VALUES (%s,%s,%s,%s,1,'SET')", (f"RO-{n * 10 + pos:07d}", order, pos, var))
    return f"Seconda {number}"


def test_preview_lists_only_future_orders_with_ready_commands_and_writes_nothing(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960701)
    nome = _con_seconda_riga(engine, 960701)
    module, lines = _module(), []
    conn = _connect(engine)
    assert module.run(conn, pf, nome, "segnaposto sbagliato", False, today=TODAY, out=lines.append) == 0
    conn.close()
    text = "\n".join(lines)
    assert "<-- TOLTA" in text and "ANTEPRIMA: nulla e' stato scritto" in text
    assert "ORD-960801" not in text                                  # consegna 13/10: nel passato, non toccato
    assert "ORD-960901" in text and "2026-10-26" in text
    assert f"2026-10-16_stralcia_riga.py ORD-960901 {nome}" in text
    assert [v[0] for v in _versions(engine, pf)] == [2]


def test_execute_opens_new_version_without_the_row_and_keeps_the_others_untouched(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960702)
    nome = _con_seconda_riga(engine, 960702)
    module, lines = _module(), []
    conn = _connect(engine)
    assert module.run(conn, pf, nome, "segnaposto sbagliato", True, today=TODAY, out=lines.append) == 0
    conn.close()
    assert [(v[0], v[3]) for v in _versions(engine, pf)] == [(2, False), (3, True)]
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("""
          SELECT pv.numero_versione, r.posizione, v.denominazione, r.quantita
          FROM tpo.righe_programma_fornitura r JOIN tpo.programmi_fornitura_versioni pv ON pv.id=r.programma_versione_id
          JOIN tpo.programmi_fornitura p ON p.id=pv.programma_fornitura_id JOIN tpo.varieta v ON v.id=r.varieta_id
          WHERE p.public_id=%s ORDER BY pv.numero_versione, r.posizione""", (pf,)).all()
        audit = connection.exec_driver_sql(
            "SELECT before_data, after_data, reason FROM tpo.audit_eventi WHERE entity_public_id=%s", (pf,)).all()
        ordini = connection.exec_driver_sql(
            "SELECT stato::text, (SELECT count(*) FROM tpo.righe_ordine r WHERE r.ordine_id=o.id) "
            "FROM tpo.ordini o WHERE public_id='ORD-960902'").one()
    assert [(r[0], r[1], r[3] if r[1] == 1 else r[2]) for r in rows if r[0] == 3] == [(3, 1, Decimal(1))]
    assert len([r for r in rows if r[0] == 2]) == 2                 # la v2 conserva entrambe le righe
    assert len(audit) == 1 and audit[0][0]["riga_tolta"]["varieta"] == nome and audit[0][1]["righe"] == 1
    assert nome in audit[0][2]
    assert ordini == ("APERTO", 2)                                  # gli ordini esistenti NON vengono toccati


def test_refuses_unknown_variety_last_row_and_non_active_program(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960703)
    nome = _con_seconda_riga(engine, 960703)
    module = _module()
    conn = _connect(engine)
    lines = []
    assert module.run(conn, pf, "Inesistente", "x", True, today=TODAY, out=lines.append) == 2
    assert "RIFIUTATO, nulla scritto" in "\n".join(lines) and len(_versions(engine, pf)) == 1
    assert module.run(conn, pf, nome, "ok", True, today=TODAY, out=lambda *_: None) == 0
    lines.clear()
    prima = _variety_first(engine, 960703)
    assert module.run(conn, pf, prima, "ultima", True, today=TODAY, out=lines.append) == 2
    assert "una sola riga" in "\n".join(lines)
    conn.close()
    assert len(_versions(engine, pf)) == 2

    pf2 = _programma(engine, 960704, stato="SOSPESO")
    _con_seconda_riga(engine, 960704)
    conn = _connect(engine)
    lines = []
    assert module.run(conn, pf2, "Seconda 960704", "x", True, today=TODAY, out=lines.append) == 2
    conn.close()
    assert "SOSPESO" in "\n".join(lines) and len(_versions(engine, pf2)) == 1


def _variety_first(engine, number):
    with engine.connect() as connection:
        return connection.exec_driver_sql(
            f"SELECT denominazione FROM tpo.varieta WHERE public_id='VAR-{number:06d}'").scalar_one()


def test_weekday_program_keeps_days_of_the_remaining_rows(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960705, tipo="GIORNI_SETTIMANA", giorni_iso=2)          # martedi'
    nome = _con_seconda_riga(engine, 960705, giorni_iso=2)
    module = _module()
    conn = _connect(engine)
    assert module.run(conn, pf, nome, "Bahia: niente Rabano", True, today=TODAY, out=lambda *_: None) == 0
    conn.close()
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("""
          SELECT pv.numero_versione, r.posizione, g.giorno_iso
          FROM tpo.righe_programma_fornitura r JOIN tpo.programmi_fornitura_versioni pv ON pv.id=r.programma_versione_id
          JOIN tpo.programmi_fornitura p ON p.id=pv.programma_fornitura_id
          LEFT JOIN tpo.righe_programma_giorni g ON g.riga_programma_id=r.id WHERE p.public_id=%s
          ORDER BY pv.numero_versione, r.posizione""", (pf,)).all()
    assert rows == [(2, 1, 2), (2, 2, 2), (3, 1, 2)]
