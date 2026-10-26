"""Registrazione semi Golinucci 25/10/2026: anteprima senza scritture, ordine dei comandi, salti e STOP."""
from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import psycopg

from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    _Factory, migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-26_registra_semi_golinucci.py"


def _module():
    spec = importlib.util.spec_from_file_location("registra_semi_golinucci", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username)


def _varieta(engine, numero, nome, sigla=None):
    with engine.begin() as c:
        c.exec_driver_sql(
            "INSERT INTO tpo.varieta(public_id,denominazione,stato,codice_tracciabilita,created_by,updated_at,updated_by) "
            "VALUES (%s,%s,'ATTIVA',%s,'test',CURRENT_TIMESTAMP,'test')", (f"VAR-{numero:06d}", nome, sigla))


def _semente(engine, referenza, lotto=None):
    with engine.begin() as c:
        seed = c.exec_driver_sql(
            "INSERT INTO tpo.sementi(fornitore,referenza_commerciale,marca,certificazioni,created_by,updated_at,updated_by) "
            "VALUES ('Golinucci Organic',%s,'Golinucci','IT-BIO-007','test',CURRENT_TIMESTAMP,'test') RETURNING id",
            (referenza,)).scalar_one()
        if lotto:
            c.exec_driver_sql(
                "INSERT INTO tpo.lotti_seme(public_id,semente_id,numero_lotto_produttore,data_ricezione,quantita_iniziale,"
                "quantita_residua,unita_misura,created_by,updated_at,updated_by) "
                "VALUES ('LSE-99' || lpad((SELECT count(*)+1 FROM tpo.lotti_seme)::text,4,'0'),%s,%s,DATE '2026-09-01',500,0,'GRAM','test',CURRENT_TIMESTAMP,'test')", (seed, lotto))


def _sacchi():
    return [
        {"varieta": "Afila", "sigla": None, "referenza": None, "cerca": ("affila", "afila"), "lotto": "GOL 0708/BM2643",
         "grammi": Decimal("5000"), "formato": "5 kg", "etichetta": "Pea Green Affila"},
        {"varieta": "Melissa", "sigla": "MEL", "referenza": "Lemon Balm", "lotto": "GOL 0013/BA2412",
         "grammi": Decimal("100"), "formato": "100 g"},
        {"varieta": "Perilla", "sigla": "SHI", "referenza": "Perilla Bicolor", "lotto": "GOL 0020/BA7340",
         "grammi": Decimal("50"), "formato": "50 g"},
    ]


def _arg(argv, nome):
    return argv[argv.index(nome) + 1]


def _runner():
    chiamate = []

    def esegui(argv):
        chiamate.append(argv)
        return 0, "STATUS: INSERTED"
    return esegui, chiamate


def _conta(engine):
    with engine.connect() as c:
        return c.exec_driver_sql("SELECT (SELECT count(*) FROM tpo.varieta), (SELECT count(*) FROM tpo.sementi), "
                                 "(SELECT count(*) FROM tpo.lotti_seme)").one()


def test_preview_writes_nothing_then_execute_runs_variety_semente_lotto_in_order(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _varieta(engine, 990001, "Afila", "AFZ")
    _semente(engine, "Pea Green Affila")
    prima = _conta(engine)
    m = _module()
    m.SACCHI = _sacchi()
    conn = _connect(engine)
    esegui, chiamate = _runner()
    righe = []
    assert m.run(conn, False, esegui, righe.append) == 0
    testo = "\n".join(righe)
    assert "ANTEPRIMA" in testo and chiamate == [] and _conta(engine) == prima
    assert "VARIETA nuova" in testo and "MEL" in testo and "SHI" in testo and "esistente: Golinucci Organic / Pea Green Affila" in testo
    righe.clear()
    assert m.run(conn, True, esegui, righe.append) == 0
    tipi = [(a[0], a[1]) for a in chiamate]
    assert tipi == [("seed-lot", "commission"), ("onboarding", "variety"), ("semente", "commission"),
                    ("seed-lot", "commission"), ("onboarding", "variety"), ("semente", "commission"),
                    ("seed-lot", "commission")]
    afila_lotto = chiamate[0]
    assert _arg(afila_lotto, "--manufacturer-lot-number") == "GOL 0708/BM2643"
    assert _arg(afila_lotto, "--seed-commercial-reference") == "Pea Green Affila"
    assert _arg(afila_lotto, "--received-date") == "2026-10-25" and _arg(afila_lotto, "--expiry-date") == "2027-10-31"
    assert _arg(afila_lotto, "--initial-quantity") == "5000"
    prov = json.loads(_arg(afila_lotto, "--provenance"))
    assert prov["anomaly"] == "UNKNOWN" and prov["received_date"] == "OWNER_AUTHORIZED" and len(prov) == 8
    var = chiamate[1]
    assert _arg(var, "--variety-id") == "VAR-990002" and _arg(var, "--traceability-code") == "MEL"
    assert _arg(chiamate[4], "--variety-id") == "VAR-990003" and _arg(chiamate[4], "--traceability-code") == "SHI"
    sem = chiamate[2]
    assert _arg(sem, "--referenza-commerciale") == "Lemon Balm" and _arg(sem, "--marca") == "Golinucci"
    assert _arg(sem, "--certificazioni") == "IT-BIO-007"
    # le idempotency key sono stabili: stesso comando -> stessa chiave
    assert _arg(chiamate[3], "--idempotency-key").startswith("SEMI-GOLINUCCI-2026-10-25-lotto-")


def test_sigla_gia_usata_ferma_tutto_senza_scrivere(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _varieta(engine, 990001, "Afila", "AFZ")
    _varieta(engine, 990002, "Altra", "MEL")
    _semente(engine, "Pea Green Affila")
    m = _module()
    m.SACCHI = _sacchi()
    esegui, chiamate = _runner()
    righe = []
    assert m.run(_connect(engine), True, esegui, righe.append) == 2
    assert chiamate == [] and "la sigla MEL e' gia' di Altra" in "\n".join(righe)


def test_lotto_gia_registrato_viene_saltato(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _varieta(engine, 990001, "Afila", "AFZ")
    _varieta(engine, 990002, "Melissa", "MEL")
    _semente(engine, "Pea Green Affila", lotto="GOL 0708/BM2643")
    _semente(engine, "Lemon Balm", lotto="GOL 0013/BA2412")
    m = _module()
    m.SACCHI = _sacchi()[:2]
    esegui, chiamate = _runner()
    righe = []
    assert m.run(_connect(engine), True, esegui, righe.append) == 0
    assert chiamate == [] and "salto" in "\n".join(righe) and "Da scrivere: 0 operazioni" in "\n".join(righe)


def test_semente_afila_ambigua_ferma(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _varieta(engine, 990001, "Afila", "AFZ")
    _semente(engine, "Pea Green Affila")
    _semente(engine, "Pea Green Afila bis")
    m = _module()
    m.SACCHI = _sacchi()[:1]
    esegui, chiamate = _runner()
    righe = []
    assert m.run(_connect(engine), True, esegui, righe.append) == 2
    assert chiamate == [] and "trovate 2 sementi Golinucci" in "\n".join(righe)
