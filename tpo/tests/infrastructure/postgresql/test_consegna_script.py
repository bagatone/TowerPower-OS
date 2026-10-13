"""Comando unico di consegna (12/10/2026): anteprima, semina proposta, ordine agganciato o manuale, cliente nuovo,
giorno passato, giacenza e protezioni, su PostgreSQL usa-e-getta. I comandi di scrittura passano dal CLI (gia' coperto
dai suoi test): `ctx.tpo` e' un registratore."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.infrastructure.postgresql.test_bolla_lettura_reader import _seed_carico_da_raccolta
from tests.infrastructure.postgresql.test_clandestino_script import Recorder, _connect
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    TZ, _seed,
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "commissioning" / "2026-10-12_consegna.py"
ULTIMO = datetime(2026, 10, 7, 12, 0, tzinfo=TZ)
OGGI = date(2026, 10, 12)
ADESSO = datetime(2026, 10, 12, 11, 0, tzinfo=TZ)
V1, V2, V3 = "Writer variety 961001", "Writer variety 961002", "Writer variety 961003"
CLIENTE = "Writer client 961001"


def _module():
    spec = importlib.util.spec_from_file_location("consegna_12_10", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ordine(engine, numero, riga_base, data="2026-10-13", varieta=(961001, 961002, 961003)):
    with engine.begin() as connection:
        ordine = connection.exec_driver_sql("""
          INSERT INTO tpo.ordini(public_id,cliente_id,data_ordine,data_consegna_prevista,stato,tipo_creazione,created_by)
          VALUES (%s,(SELECT id FROM tpo.clienti WHERE public_id='CLI-961001'),%s::date,%s::date,'APERTO','MANUALE',
                  'writer-test') RETURNING id""", (f"ORD-{numero}", data, data)).scalar_one()
        for pos, var in enumerate(varieta, 1):
            connection.exec_driver_sql("""
              INSERT INTO tpo.righe_ordine(ordine_id,posizione,varieta_id,quantita,unita_misura,public_id)
              VALUES (%s,%s,(SELECT id FROM tpo.varieta WHERE public_id=%s),1,'SET',%s)""",
                                       (ordine, pos, f"VAR-{var}", f"RO-{riga_base + pos}"))


def _setup(engine, monkeypatch, con_ordine=True):
    """V1: SEM-961001 in LUCE (7 SET attesi); V2: SEM-961002 e V3: SEM-961003 PRONTE (3 attesi, 0.5 raccolti)."""
    module = _module()
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
    if con_ordine:       # True = ordine vicino (13/10); "lontano" = ordine lontano (1/12), che il registratore usa come ordine manuale
        _ordine(engine, 961099, 961090, data="2026-12-01" if con_ordine == "lontano" else "2026-10-13")
    b = module.carica_base()
    monkeypatch.setattr(b, "ultimo_evento", lambda ctx, semina: ULTIMO)
    return module


def _seconda_semina_v2(engine, codice="TST-1210-X", residuo_prima="0"):
    """Seconda semina PRONTA della V2, piu' recente (FIFO: viene dopo SEM-961002)."""
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        variety_pk = connection.exec_driver_sql("SELECT id FROM tpo.varieta WHERE public_id='VAR-961002'").scalar_one()
        connection.exec_driver_sql("""
          INSERT INTO tpo.semine
            (public_id,varieta_id,cultivar_id,cultivar_uso_id,lotto_seme_id,protocollo_versione_id,stato,
             quantita_seme,unita_misura,data_avvio,causa_origine,cultivar_snapshot,uso_produttivo_snapshot,
             lotto_seme_snapshot,protocollo_snapshot,created_by,codice_tracciabilita,expected_useful_quantity,
             expected_useful_uom,harvest_window_start,harvest_window_end)
          VALUES ('SEM-961222',%s,1,1,1,1,'PRONTA_ALLA_RACCOLTA',10,'GRAM','2098-02-01','PIANO_PRODUZIONE',
                  'x','x','x','x','test',%s,4,'SET','2098-02-10','2098-02-15')""", (variety_pk, codice))
        if residuo_prima == "0":                      # la prima semina e' esaurita: 3 attesi, 3 raccolti
            connection.exec_driver_sql("UPDATE tpo.semine SET expected_useful_quantity=0.5 WHERE public_id='SEM-961002'")


def _req(module, voci, **kw):
    kw.setdefault("oggi", OGGI)
    kw.setdefault("adesso", ADESSO)
    kw.setdefault("pdf_dir", "/tmp/consegna-test-bolle")
    return module.Richiesta(CLIENTE, voci, **kw)


