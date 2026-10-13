"""Consegna a La Jaira (12/10/2026): anteprima, legame all'ordine aperto, ordine manuale e protezioni, su PostgreSQL
usa-e-getta. I comandi di scrittura passano dal CLI (gia' coperto dai suoi test): `ctx.tpo` e' un registratore."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pytest

from tests.infrastructure.postgresql.test_bolla_lettura_reader import _seed_carico_da_raccolta
from tests.infrastructure.postgresql.test_clandestino_script import Recorder, _connect
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    TZ, _seed,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-12_jaira.py"
ULTIMO = datetime(2026, 10, 7, 12, 0, tzinfo=TZ)
BASE = datetime(2026, 10, 12, 11, 0, tzinfo=TZ)
V = lambda n: f"Writer variety {n}"      # noqa: E731


def _module():
    spec = importlib.util.spec_from_file_location("jaira_12_10", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ordine(engine, numero, riga_base, data="2026-10-13"):
    with engine.begin() as connection:
        ordine = connection.exec_driver_sql("""
          INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,created_by)
          VALUES (%s,(SELECT id FROM tpo.clienti WHERE public_id='CLI-961001'),%s::date,%s::date,'APERTO','MANUALE',
                  'writer-test') RETURNING id""", (f"ORD-{numero}", data, data)).scalar_one()
        for pos, var in enumerate((961001, 961002, 961003), 1):
            connection.exec_driver_sql("""
              INSERT INTO tpo.righe_ordine(ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
              VALUES (%s,%s,(SELECT id FROM tpo.varieta WHERE public_id=%s),1,'SET',%s)""",
                                       (ordine, pos, f"VAR-{var}", f"RO-{riga_base + pos}"))


def _setup(engine, module, monkeypatch, con_ordine=True):
    """961001=Afila (LUCE, 7 SET attesi), 961002=Cilantro e 961003=Rabano (PRONTE, 0.5 gia' raccolti)."""
    for number, letter in ((961001, "A"), (961002, "B"), (961003, "C")):
        _seed(engine, number, stock="0", order_quantity="1")
        _seed_carico_da_raccolta(engine, number, "0.5", f"TST-1210-{letter}", datetime(2098, 1, 1, 8, tzinfo=TZ))
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.exec_driver_sql("""UPDATE tpo.semine SET stato='LUCE', expected_useful_quantity=7,
                                      expected_useful_uom='SET',
                                      harvest_window_start=data_avvio + interval '9 days',
                                      harvest_window_end=data_avvio + interval '14 days'
                                      WHERE public_id='SEM-961001'""")
        connection.exec_driver_sql("""UPDATE tpo.semine SET stato='PRONTA_ALLA_RACCOLTA', expected_useful_quantity=3,
                                      expected_useful_uom='SET',
                                      harvest_window_start=data_avvio + interval '9 days',
                                      harvest_window_end=data_avvio + interval '14 days'
                                      WHERE public_id IN ('SEM-961002','SEM-961003')""")
    if con_ordine:
        _ordine(engine, 961099, 961090)
    module.JAIRA = ("CLI-961001", "writer client")
    module.PRONTA = ("SEM-961001", V(961001), "7")
    voci = [(V(961001), "1", "SEM-961001"), (V(961002), "0.5", "SEM-961002"), (V(961003), "0.5", "SEM-961003")]
    b = module.carica_base()
    monkeypatch.setattr(b, "ultimo_evento", lambda ctx, semina: ULTIMO)
    return voci


def _ctx(module, engine, execute, tmp_path, recorder=None):
    b = module.carica_base()
    b.WORK = tmp_path / "work"
    module.WORK = tmp_path / "work"
    ctx = b.Ctx(execute, tmp_path / "bolle", conn=_connect(engine))
    ctx.check_head = lambda: None
    if recorder is not None:
        ctx.tpo = recorder
    return ctx


def test_preview_links_the_open_order_and_writes_nothing(writer_postgresql_engine, tmp_path, monkeypatch, capsys):
    engine = writer_postgresql_engine
    module = _module()
    voci = _setup(engine, module, monkeypatch)
    ctx = _ctx(module, engine, False, tmp_path)
    module.run(ctx, module.Orari(BASE), voci, None, tmp_path / "bolle")
    out = capsys.readouterr().out
    ctx.conn.close()
    assert "-> CRESCITA" in out and "-> PRONTA_ALLA_RACCOLTA" in out
    assert "la consegna si lega a ORD-961099" in out and "su ORD-961099" in out
    assert "metodo NON indicato" in out and "COMANDI CORRETTIVI" in out
    assert "anteprima: non eseguito" in out


def test_execute_links_the_open_order_with_provenance_and_times(writer_postgresql_engine, tmp_path, monkeypatch):
    engine = writer_postgresql_engine
    module = _module()
    voci = _setup(engine, module, monkeypatch)
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, module.Orari(BASE), voci, None, tmp_path / "bolle")
    ctx.conn.close()
    calls = recorder.calls

    assert not any(c[:2] == ["ordine", "registra-manuale"] for c in calls)
    transitions = {c[c.index("--target-state") + 1]: c[c.index("--effective-at") + 1]
                   for c in calls if c[:2] == ["semina", "transition"]}
    assert set(transitions) == {"CRESCITA", "PRONTA_ALLA_RACCOLTA"}
    assert transitions["PRONTA_ALLA_RACCOLTA"] == BASE.isoformat()
    assert all(c[c.index("--semina") + 1] == "SEM-961001" for c in calls if c[:2] == ["semina", "transition"])

    raccolte = {c[c.index("--semina") + 1]: (c[c.index("--quantity") + 1], c[c.index("--effective-at") + 1])
                for c in calls if c[0] == "raccolta"}
    assert {s: q for s, (q, _) in raccolte.items()} == {"SEM-961001": "1", "SEM-961002": "0.5", "SEM-961003": "0.5"}
    assert all(t == "2026-10-12T11:01:00+00:00" or t.startswith("2026-10-12T11:01:00") for _, t in raccolte.values())
    assert sum(1 for c in calls if c[:2] == ["movimento", "carica-raccolta"]) == 3

    [righe] = recorder.fulfil
    assert [(r["order_id"], r["order_line_id"], r["quantity"], r["semina"]) for r in righe] == [
        ("ORD-961099", "RO-961091", "1", "SEM-961001"), ("ORD-961099", "RO-961092", "0.5", "SEM-961002"),
        ("ORD-961099", "RO-961093", "0.5", "SEM-961003")]
    fulfil = next(c for c in calls if c[:2] == ["delivery", "fulfil"])
    assert fulfil[fulfil.index("--planned-date") + 1] == "2026-10-12"     # min(prevista 13/10, oggi)
    assert fulfil[fulfil.index("--effective-at") + 1].startswith("2026-10-12T11:02:00")
    assert not any(c[0] == "pagamento-consegna" for c in calls)            # senza --metodo non inventa nulla
    ordine = [" ".join(c[:2]) for c in calls]
    assert ordine.index("semina transition") < ordine.index("raccolta record") < ordine.index("delivery fulfil")
    assert sum(1 for c in calls if c[:2] == ["bolla", "genera"]) == 1


def test_payment_is_registered_only_with_an_explicit_method(writer_postgresql_engine, tmp_path, monkeypatch):
    engine = writer_postgresql_engine
    module = _module()
    voci = _setup(engine, module, monkeypatch)
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, module.Orari(BASE), voci, "CONTANTI", tmp_path / "bolle")
    ctx.conn.close()
    pagamento = next(c for c in recorder.calls if c[0] == "pagamento-consegna")
    assert pagamento[pagamento.index("--metodo") + 1] == "CONTANTI"
    assert pagamento[pagamento.index("--data") + 1] == "2026-10-12" and "--storico" not in pagamento
    assert pagamento[pagamento.index("--consegna") + 1] == "CON-961001"
    bolle = [c for c in recorder.calls if c[:2] == ["bolla", "genera"]]
    assert len(bolle) == 2 and "--sovrascrivi" in bolle[1]


