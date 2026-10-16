"""Piano a sessioni di semina (16/10/2026): lettura reale dal piano committato, su PostgreSQL usa-e-getta.
Riusa il Commit Writer di Production Planning (le righe del piano hanno troppi CHECK per scriverle a mano)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import psycopg

from src.tpo_core.diario_web import sessioni_semina as ss
from tests.infrastructure.postgresql.test_production_planning_commit_writer import (
    _commit,
    writer_cluster,  # noqa: F401 -- fixture dependency required by writer_database
    writer_database,
)
from tests.infrastructure.postgresql.test_production_planning_migrations import (
    isolated_postgresql as migration_postgresql,  # noqa: F401 -- fixture dependency of writer_cluster
)


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username, autocommit=True)


def test_reads_the_committed_plan_line_and_assigns_it_to_a_session(writer_database):
    _commit(writer_database)                       # una riga: semina 04/08/2026 (martedi'), consegna 15/08, 1 SET, 25 g
    conn = _connect(writer_database)
    righe = ss.leggi_righe(conn.cursor())
    conn.close()
    assert len(righe) == 1
    r = righe[0]
    assert (r.varieta, r.cliente, r.stato, r.quantita, r.unita, r.grammi) == (
        "Writer test variety", "Writer test client", "PIANIFICATA", Decimal(1), "SET", Decimal(25))
    assert (r.data_ideale, r.consegna) == (date(2026, 8, 4), date(2026, 8, 15))
    p = ss.assegna(righe, date(2026, 8, 3))        # oggi lunedi' 3/8: la sessione prima del mar 4/8 e' dom 2/8, gia' passata
    sessione = p.sessioni[0]
    assert sessione.data == date(2026, 8, 5)       # prossima sessione utile: mercoledi' 5/8, un giorno dopo la data ideale
    d = sessione.varieta[0].destinatari[0]
    assert d.ritardo_giorni == 1 and "in ritardo di 1 gg" in d.note[0]
    testo = "\n".join(ss.testo(p))
    assert "Writer test variety  1 SET   (25 g di seme)" in testo and "Writer test client" in testo


def test_empty_database_gives_an_empty_plan(writer_database):
    conn = _connect(writer_database)
    assert ss.leggi_righe(conn.cursor()) == []
    conn.close()
