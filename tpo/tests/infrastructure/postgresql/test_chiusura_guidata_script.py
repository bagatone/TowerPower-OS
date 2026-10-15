"""Chiusura guidata delle semine raccolte per intero (16/10/2026), su PostgreSQL usa-e-getta. Il CLI e' un registratore."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from tests.infrastructure.postgresql.test_bolla_lettura_reader import _seed_carico_da_raccolta
from tests.infrastructure.postgresql.test_clandestino_script import _connect
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    TZ, _seed,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-16_chiusura_guidata.py"
QUANDO = datetime(2099, 2, 1, 9, 0, tzinfo=TZ)


def _module():
    spec = importlib.util.spec_from_file_location("chiusura_guidata", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _semina(engine, number, codice, *, raccolto, atteso, stato="PRONTA_ALLA_RACCOLTA"):
    _seed(engine, number, stock="0")
    _seed_carico_da_raccolta(engine, number, raccolto, codice, datetime(2098, 1, 1, 8, tzinfo=TZ))
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        finestra = ("harvest_window_start=data_avvio + interval '9 days', harvest_window_end=data_avvio + interval '14 days'"
                    if atteso is not None else "harvest_window_start=NULL, harvest_window_end=NULL")
        connection.exec_driver_sql(
            "UPDATE tpo.semine SET stato=%s, expected_useful_quantity=%s, expected_useful_uom=%s, " + finestra +
            " WHERE public_id=%s",
            (stato, atteso, None if atteso is None else "SET", f"SEM-{number:06d}"))


def _setup(engine):
    _semina(engine, 972001, "TST-1610-A", raccolto="2", atteso="2")            # chiudibile
    _semina(engine, 972002, "TST-1610-B", raccolto="4.5", atteso="4")          # chiudibile (eccedenza)
    _semina(engine, 972003, "TST-1610-C", raccolto="1", atteso="4")            # in corso
    _semina(engine, 972004, "TST-1610-D", raccolto="1", atteso="1", stato="CRESCITA")   # completa ma non PRONTA
    _semina(engine, 972005, "TST-1610-E", raccolto="0.5", atteso=None)         # resa non compilata


class Runner:
    def __init__(self, returncode=0):
        self.calls, self.returncode = [], returncode

    def __call__(self, cmd):
        self.calls.append(cmd)
        return SimpleNamespace(returncode=self.returncode, stdout="STATUS: INSERTED\n", stderr="")


def _esegui(engine, codici=None, esegui=False, runner=None, **kw):
    module, lines = _module(), []
    conn = _connect(engine)
    code = module.run(conn, codici, when=kw.pop("when", QUANDO), esegui=esegui, out=lines.append,
                      runner=runner or Runner(), **kw)
    conn.close()
    return code, "\n".join(lines)


def test_list_shows_codes_status_and_the_ready_command(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _setup(engine)
    code, text = _esegui(engine)
    assert code == 0 and "SOLA LETTURA" in text
    assert "SEM-972001 TST-1610-A" in text and "raccolti 2 su 2 SET  -> chiudibile" in text
    assert "SEM-972002 TST-1610-B" in text and "raccolti 4.5 su 4 SET  -> chiudibile" in text
    assert "SEM-972004 TST-1610-D" in text and "NON chiudibile: e' CRESCITA, non PRONTA_ALLA_RACCOLTA" in text
    assert "IN CORSO" in text and "SEM-972003 TST-1610-C" in text and "raccolti 1 su 4 SET" in text
    assert "RESA ATTESA NON COMPILATA" in text and "SEM-972005 TST-1610-E" in text
    comando = next(l for l in text.splitlines() if "--chiudi" in l)
    assert "SEM-972001" in comando and "SEM-972002" in comando
    assert "SEM-972003" not in comando and "SEM-972004" not in comando and "SEM-972005" not in comando


def test_preview_writes_nothing_and_execute_closes_one_by_one(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _setup(engine)
    runner = Runner()
    code, text = _esegui(engine, ["SEM-972001", "SEM-972002"], runner=runner)
    assert code == 0 and runner.calls == []
    assert "ANTEPRIMA: nulla e' stato scritto" in text and "SEM-972002 TST-1610-B" in text
    assert "dichiarata da Matteo il 01/02/2099" in text and "RAC-972002 4.5 SET" in text
    code, text = _esegui(engine, ["SEM-972001", "SEM-972002"], esegui=True, runner=runner)
    assert code == 0 and "FATTO: 2 semine chiuse" in text
    assert [c[c.index("--semina") + 1] for c in runner.calls] == ["SEM-972001", "SEM-972002"]
    primo = runner.calls[0]
    assert primo[primo.index("--target-state") + 1] == "CHIUSA"
    assert primo[primo.index("--final-outcome") + 1] == "raccolta completa"
    assert primo[primo.index("--idempotency-key") + 1] == "chiusura-guidata-SEM-972001"
    assert primo[primo.index("--effective-at") + 1].startswith("2099-02-01T09:00:00") and "--confirm" in primo
    assert "venduta" not in primo[primo.index("--reason") + 1]


def test_refuses_everything_that_is_not_fully_harvested_and_ready(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _setup(engine)
    casi = (("SEM-972003", "ha raccolto 1 SET su 4 attesi"), ("SEM-972004", "e' CRESCITA"),
            ("SEM-972005", "non ha la resa attesa compilata"), ("SEM-999999", "inesistente"))
    for codice, frase in casi:
        runner = Runner()
        code, text = _esegui(engine, [codice], esegui=True, runner=runner)
        assert code == 2 and frase in text and runner.calls == [], codice
    # un elenco con una sola semina non valida non chiude nemmeno le valide
    runner = Runner()
    code, _ = _esegui(engine, ["SEM-972001", "SEM-972003"], esegui=True, runner=runner)
    assert code == 2 and runner.calls == []


def test_already_closed_is_skipped_and_command_failure_stops(writer_postgresql_engine):
    engine = writer_postgresql_engine
    _setup(engine)
    _semina(engine, 972006, "TST-1610-F", raccolto="1", atteso="1")
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.exec_driver_sql(
            "UPDATE tpo.semine SET stato='CHIUSA', esito_finale='RACCOLTA_COMPLETA' WHERE public_id='SEM-972006'")
    runner = Runner()
    code, text = _esegui(engine, ["SEM-972006"], esegui=True, runner=runner)
    assert code == 0 and "gia' CHIUSA, salto" in text and runner.calls == []
    runner = Runner(returncode=3)
    code, text = _esegui(engine, ["SEM-972001", "SEM-972002"], esegui=True, runner=runner)
    assert code == 4 and "STOP: comando fallito per SEM-972001" in text and len(runner.calls) == 1


def test_blocks_on_active_allocations_and_on_dates_before_last_event():
    module = _module()
    base = {"id": "SEM-1", "codice": "X-1", "varieta": "V", "stato": "PRONTA_ALLA_RACCOLTA", "in_corso": 0,
            "atteso": Decimal(2), "raccolto": Decimal(2), "ultimo": None}
    assert module.blocco(base) is None and module.completa(base)
    assert "2 allocazioni PRODUZIONE_IN_CORSO" in module.blocco({**base, "in_corso": 2})
    assert not module.completa({**base, "raccolto": Decimal("1.9")})
    assert not module.completa({**base, "atteso": None})
