"""Registrazione di Clandestino (11/10/2026): anteprima, controlli e comandi costruiti, su PostgreSQL usa-e-getta.

I comandi di scrittura passano dal CLI (gia' coperto dai suoi test): qui `ctx.tpo` e' sostituito da un registratore
che risponde come il CLI."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest

from tests.infrastructure.postgresql.test_bolla_lettura_reader import _seed_carico_da_raccolta
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    TZ, _seed,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-11_clandestino.py"
ULTIMO = datetime(2026, 10, 7, 12, 0, tzinfo=TZ)
V = lambda n: f"Writer variety {n}"      # noqa: E731


def _module():
    spec = importlib.util.spec_from_file_location("clandestino_11_10", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _connect(engine):
    url = engine.url
    return psycopg.connect(host=url.host, port=url.port, dbname=url.database, user=url.username, autocommit=True)


class Recorder:
    def __init__(self, engine=None):
        self.calls = []
        self.fulfil = []
        self.engine = engine

    def __call__(self, args, label):
        self.calls.append(args)
        if args[:2] == ["semina", "transition"] and self.engine is not None:   # come farebbe il CLI vero
            with self.engine.begin() as connection:
                connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
                connection.exec_driver_sql("UPDATE tpo.semine SET stato=%s WHERE public_id=%s",
                                           (args[args.index("--target-state") + 1], args[args.index("--semina") + 1]))
        if args[0] == "raccolta":
            return f"RACCOLTA_ID: RAC-9{len(self.calls):05d}\n"
        if args[:2] == ["ordine", "registra-manuale"]:
            return ("ORDINE_ID: ORD-961099\nRIGA=RO-961091 POS=1 VARIETA=VAR-961001\n"
                    "RIGA=RO-961092 POS=2 VARIETA=VAR-961002\nRIGA=RO-961093 POS=3 VARIETA=VAR-961003\n")
        if args[:2] == ["delivery", "fulfil"]:
            self.fulfil.append(json.loads(Path(args[args.index("--lines-file") + 1]).read_text()))
            return "CONSEGNA_ID: CON-961001\n"
        return ""


def _setup(engine, module, monkeypatch):
    """961001=Cilantro (LUCE, 2 SET attesi), 961002=Afila e 961003=Rabano (PRONTE, 0.5 gia' raccolti)."""
    for number, letter in ((961001, "A"), (961002, "B"), (961003, "C")):
        _seed(engine, number, stock="0", order_quantity="1")
        _seed_carico_da_raccolta(engine, number, "0.5", f"TST-1010-{letter}", datetime(2098, 1, 1, 8, tzinfo=TZ))
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.exec_driver_sql("""UPDATE tpo.semine SET stato='LUCE', expected_useful_quantity=2,
                                      expected_useful_uom='SET',
                                      harvest_window_start=data_avvio + interval '9 days',
                                      harvest_window_end=data_avvio + interval '14 days'
                                      WHERE public_id='SEM-961001'""")
        connection.exec_driver_sql("""UPDATE tpo.semine SET stato='PRONTA_ALLA_RACCOLTA', expected_useful_quantity=3,
                                      expected_useful_uom='SET',
                                      harvest_window_start=data_avvio + interval '9 days',
                                      harvest_window_end=data_avvio + interval '14 days'
                                      WHERE public_id IN ('SEM-961002','SEM-961003')""")
        ordine = connection.exec_driver_sql("""
          INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,created_by)
          VALUES ('ORD-961099',(SELECT id FROM tpo.clienti WHERE public_id='CLI-961001'),DATE '2026-10-10',
                  DATE '2026-10-10','APERTO','MANUALE','writer-test') RETURNING id""").scalar_one()
        for pos, number in enumerate((961001, 961002, 961003), 1):
            connection.exec_driver_sql("""
              INSERT INTO tpo.righe_ordine(ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
              VALUES (%s,%s,(SELECT id FROM tpo.varieta WHERE public_id=%s),1,'SET',%s)""",
                                       (ordine, pos, f"VAR-{number}", f"RO-96109{pos}"))
    module.PRONTA = ("SEM-961001", V(961001), "2")
    module.VOCI = [(V(961001), "1", "SEM-961001"), (V(961002), "0.5", "SEM-961002"), (V(961003), "0.5", "SEM-961003")]
    b = module.carica_base()
    monkeypatch.setattr(b, "ultimo_evento", lambda ctx, semina: ULTIMO)


def _ctx(module, engine, execute, tmp_path, recorder=None):
    b = module.carica_base()
    b.WORK = tmp_path / "work"
    module.WORK = tmp_path / "work"
    ctx = b.Ctx(execute, tmp_path / "bolle", conn=_connect(engine))
    ctx.check_head = lambda: None
    if recorder is not None:
        ctx.tpo = recorder
    return ctx


def test_preview_writes_nothing_and_leaves_payment_and_corrective_commands(writer_postgresql_engine, tmp_path,
                                                                           monkeypatch, capsys):
    engine = writer_postgresql_engine
    module = _module()
    _setup(engine, module, monkeypatch)
    ctx = _ctx(module, engine, False, tmp_path)
    module.run(ctx, module.Orari(), None, tmp_path / "bolle", False)
    out = capsys.readouterr().out
    ctx.conn.close()
    assert "nuovo cliente Clandestino" in out and "-> CRESCITA" in out and "-> PRONTA_ALLA_RACCOLTA" in out
    assert "metodo di pagamento NON indicato" in out and "--pagata CON-xxxxxx" in out
    assert "COMANDI CORRETTIVI" in out and "OGNI_X_GIORNI" in out and "2026-10-15" in out
    assert "anteprima: non eseguito" in out


def test_execute_builds_the_governed_commands_with_estimated_times(writer_postgresql_engine, tmp_path, monkeypatch):
    engine = writer_postgresql_engine
    module = _module()
    _setup(engine, module, monkeypatch)
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, module.Orari(), "CONTANTI", tmp_path / "bolle", True)
    ctx.conn.close()

    calls = recorder.calls
    assert [c[1] for c in calls if c[0] == "onboarding"] == ["customer"]
    cliente = next(c for c in calls if c[0] == "onboarding")
    assert cliente[cliente.index("--denomination") + 1] == "Clandestino"
    assert "Puerto del Rosario" in cliente[cliente.index("--reason") + 1]

    transitions = {c[c.index("--target-state") + 1]: c[c.index("--effective-at") + 1]
                   for c in calls if c[:2] == ["semina", "transition"]}
    assert transitions == {"CRESCITA": "2026-10-07T12:01:00+00:00" if "+00:00" in transitions.get("CRESCITA", "")
                           else transitions["CRESCITA"], "PRONTA_ALLA_RACCOLTA": transitions["PRONTA_ALLA_RACCOLTA"]}
    assert transitions["PRONTA_ALLA_RACCOLTA"].startswith("2026-10-10T09:50:00")
    assert transitions["CRESCITA"].endswith("12:01:00" + transitions["CRESCITA"][-6:])

    raccolte = {c[c.index("--semina") + 1]: (c[c.index("--quantity") + 1], c[c.index("--effective-at") + 1])
                for c in calls if c[0] == "raccolta"}
    assert {s: q for s, (q, _) in raccolte.items()} == {"SEM-961001": "1", "SEM-961002": "0.5", "SEM-961003": "0.5"}
    assert all(t.startswith("2026-10-10T10:00:00") for _, t in raccolte.values())
    assert sum(1 for c in calls if c[:2] == ["movimento", "carica-raccolta"]) == 3

    [righe] = recorder.fulfil
    assert [(r["order_line_id"], r["quantity"], r["semina"]) for r in righe] == [
        ("RO-961091", "1", "SEM-961001"), ("RO-961092", "0.5", "SEM-961002"), ("RO-961093", "0.5", "SEM-961003")]
    fulfil = next(c for c in calls if c[:2] == ["delivery", "fulfil"])
    assert fulfil[fulfil.index("--planned-date") + 1] == "2026-10-10"
    assert fulfil[fulfil.index("--effective-at") + 1].startswith("2026-10-10T10:05:00")

    pagamento = next(c for c in calls if c[0] == "pagamento-consegna")
    assert pagamento[pagamento.index("--metodo") + 1] == "CONTANTI"
    assert pagamento[pagamento.index("--data") + 1] == "2026-10-10" and "--storico" not in pagamento
    assert pagamento[pagamento.index("--consegna") + 1] == "CON-961001"
    bolle = [c for c in calls if c[:2] == ["bolla", "genera"]]
    assert len(bolle) == 2 and "--sovrascrivi" not in bolle[0] and "--sovrascrivi" in bolle[1]
    # ordine: ordine manuale prima della consegna, pronta prima delle raccolte
    ordine = [" ".join(c[:2]) for c in calls]
    assert ordine.index("semina transition") < ordine.index("raccolta record") < ordine.index("delivery fulfil")


