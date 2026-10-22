"""Rinomina di un cliente (22/10/2026): solo il nome cambia, con audit e comando correttivo, su PostgreSQL usa-e-getta."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg

from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-22_rinomina_cliente.py"


def _module():
    spec = importlib.util.spec_from_file_location("rinomina_cliente", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def _clienti(engine):
    with engine.begin() as c:
        for pid, nome in (("CLI-990004", "Selvaje"), ("CLI-990014", "Salvaje")):
            c.exec_driver_sql("INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by) "
                              "VALUES (%s,%s,'test',CURRENT_TIMESTAMP,'test')", (pid, nome))


def _nome(engine, pid):
    with engine.connect() as c:
        r = c.exec_driver_sql("SELECT denominazione, version FROM tpo.clienti WHERE public_id=%s", (pid,)).one()
    return r[0], int(r[1])


def test_the_duplicate_name_must_be_renamed_first_then_the_typo(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _clienti(engine)
    m, conn = _module(), _connect(engine)
    lines = []
    # il nome giusto e' gia' preso dal doppione: rifiuta, nulla scritto
    assert m.rinomina(conn, "CLI-990004", "Salvaje", "Refuso", True, out=lines.append) == 2
    assert "esiste gia' un altro cliente" in "\n".join(lines) and _nome(engine, "CLI-990004") == ("Selvaje", 0)
    # anteprima: nulla scritto
    lines.clear()
    assert m.rinomina(conn, "CLI-990014", "Salvaje (doppione archiviato)", "Doppione", False, out=lines.append) == 0
    assert "ANTEPRIMA: nulla e' stato scritto" in "\n".join(lines) and _nome(engine, "CLI-990014") == ("Salvaje", 0)
    # esecuzione in ordine: prima il doppione, poi il refuso
    assert m.rinomina(conn, "CLI-990014", "Salvaje (doppione archiviato)", "Doppione", True, out=lambda *_: None) == 0
    lines.clear()
    assert m.rinomina(conn, "CLI-990004", "Salvaje", "Refuso: il ristorante si chiama Salvaje", True, out=lines.append) == 0
    conn.close()
    assert _nome(engine, "CLI-990004") == ("Salvaje", 1)
    assert _nome(engine, "CLI-990014") == ("Salvaje (doppione archiviato)", 1)
    assert "--ripristina" in "\n".join(lines)
    with engine.connect() as c:
        audit = c.exec_driver_sql(
            "SELECT before_data->>'denominazione', after_data->>'denominazione', reason FROM tpo.audit_eventi "
            "WHERE entity_type='CLIENTE' AND entity_public_id='CLI-990004'").all()
    assert audit == [("Selvaje", "Salvaje", "Cliente rinominato (dichiarato da Matteo): Refuso: il ristorante si chiama Salvaje")]


def test_refusals_write_nothing(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _clienti(engine)
    m, conn = _module(), _connect(engine)
    for cliente, nome, motivo in (("CLI-990004", "Selvaje", "x"), ("CLI-990004", "   ", "x"), ("CLI-990004", "Nuovo", "  "),
                                  ("CLI-999999", "Nuovo", "x"), ("CLI-990004", "salvaje", "x")):
        lines = []
        assert m.rinomina(conn, cliente, nome, motivo, True, out=lines.append) == 2
        assert "RIFIUTATO, nulla scritto" in "\n".join(lines)
    conn.close()
    assert _nome(engine, "CLI-990004") == ("Selvaje", 0) and _nome(engine, "CLI-990014") == ("Salvaje", 0)


def test_explicit_flag_allows_a_duplicate_name(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _clienti(engine)
    m, conn = _module(), _connect(engine)
    assert m.rinomina(conn, "CLI-990004", "Salvaje", "x", True, anche_se_duplicato=True, out=lambda *_: None) == 0
    conn.close()
    assert _nome(engine, "CLI-990004") == ("Salvaje", 1)


def test_restore_puts_back_the_previous_name_only_if_unchanged(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _clienti(engine)
    m, conn = _module(), _connect(engine)
    assert m.rinomina(conn, "CLI-990004", "Salvaje Ristorante", "x", True, out=lambda *_: None) == 0
    assert m.ripristina(conn, "CLI-990004", False, out=lambda *_: None) == 0 and _nome(engine, "CLI-990004") == ("Salvaje Ristorante", 1)
    assert m.ripristina(conn, "CLI-990004", True, out=lambda *_: None) == 0
    assert _nome(engine, "CLI-990004") == ("Selvaje", 2)
    lines = []
    assert m.ripristina(conn, "CLI-990004", True, out=lines.append) == 2           # niente piu' da ripristinare
    conn.close()
    assert "non e' quello lasciato" in "\n".join(lines)
