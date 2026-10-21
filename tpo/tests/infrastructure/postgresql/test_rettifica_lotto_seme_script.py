"""Rettifica (solo in diminuzione) del residuo di un lotto di seme (21/10/2026), su PostgreSQL usa-e-getta."""
from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import psycopg

from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-21_rettifica_lotto_seme.py"


def _module():
    spec = importlib.util.spec_from_file_location("rettifica_lotto_seme", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def _lotto(engine, public_id="LSE-990101", residuo="88"):
    with engine.begin() as c:
        seed = c.exec_driver_sql(
            "INSERT INTO tpo.sementi(fornitore,referenza_commerciale,created_by,updated_at,updated_by) "
            "VALUES ('Golinucci Organic','Cilantro','test',CURRENT_TIMESTAMP,'test') RETURNING id").scalar_one()
        c.exec_driver_sql(
            "INSERT INTO tpo.lotti_seme(public_id,semente_id,numero_lotto_produttore,data_ricezione,quantita_iniziale,"
            "quantita_residua,unita_misura,created_by,updated_at,updated_by) "
            "VALUES (%s,%s,'L-1',DATE '2026-09-01',500,%s,'GRAM','test',CURRENT_TIMESTAMP,'test')",
            (public_id, seed, residuo))
    return public_id


def _stato(engine, public_id):
    with engine.connect() as c:
        r = c.exec_driver_sql("SELECT quantita_residua, version FROM tpo.lotti_seme WHERE public_id=%s",
                              (public_id,)).one()
    return Decimal(r[0]), int(r[1])


def test_preview_writes_nothing_and_execute_zeroes_the_lot_with_audit(writer_postgresql_engine):
    engine = writer_postgresql_engine
    lotto = _lotto(engine)
    module, lines = _module(), []
    conn = _connect(engine)
    assert module.rettifica(conn, lotto, Decimal(0), "Sacco finito", False, out=lines.append) == 0
    assert "ANTEPRIMA: nulla e' stato scritto" in "\n".join(lines) and _stato(engine, lotto) == (Decimal(88), 0)
    lines.clear()
    assert module.rettifica(conn, lotto, Decimal(0), "Sacco finito", True, out=lines.append) == 0
    conn.close()
    assert _stato(engine, lotto) == (Decimal(0), 1)
    with engine.connect() as c:
        audit = c.exec_driver_sql(
            "SELECT before_data->>'quantita_residua', after_data->>'quantita_residua', after_data->>'differenza', reason "
            "FROM tpo.audit_eventi WHERE entity_public_id=%s", (lotto,)).all()
    assert audit == [("88", "0", "88", "Rettifica del residuo (dichiarata da Matteo): Sacco finito")]
    assert "--ripristina" in "\n".join(lines)


def test_refuses_increase_equal_negative_missing_reason_and_unknown_lot(writer_postgresql_engine):
    engine = writer_postgresql_engine
    lotto = _lotto(engine, "LSE-990102", "50")
    module = _module()
    conn = _connect(engine)
    for lot, q, motivo in ((lotto, Decimal(60), "x"), (lotto, Decimal(50), "x"), (lotto, Decimal(-1), "x"),
                           (lotto, Decimal(10), "  "), ("LSE-999999", Decimal(0), "x")):
        lines = []
        assert module.rettifica(conn, lot, q, motivo, True, out=lines.append) == 2
        assert "RIFIUTATO, nulla scritto" in "\n".join(lines)
    conn.close()
    assert _stato(engine, lotto) == (Decimal(50), 0)


def test_restore_puts_back_the_previous_residue_only_if_unchanged(writer_postgresql_engine):
    engine = writer_postgresql_engine
    lotto = _lotto(engine, "LSE-990103", "88")
    module = _module()
    conn = _connect(engine)
    assert module.rettifica(conn, lotto, Decimal(0), "Sacco finito", True, out=lambda *_: None) == 0
    assert module.ripristina(conn, lotto, False, out=lambda *_: None) == 0 and _stato(engine, lotto) == (Decimal(0), 1)
    assert module.ripristina(conn, lotto, True, out=lambda *_: None) == 0
    assert _stato(engine, lotto) == (Decimal(88), 2)
    lines = []
    assert module.ripristina(conn, lotto, True, out=lines.append) == 2        # non c'e' piu' nulla da ripristinare
    conn.close()
    assert "non e' quello lasciato" in "\n".join(lines)
