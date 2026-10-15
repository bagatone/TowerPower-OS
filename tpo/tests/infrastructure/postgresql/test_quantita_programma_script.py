"""Cambio quantita' di una riga di programma di fornitura (14/10/2026, Splash Cilantro 1 -> 1,5), su PostgreSQL usa-e-getta."""
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

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-14_quantita_programma.py"
TODAY = date(2026, 10, 14)


def _module():
    spec = importlib.util.spec_from_file_location("quantita_programma", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _variety_name(engine, number):
    with engine.connect() as connection:
        return connection.exec_driver_sql(
            f"SELECT denominazione FROM tpo.varieta WHERE public_id='VAR-{number:06d}'").scalar_one()


def _riga_ordine(engine, number):
    """Un ordine aperto del programma ha una riga con la varieta' del programma (quantita' 1)."""
    with engine.begin() as connection:
        var = connection.exec_driver_sql(f"SELECT id FROM tpo.varieta WHERE public_id='VAR-{number:06d}'").scalar_one()
        for n in (number + 100, number + 200):
            order = connection.exec_driver_sql(f"SELECT id FROM tpo.ordini WHERE public_id='ORD-{n:06d}'").scalar_one()
            connection.exec_driver_sql(
                "INSERT INTO tpo.righe_ordine(public_id,ordine_id,posizione,varieta_id,quantita,unita_misura) "
                "VALUES (%s,%s,1,%s,1,'SET')", (f"RO-{n:06d}", order, var))


def test_preview_lists_the_orders_to_fix_and_writes_nothing(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960401)
    _riga_ordine(engine, 960401)
    nome = _variety_name(engine, 960401)
    module, lines = _module(), []
    conn = _connect(engine)
    assert module.run(conn, pf, nome, Decimal("1.5"), "Splash 1,5", False, today=date(2026, 10, 14),
                      out=lines.append) == 0
    conn.close()
    text = "\n".join(lines)
    assert f"{nome}: 1 -> 1.5 SET" in text
    # l'ordine del 13/10 e' prima di oggi: non toccato; quello del 26/10 va corretto
    assert "ORD-960501" not in text
    assert "ORD-960601" in text and "da portare a 1.5" in text
    assert "modifica_ordine.py quantita ORD-960601" in text
    assert "ANTEPRIMA: nulla e' stato scritto" in text
    assert [v[0] for v in _versions(engine, pf)] == [2]


def test_execute_opens_new_version_with_only_that_quantity_changed(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960402)
    nome = _variety_name(engine, 960402)
    module, lines = _module(), []
    conn = _connect(engine)
    assert module.run(conn, pf, nome, Decimal("1.5"), "Splash 1,5", True, today=TODAY, out=lines.append) == 0
    conn.close()
    assert [(v[0], v[1], v[2], v[3]) for v in _versions(engine, pf)] == [
        (2, "ATTIVO", date(2026, 9, 1), False), (3, "ATTIVO", date(2026, 9, 1), True)]
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("""
          SELECT pv.numero_versione, r.quantita, r.tipo_ricorrenza::text, r.intervallo_giorni
          FROM tpo.righe_programma_fornitura r JOIN tpo.programmi_fornitura_versioni pv ON pv.id=r.programma_versione_id
          JOIN tpo.programmi_fornitura p ON p.id=pv.programma_fornitura_id WHERE p.public_id=%s
          ORDER BY pv.numero_versione""", (pf,)).all()
        audit = connection.exec_driver_sql(
            "SELECT before_data, after_data FROM tpo.audit_eventi WHERE entity_public_id=%s", (pf,)).all()
    assert [(r[0], Decimal(r[1]), r[2], r[3]) for r in rows] == [
        (2, Decimal(1), "OGNI_X_GIORNI", 14), (3, Decimal("1.5"), "OGNI_X_GIORNI", 14)]
    assert len(audit) == 1 and audit[0][0]["quantita"] == "1" and audit[0][1]["quantita"] == "1.5"
    text = "\n".join(lines)
    assert "FATTO:" in text and f"{pf} {nome} 1 " in text          # correttivo pronto


def test_refuses_same_quantity_unknown_variety_and_non_positive(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960403)
    nome = _variety_name(engine, 960403)
    module = _module()
    for var, q in ((nome, Decimal(1)), ("Inesistente", Decimal(2)), (nome, Decimal(0))):
        lines = []
        conn = _connect(engine)
        assert module.run(conn, pf, var, q, "x", True, today=TODAY, out=lines.append) == 2
        conn.close()
        assert "RIFIUTATO, nulla scritto" in "\n".join(lines)
    assert len(_versions(engine, pf)) == 1


def test_corrective_command_restores_the_previous_quantity(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960404)
    nome = _variety_name(engine, 960404)
    module = _module()
    conn = _connect(engine)
    assert module.run(conn, pf, nome, Decimal("1.5"), "su", True, today=TODAY, out=lambda *_: None) == 0
    assert module.run(conn, pf, nome, Decimal(1), "Ripristino", True, today=TODAY, out=lambda *_: None) == 0
    conn.close()
    with engine.connect() as connection:
        q = connection.exec_driver_sql("""
          SELECT r.quantita FROM tpo.righe_programma_fornitura r
          JOIN tpo.programmi_fornitura_versioni pv ON pv.id=r.programma_versione_id AND pv.valida_al IS NULL
          JOIN tpo.programmi_fornitura p ON p.id=pv.programma_fornitura_id WHERE p.public_id=%s""", (pf,)).scalar_one()
    assert Decimal(q) == 1 and len(_versions(engine, pf)) == 3


def test_weekday_program_keeps_its_days_and_shows_next_deliveries(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960405, tipo="GIORNI_SETTIMANA", giorni_iso=2)      # martedi'
    nome = _variety_name(engine, 960405)
    module, lines = _module(), []
    conn = _connect(engine)
    assert module.run(conn, pf, nome, Decimal("1.5"), "Splash", False, today=TODAY, out=lines.append) == 0
    assert "martedi' 2026-10-20" in "\n".join(l for l in lines if l.startswith("PROSSIME"))
    assert module.run(conn, pf, nome, Decimal("1.5"), "Splash", True, today=TODAY, out=lambda *_: None) == 0
    conn.close()
    with engine.connect() as connection:
        rows = connection.exec_driver_sql("""
          SELECT pv.numero_versione, r.quantita, g.giorno_iso
          FROM tpo.righe_programma_fornitura r JOIN tpo.programmi_fornitura_versioni pv ON pv.id=r.programma_versione_id
          JOIN tpo.programmi_fornitura p ON p.id=pv.programma_fornitura_id
          LEFT JOIN tpo.righe_programma_giorni g ON g.riga_programma_id=r.id WHERE p.public_id=%s
          ORDER BY pv.numero_versione""", (pf,)).all()
    assert [(r[0], Decimal(r[1]), r[2]) for r in rows] == [(2, Decimal(1), 2), (3, Decimal("1.5"), 2)]