def test_without_an_open_order_or_with_manual_flag_it_creates_a_manual_order(writer_postgresql_engine, tmp_path,
                                                                             monkeypatch):
    engine = writer_postgresql_engine
    module = _module()
    voci = _setup(engine, module, monkeypatch)            # l'ordine aperto c'e', ma --manuale lo ignora
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, module.Orari(BASE), voci, None, tmp_path / "bolle", manuale=True)
    ctx.conn.close()
    manuale = next(c for c in recorder.calls if c[:2] == ["ordine", "registra-manuale"])
    assert manuale[manuale.index("--client") + 1] == "CLI-961001"
    assert manuale.count("--riga") == 3
    fulfil = next(c for c in recorder.calls if c[:2] == ["delivery", "fulfil"])
    assert fulfil[fulfil.index("--planned-date") + 1] == "2026-10-12"


def test_two_candidate_orders_stop_before_writing_and_the_flag_picks_one(writer_postgresql_engine, tmp_path,
                                                                         monkeypatch):
    engine = writer_postgresql_engine
    module = _module()
    voci = _setup(engine, module, monkeypatch)
    _ordine(engine, 961098, 961080, data="2026-09-29")
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    with pytest.raises(module.carica_base().Stop, match="--ordine"):
        module.run(ctx, module.Orari(BASE), voci, None, tmp_path / "bolle")
    assert not recorder.calls
    module.run(ctx, module.Orari(BASE), voci, None, tmp_path / "bolle", ordine_forzato="ORD-961098")
    ctx.conn.close()
    [righe] = recorder.fulfil
    assert {r["order_id"] for r in righe} == {"ORD-961098"}
    fulfil = next(c for c in recorder.calls if c[:2] == ["delivery", "fulfil"])
    assert fulfil[fulfil.index("--planned-date") + 1] == "2026-09-29"


