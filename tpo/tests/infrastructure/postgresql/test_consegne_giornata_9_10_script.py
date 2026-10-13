"""Consegne del 9/10/2026: controlli, anteprima, modifica Splash e comandi costruiti, su PostgreSQL usa-e-getta.

I comandi di scrittura passano dal CLI (`tpo ...`, gia' coperti dai loro test): qui `ctx.tpo` e' sostituito da un
registratore che risponde come il CLI. La modifica ordine di Splash usa invece il database vero."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from tests.infrastructure.postgresql.test_bolla_lettura_reader import _seed_carico_da_raccolta
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    TZ, _seed,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-09_consegne_giornata.py"
T = datetime(2099, 1, 2, 9, 0, tzinfo=TZ)


def _module():
    spec = importlib.util.spec_from_file_location("consegne_9_10", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine, autocommit=True):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username,
                           autocommit=autocommit)


def _scalar(engine, sql, args=()):
    with engine.connect() as connection:
        return connection.exec_driver_sql(sql, args).scalar_one()


class Recorder:
    def __init__(self):
        self.calls = []
        self.fulfil = []

    def __call__(self, args, label):
        self.calls.append(args)
        if args[0] == "raccolta":
            return f"RACCOLTA_ID: RAC-9{len(self.calls):05d}\n"
        if args[:2] == ["ordine", "registra-manuale"]:
            return "ORDINE_ID: ORD-961099\nRIGA=RO-961099 POS=1 VARIETA=VAR-961004\n"
        if args[:2] == ["delivery", "fulfil"]:
            self.fulfil.append((args[args.index("--client") + 1], json.loads(Path(args[args.index("--lines-file") + 1]).read_text())))
            return f"CONSEGNA_ID: CON-9{len(self.fulfil):05d}\n"
        return ""


def _setup(engine, module):
    """Splash=961001 (2 righe da 1), Azul=961003 (3), Callao=961004 (manuale), Alchimia=961005 (2 righe) + 961006
    (giacenza). Ogni varieta' ha una semina PRONTA con una raccolta storica di 0.5."""
    _seed(engine, 961001, stock="0", lines=2, order_quantity="1")
    _seed(engine, 961003, stock="0", order_quantity="3")
    _seed(engine, 961004, stock="0", order_quantity="1")
    _seed(engine, 961005, stock="0", order_quantity="0.5")
    _seed(engine, 961006, stock="2", order_quantity="0.5")
    with engine.begin() as connection:     # la riga di giacenza di Alchimia sta sullo stesso cliente
        connection.exec_driver_sql("""UPDATE tpo.ordini SET cliente_id=(SELECT id FROM tpo.clienti
                                      WHERE public_id='CLI-961005') WHERE public_id='ORD-961006'""")
    for number, letter in ((961001, "A"), (961003, "B"), (961004, "C"), (961005, "D")):
        _seed_carico_da_raccolta(engine, number, "0.5", f"TST-0110-{letter}", datetime(2098, 1, 1, 8, tzinfo=TZ))
        with engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
            connection.exec_driver_sql("UPDATE tpo.semine SET stato='PRONTA_ALLA_RACCOLTA' WHERE public_id=%s",
                                       (f"SEM-{number:06d}",))
    v = lambda n: f"Writer variety {n}"      # noqa: E731
    module.SPLASH = ("CLI-961001", "Writer client 961001")
    module.AZUL = ("CLI-961003", "Writer client 961003")
    module.CALLAO = ("CLI-961004", "Writer client 961004")
    module.ALCHIMIA = ("CLI-961005", "Writer client 961005")
    module.SPLASH_RIGHE = [("ORD-961001", "RO-961001", v(961001), "0.5", "SEM-961001"),
                           ("ORD-961001", "RO-961002", v(961001), "0.5", "SEM-961001")]
    module.AZUL_RIGA = ("ORD-961003", "RO-961003", v(961003), "2", "SEM-961003")
    module.CALLAO_MANUALE = [(v(961004), "1", "SEM-961004")]
    module.ALCHIMIA_RIGHE = [("ORD-961005", "RO-961005", v(961005), "0.25", "SEM-961005"),
                             ("ORD-961006", "RO-961006", v(961006), "0.5", "SEM-961099")]
    module.DA_GIACENZA = {"SEM-961099"}


def _ctx(module, engine, execute, tmp_path, recorder=None):
    module.WORK = tmp_path / "work"
    module.b.WORK = tmp_path / "work"
    ctx = module.b.Ctx(execute, tmp_path / "bolle", conn=_connect(engine))
    ctx.check_head = lambda: None
    if recorder is not None:
        ctx.tpo = recorder
    return ctx


def test_preview_checks_and_guards_write_nothing(writer_postgresql_engine, tmp_path, capsys):
    engine = writer_postgresql_engine
    module = _module()
    _setup(engine, module)
    ctx = _ctx(module, engine, False, tmp_path)
    da_fare = dict.fromkeys(("splash", "azul", "callao", "alchimia"), True)

    # cliente sbagliato (nome diverso da quello atteso): si ferma
    module.CALLAO = ("CLI-961004", "Altro cliente")
    with pytest.raises(module.b.Stop, match="Non procedo"):
        module.controlli(ctx, module.Piano(), da_fare)
    module.CALLAO = ("CLI-961004", "Writer client 961004")

    # riga di un altro ordine/cliente: si ferma
    module.AZUL_RIGA = ("ORD-961003", "RO-961001", "Writer variety 961003", "2", "SEM-961003")
    with pytest.raises(module.b.Stop, match="a sistema e'"):
        module.controlli(ctx, module.Piano(), da_fare)
    module.AZUL_RIGA = ("ORD-961003", "RO-961003", "Writer variety 961003", "2", "SEM-961003")

    # residuo insufficiente (3 a sistema, ne chiedo 4)
    module.AZUL_RIGA = ("ORD-961003", "RO-961003", "Writer variety 961003", "2", "SEM-961003")
    with pytest.raises(module.b.Stop, match="residuo"):
        module.controlli(ctx, module.Piano(azul_cilantro="4"), da_fare)
    ctx.conn.close()