def _ctx(module, engine, execute, tmp_path, recorder=None):
    b = module.carica_base()
    module.WORK = tmp_path / "work"
    ctx = b.Ctx(execute, tmp_path / "bolle", conn=_connect(engine))
    ctx.check_head = lambda: None
    if recorder is not None:
        ctx.tpo = recorder
    return ctx


TRE = [f"{V1}:1", f"{V2}:0.5", f"{V3}:0.5"]


def test_preview_proposes_the_semine_and_writes_nothing(writer_postgresql_engine, tmp_path, monkeypatch, capsys):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch)
    ctx = _ctx(module, engine, False, tmp_path)
    module.run(ctx, _req(module, TRE, pronte=["SEM-961001:7"]))
    out = capsys.readouterr().out
    ctx.conn.close()
    assert "SEM-961001" in out and "PROPOSTA" in out and "SEM-961002" in out
    assert "-> CRESCITA" in out and "-> PRONTA_ALLA_RACCOLTA" in out
    assert "la consegna si lega a ORD-961099" in out
    assert "metodo NON indicato" in out and "COMANDI CORRETTIVI" in out and "anteprima: non eseguito" in out
    assert not (tmp_path / "work").exists()                       # l'anteprima non salva nulla


def test_execute_links_the_open_order_with_the_proposed_provenance(writer_postgresql_engine, tmp_path, monkeypatch):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch)
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, _req(module, TRE, pronte=["SEM-961001:7"]))
    ctx.conn.close()
    calls = recorder.calls
    assert not any(c[:2] == ["ordine", "registra-manuale"] for c in calls)
    assert not any(c[0] == "onboarding" for c in calls) and not any(c[0] == "pagamento-consegna" for c in calls)
    transitions = {c[c.index("--target-state") + 1]: c[c.index("--effective-at") + 1]
                   for c in calls if c[:2] == ["semina", "transition"]}
    assert set(transitions) == {"CRESCITA", "PRONTA_ALLA_RACCOLTA"}
    assert transitions["PRONTA_ALLA_RACCOLTA"].startswith("2026-10-12T11:00:00")
    raccolte = {c[c.index("--semina") + 1]: (c[c.index("--quantity") + 1], c[c.index("--effective-at") + 1])
                for c in calls if c[0] == "raccolta"}
    assert {s: q for s, (q, _) in raccolte.items()} == {"SEM-961001": "1", "SEM-961002": "0.5", "SEM-961003": "0.5"}
    assert all(t.startswith("2026-10-12T11:01:00") for _, t in raccolte.values())
    [righe] = recorder.fulfil
    assert [(r["order_id"], r["order_line_id"], r["quantity"], r["semina"]) for r in righe] == [
        ("ORD-961099", "RO-961091", "1", "SEM-961001"), ("ORD-961099", "RO-961092", "0.5", "SEM-961002"),
        ("ORD-961099", "RO-961093", "0.5", "SEM-961003")]
    fulfil = next(c for c in calls if c[:2] == ["delivery", "fulfil"])
    assert fulfil[fulfil.index("--planned-date") + 1] == "2026-10-12"
    assert fulfil[fulfil.index("--effective-at") + 1].startswith("2026-10-12T11:02:00")
    ordine = [" ".join(c[:2]) for c in calls]
    assert ordine.index("semina transition") < ordine.index("raccolta record") < ordine.index("delivery fulfil")
    assert sum(1 for c in calls if c[:2] == ["bolla", "genera"]) == 1
    assert (tmp_path / "work" / f"piano_{module.Richiesta(CLIENTE, TRE, oggi=OGGI).tag}.json").exists()


def test_a_semina_still_in_germination_goes_through_luce_crescita_pronta_with_administrative_times(
        writer_postgresql_engine, tmp_path, monkeypatch, capsys):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch, con_ordine="lontano")
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.exec_driver_sql("UPDATE tpo.semine SET stato='GERMINAZIONE' WHERE public_id='SEM-961001'")
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, _req(module, [f"{V1}:1"], pronte=["SEM-961001:7"]))
    ctx.conn.close()
    steps = [(c[c.index("--target-state") + 1], c[c.index("--effective-at") + 1]) for c in recorder.calls
             if c[:2] == ["semina", "transition"]]
    assert [n for n, _ in steps] == ["LUCE", "CRESCITA", "PRONTA_ALLA_RACCOLTA"]
    assert steps[0][1] < steps[1][1] < steps[2][1] and steps[2][1].startswith("2026-10-12T11:00:00")
    assert any(c[0] == "raccolta" for c in recorder.calls)