@pytest.mark.parametrize("mutation, message", [
    ("UPDATE tpo.semine SET expected_useful_quantity=6 WHERE public_id='SEM-961001'", "non coincidono"),
    ("UPDATE tpo.semine SET stato='CRESCITA' WHERE public_id='SEM-961002'", "non PRONTA_ALLA_RACCOLTA"),
    ("UPDATE tpo.semine SET expected_useful_quantity=0.75 WHERE public_id='SEM-961003'", "superano gli attesi"),
    ("UPDATE tpo.stock SET disponibile=1 WHERE varieta_id=(SELECT id FROM tpo.varieta WHERE public_id='VAR-961002')",
     "giacenza"),
    ("UPDATE tpo.clienti SET denominazione='Altro locale' WHERE public_id='CLI-961001'", "Non procedo"),
])
def test_guards_stop_before_writing(writer_postgresql_engine, tmp_path, monkeypatch, mutation, message):
    engine = writer_postgresql_engine
    module = _module()
    voci = _setup(engine, module, monkeypatch)
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.exec_driver_sql(mutation)
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    with pytest.raises(module.carica_base().Stop, match=message):
        module.run(ctx, module.Orari(BASE), voci, None, tmp_path / "bolle")
    ctx.conn.close()
    assert not any(c[0] in ("raccolta", "delivery", "movimento", "semina") for c in recorder.calls)


def test_already_ready_afila_skips_the_declaration(writer_postgresql_engine, tmp_path, monkeypatch):
    engine = writer_postgresql_engine
    module = _module()
    voci = _setup(engine, module, monkeypatch)
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.exec_driver_sql("UPDATE tpo.semine SET stato='PRONTA_ALLA_RACCOLTA' WHERE public_id='SEM-961001'")
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, module.Orari(BASE), voci, None, tmp_path / "bolle")
    ctx.conn.close()
    assert not any(c[:2] == ["semina", "transition"] for c in recorder.calls)
    assert sum(1 for c in recorder.calls if c[0] == "raccolta") == 3