def test_programme_is_created_for_the_existing_customer_once(writer_postgresql_engine, tmp_path, monkeypatch, capsys):
    engine = writer_postgresql_engine
    module = _module()
    _setup(engine, module, monkeypatch)
    with engine.begin() as connection:
        connection.exec_driver_sql("""INSERT INTO tpo.clienti(public_id,denominazione,created_by,updated_at,updated_by)
                                      VALUES ('CLI-961500','Clandestino','writer-test',now(),'writer-test')""")
    seen = []
    monkeypatch.setattr(module, "carica_programma", lambda: SimpleNamespace(
        run=lambda conn, cliente, righe, prima, ogni, motivo, esegui: seen.append((cliente, righe, prima, ogni, esegui)) or 0))
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, module.Orari(), None, tmp_path / "bolle", False)
    ctx.conn.close()
    assert not any(c[0] == "onboarding" for c in recorder.calls)               # cliente gia' esistente: riuso
    assert seen == [("Clandestino", ["Cilantro:1"], module.PROGRAMMA_PRIMA, 7, True)]
    assert module.PROGRAMMA_PRIMA.weekday() == 3                                   # giovedi'
    assert not any(c[0] == "pagamento-consegna" for c in recorder.calls)         # senza --metodo non inventa nulla
    assert "--pagata CON-961001 --metodo CONTANTI" in capsys.readouterr().out