def test_fifo_skips_an_exhausted_semina_and_lists_the_alternatives(writer_postgresql_engine, tmp_path, monkeypatch,
                                                                    capsys):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch)
    _seconda_semina_v2(engine)
    ctx = _ctx(module, engine, False, tmp_path)
    module.run(ctx, _req(module, TRE, pronte=["SEM-961001:7"]))
    out = capsys.readouterr().out
    ctx.conn.close()
    assert f"{V2} 0.5: SEM-961222" in out and "PROPOSTA" in out


def test_explicit_semina_wins_and_a_not_ready_one_needs_the_declaration(writer_postgresql_engine, tmp_path,
                                                                        monkeypatch):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch)
    _seconda_semina_v2(engine, residuo_prima="1")                  # la prima ha ancora residuo, ma scelgo la seconda
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    with pytest.raises(module.carica_base().Stop, match="--pronta SEM-961001"):
        module.run(ctx, _req(module, [f"{V1}:1:SEM-961001"]))      # in LUCE e non dichiarata: si ferma
    assert not recorder.calls
    module.run(ctx, _req(module, [f"{V2}:0.5:SEM-961222", f"{V3}:0.5"]))
    ctx.conn.close()
    sem = {c[c.index("--semina") + 1] for c in recorder.calls if c[0] == "raccolta"}
    assert sem == {"SEM-961222", "SEM-961003"}


def test_without_a_covering_order_or_with_manual_flag_it_creates_a_manual_order(writer_postgresql_engine, tmp_path,
                                                                                monkeypatch):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch)
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, _req(module, TRE, pronte=["SEM-961001:7"], manuale=True))
    ctx.conn.close()
    manuale = next(c for c in recorder.calls if c[:2] == ["ordine", "registra-manuale"])
    assert manuale[manuale.index("--client") + 1] == "CLI-961001" and manuale.count("--riga") == 3


def test_an_order_far_from_the_delivery_date_is_not_linked_automatically(writer_postgresql_engine, tmp_path,
                                                                          monkeypatch, capsys):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch, con_ordine="lontano")     # come l'ordine futuro di El Callao: NON si tocca
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, _req(module, TRE, pronte=["SEM-961001:7"]))
    out = capsys.readouterr().out
    ctx.conn.close()
    assert "data lontana piu' di 3 giorni" in out and "nessun ordine aperto copre tutte le voci in data vicina" in out
    assert any(c[:2] == ["ordine", "registra-manuale"] for c in recorder.calls)


def test_two_candidate_orders_stop_before_writing_and_the_flag_picks_one(writer_postgresql_engine, tmp_path,
                                                                         monkeypatch):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch)
    _ordine(engine, 961098, 961080, data="2026-10-12")
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    with pytest.raises(module.carica_base().Stop, match="--ordine"):
        module.run(ctx, _req(module, TRE, pronte=["SEM-961001:7"]))
    assert not recorder.calls
    module.run(ctx, _req(module, TRE, pronte=["SEM-961001:7"], ordine="ORD-961098"))
    ctx.conn.close()
    [righe] = recorder.fulfil
    assert {r["order_id"] for r in righe} == {"ORD-961098"}
    fulfil = next(c for c in recorder.calls if c[:2] == ["delivery", "fulfil"])
    assert fulfil[fulfil.index("--planned-date") + 1] == "2026-10-12"


def test_repeated_order_flag_links_each_variety_to_the_first_listed_order_covering_it(writer_postgresql_engine,
                                                                                    tmp_path, monkeypatch, capsys):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch, con_ordine="lontano")      # 961099 (tutte e tre, lontano) = ordine manuale
    _ordine(engine, 961098, 961080, data="2026-10-12", varieta=(961002,))      # arretrato che copre solo V2
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, _req(module, TRE, pronte=["SEM-961001:7"], ordine=["ORD-961098"]))
    out = capsys.readouterr().out
    ctx.conn.close()
    assert "le altre voci" in out and V1 in out
    [righe] = recorder.fulfil
    per_ordine = {}
    for r in righe:
        per_ordine.setdefault(r["order_id"], []).append(r["quantity"])
    assert sorted(per_ordine) == ["ORD-961098", "ORD-961099"] and per_ordine["ORD-961098"] == ["0.5"]
    assert any(c[:2] == ["ordine", "registra-manuale"] for c in recorder.calls)
    fulfil = next(c for c in recorder.calls if c[:2] == ["delivery", "fulfil"])
    assert fulfil[fulfil.index("--planned-date") + 1] == "2026-10-12"


