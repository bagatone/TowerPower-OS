"""Listino uniforme (23/10/2026): stesso prezzo a SET per tutte le varieta' ATTIVE, con anteprima, audit e correttivo."""
from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import psycopg

from src.tpo_core.application.listino_varieta.models import ImpostaPrezzoListinoVarieta, ListinoVarietaAuthority
from src.tpo_core.domain.identifiers import ActorId, VarietaId
from src.tpo_core.infrastructure.postgresql.fatturazione_configuration import PostgreSQLListinoVarietaWriter
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    _Factory, migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-23_listino_uniforme.py"


def _module():
    spec = importlib.util.spec_from_file_location("listino_uniforme", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def _varieta(engine, numero, nome, stato="ATTIVA"):
    with engine.begin() as c:
        c.exec_driver_sql(
            "INSERT INTO tpo.varieta(public_id,denominazione,stato,created_by,updated_at,updated_by) "
            "VALUES (%s,%s,%s,'test',CURRENT_TIMESTAMP,'test')", (f"VAR-{numero:06d}", nome, stato))


def _prezzi(engine):
    with engine.connect() as c:
        return dict(c.exec_driver_sql(
            "SELECT v.public_id, l.prezzo_unitario::text || '/' || l.aliquota_igic::text "
            "FROM tpo.varieta v JOIN tpo.listino_varieta l ON l.varieta_id=v.id "
            "WHERE v.public_id LIKE 'VAR-98%%'").all())


def _runner(engine):
    """Esegue gli argv di `tpo listino-varieta set` con il writer vero, sul database usa-e-getta."""
    writer = PostgreSQLListinoVarietaWriter(_Factory(engine))
    chiamate = []

    def esegui(argv):
        chiamate.append(argv)
        v = {argv[i]: argv[i + 1] for i in range(2, len(argv), 2)}
        writer.imposta_prezzo(ImpostaPrezzoListinoVarieta(
            VarietaId(v["--varieta"]), Decimal(v["--prezzo-unitario"]), Decimal(v["--aliquota-igic"]),
            ListinoVarietaAuthority(ActorId(v["--actor"]), v["--reason"], v["--correlation-id"])))
        return 0, "ok"
    return esegui, chiamate


def test_preview_writes_nothing_then_execute_sets_all_active_and_skips_dismessa(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _varieta(engine, 980001, "Afila")
    _varieta(engine, 980002, "Cilantro")
    _varieta(engine, 980003, "Utrillo", stato="DISMESSA")
    m, conn = _module(), _connect(engine)
    esegui, chiamate = _runner(engine)
    righe = []
    assert m.run(conn, Decimal("12.50"), Decimal("0"), False, esegui_tpo=esegui, out=righe.append) == 0
    testo = "\n".join(righe)
    assert "ANTEPRIMA: nulla e' stato scritto" in testo and "VAR-980003 | Utrillo | DISMESSA: saltata" in testo
    assert chiamate == [] and _prezzi(engine) == {}
    righe.clear()
    assert m.run(conn, Decimal("12.50"), Decimal("0"), True, esegui_tpo=esegui, out=righe.append) == 0
    assert _prezzi(engine) == {"VAR-980001": "12.5000/0.00", "VAR-980002": "12.5000/0.00"}
    assert len(chiamate) == 2 and "nessuna varieta' aveva un prezzo prima" in "\n".join(righe)
    # rilancio: gia' a questi valori, nulla da scrivere
    righe.clear()
    assert m.run(conn, Decimal("12.50"), Decimal("0"), True, esegui_tpo=esegui, out=righe.append) == 0
    assert len(chiamate) == 2 and "Nulla da scrivere" in "\n".join(righe)
    conn.close()


def test_changed_price_prints_the_restoring_command_and_audit_has_before_after(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _varieta(engine, 980001, "Afila")
    m, conn = _module(), _connect(engine)
    esegui, chiamate = _runner(engine)
    assert m.run(conn, Decimal("10"), Decimal("7"), True, esegui_tpo=esegui, out=lambda *_: None) == 0
    righe = []
    assert m.run(conn, Decimal("12.50"), Decimal("0"), True, esegui_tpo=esegui, out=righe.append) == 0
    conn.close()
    testo = "\n".join(righe)
    assert "era 10,00 EUR IGIC 7.00% -> cambia" in testo
    assert "--prezzo-unitario 10.0000" in testo and "--aliquota-igic 7.00" in testo      # il correttivo rimette 10 / 7
    assert _prezzi(engine) == {"VAR-980001": "12.5000/0.00"}
    with engine.connect() as c:
        audit = c.exec_driver_sql(
            "SELECT before_data->>'prezzo_unitario', after_data->>'prezzo_unitario' FROM tpo.audit_eventi "
            "WHERE entity_type='LISTINO_VARIETA' AND entity_public_id='VAR-980001' ORDER BY id").all()
    assert audit == [(None, "10.0000"), ("10.0000", "12.5000")]


def test_invalid_values_and_failures_are_reported(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _varieta(engine, 980001, "Afila")
    m, conn = _module(), _connect(engine)
    righe = []
    assert m.run(conn, Decimal("-1"), Decimal("0"), True, esegui_tpo=lambda a: (0, ""), out=righe.append) == 2
    assert m.run(conn, Decimal("12.50"), Decimal("101"), True, esegui_tpo=lambda a: (0, ""), out=righe.append) == 2
    assert m.run(conn, Decimal("12.50"), Decimal("0"), True, esegui_tpo=lambda a: (3, "boom"), out=righe.append) == 1
    conn.close()
    assert "fallita (exit 3): boom" in "\n".join(righe) and _prezzi(engine) == {}