@pytest.mark.parametrize("mutation, message", [
    ("UPDATE tpo.semine SET expected_useful_quantity=3 WHERE public_id='SEM-961001'", "non coincidono"),
    ("UPDATE tpo.semine SET stato='CRESCITA' WHERE public_id='SEM-961002'", "non PRONTA_ALLA_RACCOLTA"),
    ("UPDATE tpo.semine SET expected_useful_quantity=0.75 WHERE public_id='SEM-961003'", "superano gli attesi"),
    ("UPDATE tpo.stock SET disponibile=1 WHERE varieta_id=(SELECT id FROM tpo.varieta WHERE public_id='VAR-961002')",
     "giacenza"),
])
def test_guards_stop_before_writing(writer_postgresql_engine, tmp_path, monkeypatch, mutation, message):
    engine = writer_postgresql_engine
    module = _module()
    _setup(engine, module, monkeypatch)
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.exec_driver_sql(mutation)
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    with pytest.raises(module.carica_base().Stop, match=message):
        module.run(ctx, module.Orari(), None, tmp_path / "bolle", True)
    ctx.conn.close()
    assert not any(c[0] in ("raccolta", "delivery", "movimento") for c in recorder.calls)


def test_already_ready_cilantro_skips_the_declaration_and_times_must_be_ordered(writer_postgresql_engine, tmp_path,
                                                                                monkeypatch):
    engine = writer_postgresql_engine
    module = _module()
    _setup(engine, module, monkeypatch)
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.exec_driver_sql("UPDATE tpo.semine SET stato='PRONTA_ALLA_RACCOLTA' WHERE public_id='SEM-961001'")
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, module.Orari(), None, tmp_path / "bolle", True)
    ctx.conn.close()
    assert not any(c[:2] == ["semina", "transition"] for c in recorder.calls)
    with pytest.raises(ValueError):
        module.Orari(pronta="10:10", raccolta="10:00", consegna="10:05")