def test_two_order_flags_split_the_lines_between_two_open_orders_without_a_manual_order(writer_postgresql_engine,
                                                                                        tmp_path, monkeypatch):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch)                            # 961099 vicino, tutte e tre le varieta'
    _ordine(engine, 961098, 961080, data="2026-10-12", varieta=(961002,))
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, _req(module, TRE, pronte=["SEM-961001:7"], ordine=["ORD-961098", "ORD-961099"]))
    ctx.conn.close()
    [righe] = recorder.fulfil
    assert sorted((r["order_id"], r["quantity"]) for r in righe) == [
        ("ORD-961098", "0.5"), ("ORD-961099", "0.5"), ("ORD-961099", "1")]
    assert not any(c[:2] == ["ordine", "registra-manuale"] for c in recorder.calls)


def test_a_past_day_needs_the_hour_and_marks_the_times_as_estimated(writer_postgresql_engine, tmp_path, monkeypatch):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch, con_ordine="lontano")
    with pytest.raises(module.carica_base().Stop, match="--ora"):
        _req(module, [f"{V2}:0.5"], giorno=date(2026, 10, 10))
    with pytest.raises(module.carica_base().Stop, match="futuro"):
        _req(module, [f"{V2}:0.5"], giorno=date(2026, 10, 13))
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, _req(module, [f"{V2}:0.5"], giorno=date(2026, 10, 10), ora="09:50"))
    ctx.conn.close()
    racc = next(c for c in recorder.calls if c[0] == "raccolta")
    assert racc[racc.index("--effective-at") + 1].startswith("2026-10-10T09:51:00")
    assert "orario stimato" in racc[racc.index("--notes") + 1]
    fulfil = next(c for c in recorder.calls if c[:2] == ["delivery", "fulfil"])
    assert fulfil[fulfil.index("--planned-date") + 1] == "2026-10-10"
    assert fulfil[fulfil.index("--effective-at") + 1].startswith("2026-10-10T09:52:00")


def test_unknown_customer_is_an_error_and_a_new_one_needs_the_flag_and_no_lookalike(writer_postgresql_engine,
                                                                                    tmp_path, monkeypatch):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch, con_ordine=False)
    b = module.carica_base()
    ctx = _ctx(module, engine, False, tmp_path)
    with pytest.raises(b.Stop, match="--nuovo-cliente"):
        module.run(ctx, module.Richiesta("Clandestino", [f"{V2}:0.5"], oggi=OGGI, adesso=ADESSO))
    with pytest.raises(b.Stop, match="nome simile"):
        module.run(ctx, module.Richiesta("Writer client 961002x", [f"{V2}:0.5"], oggi=OGGI, adesso=ADESSO,
                                         nuovo_cliente=True))
    ctx.conn.close()


def test_new_customer_is_created_once_with_its_programme(writer_postgresql_engine, tmp_path, monkeypatch):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch)
    seen = []
    monkeypatch.setattr(module, "carica_programma", lambda: SimpleNamespace(
        run=lambda conn, cliente, righe, prima, ogni, motivo, esegui: seen.append((cliente, righe, prima, ogni, esegui)) or 0))
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    req = module.Richiesta("Clandestino", [f"{V2}:0.5"], oggi=OGGI, adesso=ADESSO, nuovo_cliente=True,
                           programma_righe=[f"{V2}:1"], programma_prima=date(2026, 10, 15), programma_ogni=7,
                           pdf_dir="/tmp/consegna-test-bolle")
    module.run(ctx, req)
    ctx.conn.close()
    cliente = next(c for c in recorder.calls if c[0] == "onboarding")
    assert cliente[cliente.index("--denomination") + 1] == "Clandestino"
    assert cliente[cliente.index("--customer-id") + 1].startswith("CLI-96")
    assert seen == [("Clandestino", [f"{V2}:1"], date(2026, 10, 15), 7, True)]
    manuale = next(c for c in recorder.calls if c[:2] == ["ordine", "registra-manuale"])
    assert manuale[manuale.index("--client") + 1] == cliente[cliente.index("--customer-id") + 1]


def test_giacenza_line_has_no_harvest_and_no_provenance_and_needs_enough_stock(writer_postgresql_engine, tmp_path,
                                                                                monkeypatch):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE tpo.stock SET disponibile=1 WHERE varieta_id="
                                   "(SELECT id FROM tpo.varieta WHERE public_id='VAR-961002')")
    b = module.carica_base()
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    with pytest.raises(b.Stop, match="giacenza 1 SET"):            # senza --da-giacenza: giacenza != 0 prima del carico
        module.run(ctx, _req(module, [f"{V2}:0.5"]))
    with pytest.raises(b.Stop, match="< 2"):
        module.run(ctx, _req(module, [f"{V2}:2"], da_giacenza=[V2]))
    assert not recorder.calls
    module.run(ctx, _req(module, [f"{V2}:0.5", f"{V3}:0.5"], da_giacenza=[V2]))
    ctx.conn.close()
    assert {c[c.index("--semina") + 1] for c in recorder.calls if c[0] == "raccolta"} == {"SEM-961003"}
    [righe] = recorder.fulfil
    assert {r["order_line_id"]: ("semina" in r) for r in righe} == {"RO-961092": False, "RO-961093": True}


