"""Script 11/10/2026 dei pagamenti consegna: anteprima, storico, pagamento vero, annullamento, rilancio.

I comandi di scrittura passano dal vero CLI (parser + adapter) collegato a un database PostgreSQL usa-e-getta;
la rigenerazione delle bolle e' registrata, non eseguita."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
import sqlalchemy as sa
from alembic import command as alembic_command

from src.tpo_core.cli import main as main_module
from src.tpo_core.infrastructure.postgresql.alembic import make_config
from tests.infrastructure.postgresql.test_production_planning_migrations import isolated_postgresql  # noqa: F401
from tests.integration.postgresql.test_pagamento_consegna import _Factory

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-11_pagamenti_consegne.py"


def _module():
    spec = importlib.util.spec_from_file_location("pagamenti_consegne_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db(isolated_postgresql, monkeypatch):  # noqa: F811
    import uuid
    cluster = isolated_postgresql.engine
    name = f"tpo_pagscript_{uuid.uuid4().hex}"
    with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = sa.create_engine(cluster.url.set(database=name))
    with engine.begin() as c:
        alembic_command.upgrade(make_config(connection=c), "head")
        c.exec_driver_sql("""INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
                             VALUES ('CLI-000001','Splash','t',CURRENT_TIMESTAMP,'t'),
                                    ('CLI-000002','Azul y Sal','t',CURRENT_TIMESTAMP,'t')""")
        for number, cli, stato in ((1, 1, "CONSEGNATA"), (2, 1, "CONSEGNATA"), (3, 2, "CONSEGNATA"),
                                   (4, 2, "PROGRAMMATA")):
            eff = "TIMESTAMPTZ '2026-10-09 10:00+01'" if stato == "CONSEGNATA" else "NULL"
            c.exec_driver_sql(f"""INSERT INTO tpo.consegne(public_id,cliente_id,stato,data_prevista,data_effettiva,created_by)
                                  SELECT 'CON-00000{number}',id,'{stato}',DATE '2026-10-09',{eff},'t'
                                  FROM tpo.clienti WHERE public_id='CLI-00000{cli}'""")
    url = engine.url
    conn = psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username, autocommit=True)
    import src.tpo_core.cli.pagamento_consegna as cli_module
    from src.tpo_core.application.pagamento_consegna import PagamentoConsegnaService
    from src.tpo_core.infrastructure.postgresql.pagamento_consegna import PostgreSQLPagamentoConsegnaWriter
    monkeypatch.setattr(cli_module, "build_pagamento_consegna_service",
                        lambda settings: PagamentoConsegnaService(PostgreSQLPagamentoConsegnaWriter(_Factory(engine))))
    monkeypatch.setattr(cli_module.PostgreSQLSettings, "from_environment", lambda: object())
    try:
        yield engine, conn
    finally:
        conn.close()
        engine.dispose()
        with cluster.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


class Ctx:
    """Contesto del base-script ma con `tpo` che esegue il CLI vero (pagamenti) o registra (bolle)."""
    def __init__(self, module, conn, execute):
        base = module.carica_base()
        self.execute, self.conn, self.calls, self.bolle = execute, conn, [], []
        self._real = base.Ctx(execute, Path("."), conn=conn)

    def q(self, sql, args=()): return self._real.q(sql, args)
    def one(self, sql, args=()): return self._real.one(sql, args)
    def check_head(self): return self._real.check_head()

    def tpo(self, args, label):
        self.calls.append(args)
        if not self.execute:
            return ""
        if args[0] == "bolla":
            self.bolle.append(args[args.index("--consegna") + 1])
            return ""
        from src.tpo_core.cli.pagamento_consegna import run_pagamento_consegna_command
        namespace = main_module._parser().parse_args(args)
        out, err = StringIO(), StringIO()
        code = run_pagamento_consegna_command(namespace, stdout=out, stderr=err)
        assert code == 0, err.getvalue()
        return out.getvalue()


def _args(module, *argv):
    return module.parser().parse_args(list(argv))


def _scalar(engine, sql):
    with engine.connect() as connection:
        return connection.exec_driver_sql(sql).scalar_one()


def test_storico_preview_writes_nothing_then_declares_all_paid_with_flag(db, tmp_path, capsys):
    engine, conn = db
    module = _module()
    ctx = Ctx(module, conn, execute=False)
    assert module.run(ctx, _args(module, "--storico", "--data", "2026-10-11", "--pdf-dir", str(tmp_path))) == 0
    assert _scalar(engine, "SELECT count(*) FROM tpo.pagamenti_consegna") == 0
    assert len(ctx.calls) == 3 + 3                   # 3 pagamenti + 3 bolle; la consegna PROGRAMMATA non c'e'
    assert "da pagare: 3" in capsys.readouterr().out

    ctx = Ctx(module, conn, execute=True)
    assert module.run(ctx, _args(module, "--storico", "--data", "2026-10-11", "--pdf-dir", str(tmp_path))) == 0
    rows = engine.connect().exec_driver_sql(
        "SELECT c.public_id,p.data_pagamento,p.metodo,p.importo,p.storico,p.note FROM tpo.pagamenti_consegna p "
        "JOIN tpo.consegne c ON c.id=p.consegna_id ORDER BY c.public_id").all()
    assert [r[0] for r in rows] == ["CON-000001", "CON-000002", "CON-000003"]
    assert all(r[1] == date(2026, 10, 11) and r[2] == "ALTRO" and r[3] is None and r[4] is True for r in rows)
    assert "non sono stati registrati" in rows[0][5]
    assert sorted(ctx.bolle) == ["CON-000001", "CON-000002", "CON-000003"]

    # rilancio: niente di nuovo, nessun doppione
    ctx = Ctx(module, conn, execute=True)
    assert module.run(ctx, _args(module, "--storico", "--pdf-dir", str(tmp_path))) == 0
    assert _scalar(engine, "SELECT count(*) FROM tpo.pagamenti_consegna") == 3
    assert not [c for c in ctx.calls if c[0] == "pagamento-consegna"]


def test_real_payment_cancel_and_repay(db, tmp_path):
    engine, conn = db
    module = _module()
    base = ["--pdf-dir", str(tmp_path)]
    ctx = Ctx(module, conn, execute=True)
    assert module.run(ctx, _args(module, "--pagata", "CON-000001", "--metodo", "BIZUM",
                                 "--data", "2026-10-12", "--importo", "12.50", *base)) == 0
    with engine.connect() as connection:
        metodo, importo, storico, data = connection.exec_driver_sql(
            "SELECT metodo,importo,storico,data_pagamento FROM tpo.pagamenti_consegna").one()
    assert (metodo, str(importo), storico, data) == ("BIZUM", "12.50", False, date(2026, 10, 12))
    assert ctx.bolle == ["CON-000001"]

    ctx = Ctx(module, conn, execute=True)
    assert module.run(ctx, _args(module, "--annulla", "PGC-000001", *base)) == 0
    assert _scalar(engine, "SELECT count(*) FROM tpo.pagamenti_consegna WHERE tipo='ANNULLAMENTO'") == 1

    ctx = Ctx(module, conn, execute=True)           # corretto: nuovo pagamento, chiave nuova (n2)
    assert module.run(ctx, _args(module, "--pagata", "CON-000001", "--metodo", "CONTANTI",
                                 "--data", "2026-10-12", *base)) == 0
    assert _scalar(engine, "SELECT count(*) FROM tpo.pagamenti_consegna WHERE tipo='PAGAMENTO'") == 2


def test_stops_on_bad_input_and_missing_migration(db, tmp_path):
    engine, conn = db
    module = _module()
    base_mod = module.carica_base()
    ctx = Ctx(module, conn, execute=False)
    with pytest.raises(base_mod.Stop, match="non effettuate"):
        module.run(ctx, _args(module, "--pagata", "CON-000004", "--metodo", "CONTANTI", "--pdf-dir", str(tmp_path)))
    with pytest.raises(base_mod.Stop, match="solo con una consegna"):
        module.run(ctx, _args(module, "--pagata", "CON-000001", "CON-000002", "--metodo", "CONTANTI",
                              "--importo", "5", "--pdf-dir", str(tmp_path)))
    with pytest.raises(base_mod.Stop, match="non e' un pagamento"):
        module.run(ctx, _args(module, "--annulla", "PGC-000099", "--pdf-dir", str(tmp_path)))
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE public.alembic_version SET version_num='20261003_0037'")
    with pytest.raises(base_mod.Stop, match="migrazione"):
        module.run(ctx, _args(module, "--storico", "--pdf-dir", str(tmp_path)))


def test_storico_can_exclude_clients_that_did_not_pay_and_prints_corrective_command(db, tmp_path, capsys):
    engine, conn = db
    module = _module()
    base = ["--pdf-dir", str(tmp_path)]
    ctx = Ctx(module, conn, execute=False)
    assert module.run(ctx, _args(module, "--storico", "--escludi-clienti", "azul y sal", *base)) == 0
    out = capsys.readouterr().out
    assert "ESCLUSA CON-000003 (Azul y Sal)" in out and "pagate 2 consegne" in out
    assert "--annulla PGC-000001 [PGC-...] --esegui" in out and _scalar(
        engine, "SELECT count(*) FROM tpo.pagamenti_consegna") == 0

    ctx = Ctx(module, conn, execute=True)
    assert module.run(ctx, _args(module, "--storico", "--escludi-clienti", "Azul", *base)) == 0
    out = capsys.readouterr().out
    assert "--annulla PGC-000001 PGC-000002 --esegui" in out
    assert engine.connect().exec_driver_sql(
        "SELECT c.public_id FROM tpo.pagamenti_consegna p JOIN tpo.consegne c ON c.id=p.consegna_id "
        "ORDER BY 1").all() == [("CON-000001",), ("CON-000002",)]
    assert sorted(ctx.bolle) == ["CON-000001", "CON-000002"]

    # il comando correttivo stampato funziona e dice come rimettere il pagato
    ctx = Ctx(module, conn, execute=True)
    assert module.run(ctx, _args(module, "--annulla", "PGC-000001", "PGC-000002", *base)) == 0
    out = capsys.readouterr().out
    assert "--pagata CON-000001 --metodo ALTRO --data" in out
    assert _scalar(engine, "SELECT count(*) FROM tpo.pagamenti_consegna WHERE tipo='ANNULLAMENTO'") == 2

    base_mod = module.carica_base()
    with pytest.raises(base_mod.Stop, match="assomiglia"):
        module.run(Ctx(module, conn, execute=False),
                   _args(module, "--storico", "--escludi-clienti", "Inesistente", *base))


def test_storico_can_exclude_single_consegne(db, tmp_path, capsys):
    engine, conn = db
    module = _module()
    base = ["--pdf-dir", str(tmp_path)]
    ctx = Ctx(module, conn, execute=True)
    assert module.run(ctx, _args(module, "--storico", "--escludi-consegne", "CON-000002", *base)) == 0
    out = capsys.readouterr().out
    assert "ESCLUSA CON-000002 (Splash)" in out
    assert engine.connect().exec_driver_sql(
        "SELECT c.public_id FROM tpo.pagamenti_consegna p JOIN tpo.consegne c ON c.id=p.consegna_id "
        "ORDER BY 1").all() == [("CON-000001",), ("CON-000003",)]
    with pytest.raises(module.carica_base().Stop, match="inesistenti"):
        module.run(Ctx(module, conn, execute=False),
                   _args(module, "--storico", "--escludi-consegne", "CON-000099", *base))
