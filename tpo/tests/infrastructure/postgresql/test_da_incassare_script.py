"""Elenco "da incassare" (16/10/2026), su PostgreSQL usa-e-getta. Sola lettura."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    _command, _seed, _writer,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)
from tests.infrastructure.postgresql.test_sposta_giorno_programma_script import _connect

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-16_da_incassare.py"
OGGI = date(2099, 1, 11)                    # le consegne dei test sono del 2099-01-01 -> 10 giorni


def _module():
    spec = importlib.util.spec_from_file_location("da_incassare", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _consegna(engine, number, quantita="0.5", prezzo=None):
    """Cliente 'Writer client N' con la consegna CON-N da `quantita` SET; prezzo di listino facoltativo."""
    _seed(engine, number)
    _writer(engine).publish(_command(number, quantita, movement=number))
    if prezzo is not None:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO tpo.listino_varieta(varieta_id,prezzo_unitario,aliquota_igic,created_at,created_by,"
                "updated_at,updated_by) SELECT id,%s,7,now(),'t',now(),'t' FROM tpo.varieta WHERE public_id=%s",
                (prezzo, f"VAR-{number:06d}"))


def _paga(engine, number, tipo="PAGAMENTO", annulla=None):
    with engine.begin() as connection:
        con = connection.exec_driver_sql(f"SELECT id FROM tpo.consegne WHERE public_id='CON-{number:06d}'").scalar_one()
        if tipo == "PAGAMENTO":
            connection.exec_driver_sql(
                "INSERT INTO tpo.pagamenti_consegna(public_id,consegna_id,tipo,data_pagamento,metodo,idempotency_key,"
                "payload_hash,reason,correlation_id,created_by) "
                "VALUES (%s,%s,'PAGAMENTO','2099-01-05','CONTANTI',%s,'h','test','c','t')",
                (f"PGC-{number:06d}", con, f"k-pag-{number}"))
        else:
            connection.exec_driver_sql(
                "INSERT INTO tpo.pagamenti_consegna(public_id,consegna_id,tipo,annulla_pagamento_id,idempotency_key,"
                "payload_hash,reason,correlation_id,created_by) "
                "SELECT %s,%s,'ANNULLAMENTO',id,%s,'h','test','c','t' FROM tpo.pagamenti_consegna WHERE public_id=%s",
                (f"PGC-9{number:05d}", con, f"k-ann-{number}", annulla))


def _esegui(engine, **kwargs):
    module, lines = _module(), []
    conn = _connect(engine)
    code = module.run(conn, oggi=OGGI, out=lines.append, **kwargs)
    conn.close()
    return code, "\n".join(lines)


def test_unpaid_delivery_is_listed_with_listino_value_and_ready_command(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _consegna(engine, 971001, quantita="0.5", prezzo="8")
    code, text = _esegui(engine, cliente="Writer client 971001")
    assert code == 0
    assert "Writer client 971001 (CLI-971001): 1 consegna, la piu' vecchia di 10 giorni" in text
    assert "CON-971001  2099-01-01 (10 gg)  Writer variety 971001 0.5  -> 4.00 EUR" in text
    assert "--pagata CON-971001 --metodo METODO" in text and "--esegui" in text      # segnaposto + istruzione
    assert "TOTALE: 1 consegne da incassare, 1 clienti, da listino 4.00 EUR netto" in text
    assert "SOLA LETTURA" in text


def test_paid_is_excluded_and_cancelled_payment_comes_back(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _consegna(engine, 971002)
    filtro = dict(cliente="Writer client 971002")
    assert "Nessuna consegna da incassare" not in _esegui(engine, **filtro)[1]
    _paga(engine, 971002)
    assert "Nessuna consegna da incassare" in _esegui(engine, **filtro)[1]
    _paga(engine, 971002, tipo="ANNULLAMENTO", annulla="PGC-971002")
    assert "CON-971002" in _esegui(engine, **filtro)[1]


def test_missing_listino_price_is_stated_not_guessed(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _consegna(engine, 971003)                                             # nessun prezzo
    _, text = _esegui(engine, cliente="Writer client 971003")
    assert "-> valore n.d." in text
    assert "valore da listino non calcolabile" in text and "0.00 EUR" not in text
    assert "NOTA: il listino non ha il prezzo di: Writer variety 971003" in text


def test_metodo_completes_the_command_and_terms_mark_overdue(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _consegna(engine, 971004, prezzo="10")
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE tpo.clienti SET termini_pagamento_giorni=7 WHERE public_id='CLI-971004'")
    _, text = _esegui(engine, cliente="client 971004", metodo="contanti")
    assert "--pagata CON-971004 --metodo CONTANTI --esegui" in text
    assert "scad. 2099-01-08 SCADUTA" in text


def test_invalid_metodo_is_refused(writer_postgresql_engine):
    code, text = _esegui(writer_postgresql_engine, metodo="assegno")
    assert code == 2 and "metodo 'assegno' non valido" in text


def test_csv_is_written_and_no_unpaid_message(writer_postgresql_engine, tmp_path):
    engine = writer_postgresql_engine
    _consegna(engine, 971005, prezzo="8")
    csv_file = tmp_path / "da_incassare.csv"
    _, text = _esegui(engine, cliente="Writer client 971005", csv_path=str(csv_file))
    assert "CSV scritto" in text
    righe = csv_file.read_text(encoding="utf-8-sig").splitlines()
    assert righe[0].startswith("cliente;codice_cliente;consegna") and "CON-971005" in righe[1] and ";4.00;" in righe[1]
    assert "Nessuna consegna da incassare per 'Nessuno'" in _esegui(engine, cliente="Nessuno")[1]