def test_payment_only_with_an_explicit_method(writer_postgresql_engine, tmp_path, monkeypatch):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch)
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    module.run(ctx, _req(module, TRE, pronte=["SEM-961001:7"], metodo="CONTANTI"))
    ctx.conn.close()
    pagamento = next(c for c in recorder.calls if c[0] == "pagamento-consegna")
    assert pagamento[pagamento.index("--metodo") + 1] == "CONTANTI"
    assert pagamento[pagamento.index("--data") + 1] == "2026-10-12" and "--storico" not in pagamento
    bolle = [c for c in recorder.calls if c[:2] == ["bolla", "genera"]]
    assert len(bolle) == 2 and "--sovrascrivi" in bolle[1]


@pytest.mark.parametrize("mutation, message", [
    ("UPDATE tpo.semine SET expected_useful_quantity=6 WHERE public_id='SEM-961001'", "non coincidono"),
    ("UPDATE tpo.semine SET stato='CRESCITA' WHERE public_id='SEM-961002'", "nessuna semina PRONTA"),
    ("UPDATE tpo.stock SET disponibile=1 WHERE varieta_id=(SELECT id FROM tpo.varieta WHERE public_id='VAR-961003')",
     "giacenza"),
])
def test_guards_stop_before_writing(writer_postgresql_engine, tmp_path, monkeypatch, mutation, message):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch)
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.exec_driver_sql(mutation)
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    with pytest.raises(module.carica_base().Stop, match=message):
        module.run(ctx, _req(module, TRE, pronte=["SEM-961001:7"]))
    ctx.conn.close()
    assert not any(c[0] in ("raccolta", "delivery", "movimento", "semina") for c in recorder.calls)


def test_over_expected_needs_the_explicit_flag(writer_postgresql_engine, tmp_path, monkeypatch):
    engine = writer_postgresql_engine
    module = _setup(engine, monkeypatch, con_ordine="lontano")
    b = module.carica_base()
    recorder = Recorder(engine)
    ctx = _ctx(module, engine, True, tmp_path, recorder)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE tpo.semine SET expected_useful_quantity=0.75 WHERE public_id='SEM-961003'")
    with pytest.raises(b.Stop, match="nessuna semina"):             # la proposta automatica non va oltre gli attesi
        module.run(ctx, _req(module, [f"{V3}:0.5"]))
    with pytest.raises(b.Stop, match="oltre-attesi"):
        module.run(ctx, _req(module, [f"{V3}:0.5:SEM-961003"]))
    module.run(ctx, _req(module, [f"{V3}:0.5:SEM-961003"], oltre_attesi=True))
    ctx.conn.close()
    racc = next(c for c in recorder.calls if c[0] == "raccolta")
    assert "oltre i 0.75 SET attesi" in racc[racc.index("--notes") + 1]


@pytest.mark.parametrize("voci, message", [
    ([f"{V1}:0.3"], "interi o mezzi"),
    ([f"{V1}:1", f"{V1}:1"], "ripetuta"),
    (["solo-nome"], "non valida"),
    ([f"{V1}:1:SEM-1"], "semina"),
    ([f"{V1}:0"], "interi o mezzi"),
])
def test_request_validation(writer_postgresql_engine, voci, message):
    module = _module()
    with pytest.raises(module.carica_base().Stop, match=message):
        module.Richiesta(CLIENTE, voci, oggi=OGGI, adesso=ADESSO)


def test_same_request_has_the_same_key_and_a_replica_gets_another():
    module = _module()
    a = module.Richiesta("La Jaira", ["Afila:1", "Cilantro:0.5"], oggi=OGGI)
    b = module.Richiesta("la jaira", ["Cilantro:0.5", "Afila:1:SEM-000021"], oggi=OGGI)
    c = module.Richiesta("La Jaira", ["Afila:1", "Cilantro:0.5"], oggi=OGGI, replica=2)
    assert a.tag == b.tag and c.tag == a.tag + "-r2"
    assert module.Richiesta("La Jaira", ["Afila:1", "Cilantro:1"], oggi=OGGI).tag != a.tag