def test_over_expected_harvest_and_nonzero_stock_stop(writer_postgresql_engine, tmp_path):
    engine = writer_postgresql_engine
    module = _module()
    _setup(engine, module)
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.exec_driver_sql("UPDATE tpo.semine SET expected_useful_quantity=2, expected_useful_uom='SET', "
                                   "harvest_window_start=data_avvio + interval '9 days', harvest_window_end=data_avvio + interval '14 days' "
                                   "WHERE public_id='SEM-961003'")
    ctx = _ctx(module, engine, False, tmp_path, recorder=Recorder())
    # 0.5 gia' raccolti + 2 = 2.5 > 2 attesi: serve --oltre-attesi
    with pytest.raises(module.b.Stop, match="oltre-attesi"):
        module.raccolte(ctx, module.Piano(), T)
    module.raccolte(ctx, module.Piano(oltre_attesi=True), T)       # con la dichiarazione passa
    assert any(c[0] == "raccolta" and c[c.index("--semina") + 1] == "SEM-961003" for c in ctx.tpo.calls)
    with engine.begin() as connection:                              # giacenza diversa da 0 prima del carico
        connection.exec_driver_sql("UPDATE tpo.stock SET disponibile=1 WHERE varieta_id="
                                   "(SELECT id FROM tpo.varieta WHERE public_id='VAR-961004')")
    with pytest.raises(module.b.Stop, match="giacenza"):
        module.raccolte(ctx, module.Piano(oltre_attesi=True), T)
    ctx.conn.close()


def test_execute_amends_splash_and_builds_the_governed_commands(writer_postgresql_engine, tmp_path):
    engine = writer_postgresql_engine
    module = _module()
    _setup(engine, module)
    with engine.begin() as connection:       # l'ordine manuale di El Callao che il CLI crea (qui simulato)
        order = connection.exec_driver_sql("""
          INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,created_by)
          VALUES ('ORD-961099',(SELECT id FROM tpo.clienti WHERE public_id='CLI-961004'),DATE '2099-01-02',
                  DATE '2099-01-02','APERTO','MANUALE','writer-test') RETURNING id""").scalar_one()
        connection.exec_driver_sql("""
          INSERT INTO tpo.righe_ordine(ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
          VALUES (%s,1,(SELECT id FROM tpo.varieta WHERE public_id='VAR-961004'),1,'SET','RO-961099')""", (order,))
    recorder = Recorder()
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.fase_consegne(ctx, module.Piano(oltre_attesi=True), T, lambda: _connect(engine, autocommit=False))
    ctx.conn.close()

    # Splash: le due righe sono state portate a 0.5 dal vero database, con audit
    assert _scalar(engine, "SELECT quantita FROM tpo.righe_ordine WHERE public_id='RO-961001'") == Decimal("0.5")
    assert _scalar(engine, "SELECT quantita FROM tpo.righe_ordine WHERE public_id='RO-961002'") == Decimal("0.5")

    comandi = [" ".join(c[:2]) for c in recorder.calls]
    assert comandi.count("raccolta record") == 4 and comandi.count("movimento carica-raccolta") == 4
    assert comandi.count("delivery fulfil") == 4 and comandi.count("bolla genera") == 4
    assert comandi.count("ordine registra-manuale") == 1
    raccolte = {c[c.index("--semina") + 1]: c[c.index("--quantity") + 1]
                for c in recorder.calls if c[0] == "raccolta"}
    assert raccolte == {"SEM-961001": "1", "SEM-961003": "2", "SEM-961004": "1", "SEM-961005": "0.25"}

    per_cliente = dict(recorder.fulfil)
    assert set(per_cliente) == {"CLI-961001", "CLI-961003", "CLI-961004", "CLI-961005"}
    splash = per_cliente["CLI-961001"]
    assert [r["quantity"] for r in splash] == ["0.5", "0.5"] and {r["semina"] for r in splash} == {"SEM-961001"}
    assert all(r["expected_order_line_version"] >= 1 for r in splash)       # versione dopo la modifica
    alchimia = per_cliente["CLI-961005"]
    assert [(r["order_line_id"], r["quantity"], r["semina"]) for r in alchimia] == [
        ("RO-961005", "0.25", "SEM-961005"), ("RO-961006", "0.5", "SEM-961099")]
    assert per_cliente["CLI-961004"][0]["order_id"] == "ORD-961099"


def test_rerun_skips_splash_amendment_when_already_done(writer_postgresql_engine, tmp_path, capsys):
    engine = writer_postgresql_engine
    module = _module()
    _setup(engine, module)
    ctx = _ctx(module, engine, False, tmp_path)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE tpo.righe_ordine SET quantita=0.5 WHERE public_id IN ('RO-961001','RO-961002')")
    module.modifica_splash(ctx, lambda: _connect(engine, autocommit=False))
    assert capsys.readouterr().out.count("gia' 0.5 SET, salto") == 2
    ctx.conn.close()
