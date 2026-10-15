"""Controllo programmi / ordini (15/10/2026), su PostgreSQL usa-e-getta. Sola lettura."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)
from tests.infrastructure.postgresql.test_sposta_giorno_programma_script import _connect, _programma

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-15_controllo_programmi.py"
ADESSO = datetime(2026, 10, 12, 10, 0, tzinfo=ZoneInfo("Atlantic/Canary"))


def _module():
    spec = importlib.util.spec_from_file_location("controllo_programmi", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _righe(engine, number, quantita=1):
    """Una riga d'ordine (la varieta' del programma) su entrambi gli ordini seminati da _programma."""
    with engine.begin() as connection:
        var = connection.exec_driver_sql(f"SELECT id FROM tpo.varieta WHERE public_id='VAR-{number:06d}'").scalar_one()
        for n in (number + 100, number + 200):
            order = connection.exec_driver_sql(f"SELECT id FROM tpo.ordini WHERE public_id='ORD-{n:06d}'").scalar_one()
            connection.exec_driver_sql(
                "INSERT INTO tpo.righe_ordine(public_id,ordine_id,posizione,varieta_id,quantita,unita_misura) "
                "VALUES (%s,%s,1,%s,%s,'SET')", (f"RO-{n:06d}", order, var, quantita))


def _nome(engine, number):
    with engine.connect() as connection:
        return connection.exec_driver_sql(
            f"SELECT denominazione FROM tpo.varieta WHERE public_id='VAR-{number:06d}'").scalar_one()


def _esegui(engine, pf):
    module, lines = _module(), []
    conn = _connect(engine)
    assert module.run(conn, pf, adesso=ADESSO, out=lines.append) == 0
    conn.close()
    return "\n".join(lines)


def test_attese_follows_the_scheduler_rules():
    module = _module()
    riga = (1, "Cilantro", Decimal("1.5"), "SET", "OGNI_X_GIORNI", 14, set())
    sett = (2, "Afila", Decimal(1), "SET", "GIORNI_SETTIMANA", None, {2})
    previste = module.attese([riga, sett], date(2026, 9, 1), None, date(2026, 10, 12), date(2026, 10, 26))
    assert sorted(previste) == [date(2026, 10, 13), date(2026, 10, 20)]            # 27/10 e' fuori finestra
    assert {v[0] for v in previste[date(2026, 10, 13)].values()} == {"Cilantro", "Afila"}
    assert {v[0] for v in previste[date(2026, 10, 20)].values()} == {"Afila"}
    # ancora 20/10 e fine 25/10: solo il 20/10 (il 3/11 sarebbe oltre la fine)
    assert sorted(module.attese([riga], date(2026, 10, 20), date(2026, 10, 25), date(2026, 10, 12), date(2026, 11, 10))) \
        == [date(2026, 10, 20)]


def test_missing_lines_and_unexpected_order(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960701)
    nome = _nome(engine, 960701)
    text = _esegui(engine, pf)
    assert "ORD-960801" in text and f"manca {nome} 1 SET" in text                       # 13/10 senza righe
    assert "NON PREVISTO  ORD-960901" in text and "modifica_ordine.py annulla ORD-960901" in text   # 26/10
    assert "SOLA LETTURA" in text and "1 programmi controllati" in text


def test_quantity_difference_gives_the_ready_command(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960702)
    nome = _nome(engine, 960702)
    _righe(engine, 960702, quantita=1)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE tpo.righe_programma_fornitura SET quantita=1.5 WHERE programma_versione_id IN "
            "(SELECT pv.id FROM tpo.programmi_fornitura_versioni pv JOIN tpo.programmi_fornitura p "
            " ON p.id=pv.programma_fornitura_id WHERE p.public_id=%s)", (pf,))
    text = _esegui(engine, pf)
    assert f"QUANTITA' ORD-960802" in text and f"{nome} 1 -> programma 1.5" in text
    assert f"modifica_ordine.py quantita ORD-960802 {nome} 1.5" in text


def test_clean_program_is_reported_coherent(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960703)
    _righe(engine, 960703, quantita=1)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE tpo.ordini SET stato='ANNULLATO' WHERE public_id='ORD-960903'")
    text = _esegui(engine, pf)
    assert "COERENTI (1)" in text and pf in text
    assert "nessuna differenza" in text and "MANCA" not in text and "NON PREVISTO" not in text


def test_missing_order_and_double_order(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960704)
    _righe(engine, 960704, quantita=1)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE tpo.ordini SET stato='ANNULLATO' WHERE public_id='ORD-960904'")
        client, run_id, program = connection.exec_driver_sql(
            "SELECT cliente_id, run_id, programma_fornitura_id FROM tpo.ordini WHERE public_id='ORD-960804'").one()
        connection.exec_driver_sql(
            "INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,"
            "run_id,programma_fornitura_id,chiave_idempotenza,created_by) "
            "VALUES ('ORD-960999',%s,'2026-10-02','2026-10-13','APERTO','AUTOMATICO',%s,%s,'chiave-doppia','test')",
            (client, run_id, program))
    text = _esegui(engine, pf)
    assert "DOPPIO    martedi' 2026-10-13: 2 ordini" in text and "ORD-960804" in text and "ORD-960999" in text
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE tpo.ordini SET stato='ANNULLATO' WHERE public_id IN ('ORD-960804','ORD-960999')")
    assert "MANCA     martedi' 2026-10-13" in _esegui(engine, pf)


def test_weekday_program_expects_every_matching_day_in_the_window(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960705, tipo="GIORNI_SETTIMANA", giorni_iso=2)             # ogni martedi'
    _righe(engine, 960705, quantita=1)
    text = _esegui(engine, pf)
    assert "MANCA     martedi' 2026-10-20" in text                                       # nessun ordine il 20/10
    assert "NON PREVISTO  ORD-960905" in text                                            # il 26/10 e' lunedi'
    assert "QUANTITA'" not in text and "RIGHE" not in text                               # il 13/10 e' a posto


def test_suspended_program_lists_the_ghost_orders(writer_postgresql_engine):
    engine = writer_postgresql_engine
    pf = _programma(engine, 960706, stato="SOSPESO")
    text = _esegui(engine, pf)
    assert "programma SOSPESO, ma ci sono ordini aperti" in text
    assert "FANTASMA  ORD-960806" in text and "FANTASMA  ORD-960906" in text
    assert "modifica_ordine.py annulla ORD-960806" in text


def test_unknown_program_is_refused(writer_postgresql_engine):
    module, lines = _module(), []
    conn = _connect(writer_postgresql_engine)
    assert module.run(conn, "PF-999999", adesso=ADESSO, out=lines.append) == 2
    conn.close()
    assert "inesistente" in "\n".join(lines)
