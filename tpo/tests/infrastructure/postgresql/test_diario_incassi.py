"""Incassi nel diario (16/10/2026): elenco "da incassare" e pagamento con conferma, su PostgreSQL usa-e-getta.
Il runner dell'adapter CLI e' un doppio: qui si verifica cosa il diario CHIEDE di scrivere, non il dominio dei pagamenti
(gia' coperto dai suoi test)."""
from __future__ import annotations

from datetime import date

import pytest

from src.tpo_core.diario_web import db_context, incassi
from tests.infrastructure.postgresql.test_da_incassare_script import _consegna, _paga
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)
from tests.infrastructure.postgresql.test_sposta_giorno_programma_script import _connect

OGGI = date(2099, 1, 11)            # le consegne dei test sono del 2099-01-01
SETTINGS = object()                 # db_context._connect e' sostituito: i settings non servono


@pytest.fixture
def db(writer_postgresql_engine, monkeypatch):
    engine = writer_postgresql_engine
    monkeypatch.setattr(db_context, "_connect", lambda settings: _connect(engine))
    return engine


class Runner:
    def __init__(self, fallisci_su=None):
        self.calls, self.fallisci_su = [], fallisci_su

    def __call__(self, args, *, stdout, stderr):
        self.calls.append(args)
        if args.consegna == self.fallisci_su:
            stderr.write("PAGAMENTO_CONSEGNA_FAILED: SIMULATO: no\n")
            return 5
        stdout.write(f"PAGAMENTO_CONSEGNA_ID=PGC-{len(self.calls):06d}\nOUTCOME=INSERTED\n")
        return 0


def _cliente(elenco, nome):
    return next(c for c in elenco if c.cliente_nome == nome)


def test_lists_unpaid_with_age_and_voci_and_excludes_paid(db):
    _consegna(db, 974001, quantita="0.5")
    _consegna(db, 974002)
    _paga(db, 974002)
    elenco = incassi.da_incassare(SETTINGS, OGGI)
    c = _cliente(elenco, "Writer client 974001")
    assert c.cliente_public_id == "CLI-974001"
    assert [(x.codice, x.data, x.giorni, x.voci) for x in c.consegne] == [
        ("CON-974001", "2099-01-01", 10, ["Writer variety 974001 0.5 SET"])]
    assert not any(x.cliente_nome == "Writer client 974002" for x in elenco)
    _paga(db, 974002, tipo="ANNULLAMENTO", annulla="PGC-974002")                 # annullato: torna da incassare
    assert _cliente(incassi.da_incassare(SETTINGS, OGGI), "Writer client 974002").consegne[0].codice == "CON-974002"


def test_proposal_never_guesses_the_method_and_checks_everything(db):
    _consegna(db, 974011)
    _consegna(db, 974012)
    _consegna(db, 974013)
    _paga(db, 974013)
    casi = (
        (["CON-974011"], None, "Manca il metodo"),
        (["CON-974011"], "assegno", "non valido"),
        (["CON-974011"], "CONTANTI", None),
        (["CON-999999"], "CONTANTI", "inesistenti"),
        (["CON-974013"], "CONTANTI", "Gia' pagate: CON-974013"),
        (["CON-974011", "CON-974012"], "CONTANTI", "clienti diversi"),
        ([], "CONTANTI", "Nessuna consegna"),
    )
    for codici, metodo, frase in casi:
        if frase is None:
            p = incassi.prepara_pagamento(SETTINGS, codici, metodo, oggi=OGGI)
            assert (p.cliente_nome, p.metodo, p.data_pagamento, p.importo) == (
                "Writer client 974011", "CONTANTI", "2099-01-11", None)
            assert p.consegne == [{"codice": "CON-974011", "data": "2099-01-01",
                                   "voci": ["Writer variety 974011 0.5 SET"]}]
            continue
        with pytest.raises(incassi.PagamentoNonPossibile, match=frase):
            incassi.prepara_pagamento(SETTINGS, codici, metodo, oggi=OGGI)


def test_proposal_date_and_amount_rules(db):
    _consegna(db, 974021)
    with pytest.raises(incassi.PagamentoNonPossibile, match="nel futuro"):
        incassi.prepara_pagamento(SETTINGS, ["CON-974021"], "CONTANTI", "2099-02-01", oggi=OGGI)
    with pytest.raises(incassi.PagamentoNonPossibile, match="dopo la data di pagamento"):
        incassi.prepara_pagamento(SETTINGS, ["CON-974021"], "CONTANTI", "2098-12-31", oggi=OGGI)
    with pytest.raises(incassi.PagamentoNonPossibile, match="non valida"):
        incassi.prepara_pagamento(SETTINGS, ["CON-974021"], "CONTANTI", "ieri", oggi=OGGI)
    with pytest.raises(incassi.PagamentoNonPossibile, match="Importo"):
        incassi.prepara_pagamento(SETTINGS, ["CON-974021"], "CONTANTI", importo="abc", oggi=OGGI)
    p = incassi.prepara_pagamento(SETTINGS, ["con-974021"], "contanti", "2099-01-05", "12.50", oggi=OGGI)
    assert (p.data_pagamento, p.importo, p.metodo) == ("2099-01-05", "12.50", "CONTANTI")


def test_execute_builds_the_cli_command_and_points_to_the_pdf_regeneration(db):
    _consegna(db, 974031)
    p = incassi.prepara_pagamento(SETTINGS, ["CON-974031"], "BONIFICO", oggi=OGGI)
    runner = Runner()
    testo = incassi.esegui_pagamento(SETTINGS, p, "giulia@towerpower", runner=runner)
    a = runner.calls[0]
    assert (a.pagamento_consegna_command, a.consegna, a.data, a.metodo, a.importo, a.storico) == (
        "registra", "CON-974031", "2099-01-11", "BONIFICO", None, False)
    assert a.actor == "giulia@towerpower" and "tramite il diario" in a.reason
    assert a.idempotency_key == a.correlation_id == "diario-pagamento-con-974031-n1"
    assert "CON-974031: pagamento PGC-000001 registrato (BONIFICO, 2099-01-11)" in testo
    assert "scripts/commissioning/2026-10-11_pagamenti_consegne.py --pagata CON-974031 --metodo BONIFICO --esegui" in testo


def test_execute_rereads_the_attempt_number_after_a_cancelled_payment(db):
    _consegna(db, 974041)
    _paga(db, 974041)
    _paga(db, 974041, tipo="ANNULLAMENTO", annulla="PGC-974041")
    p = incassi.prepara_pagamento(SETTINGS, ["CON-974041"], "CARTA", oggi=OGGI)
    runner = Runner()
    incassi.esegui_pagamento(SETTINGS, p, "giulia@towerpower", runner=runner)
    assert runner.calls[0].idempotency_key == "diario-pagamento-con-974041-n2"        # 1 pagamento gia' registrato


def test_execute_skips_what_was_paid_in_the_meantime(db):
    _consegna(db, 974051)
    p = incassi.prepara_pagamento(SETTINGS, ["CON-974051"], "CONTANTI", oggi=OGGI)
    _paga(db, 974051)                                  # un altro telefono ha registrato prima di noi
    runner = Runner()
    testo = incassi.esegui_pagamento(SETTINGS, p, "giulia@towerpower", runner=runner)
    assert runner.calls == [] and "gia' pagata, saltata" in testo and "bolle PDF" not in testo


def test_execute_stops_at_the_first_failure_and_says_what_was_done(db):
    _consegna(db, 974061)
    _consegna(db, 974062)
    p = incassi.PropostaPagamento(
        consegne=[{"codice": "CON-974061", "data": "2099-01-01", "voci": []},
                  {"codice": "CON-974062", "data": "2099-01-01", "voci": []}],
        cliente_nome="x", metodo="CONTANTI", data_pagamento="2099-01-11", importo=None)
    runner = Runner(fallisci_su="CON-974062")
    with pytest.raises(incassi.PagamentoFallito) as errore:
        incassi.esegui_pagamento(SETTINGS, p, "giulia@towerpower", runner=runner)
    testo = str(errore.value)
    assert "CON-974061: pagamento" in testo and "POI: CON-974062: PAGAMENTO_CONSEGNA_FAILED" in testo
    runner = Runner(fallisci_su="CON-974061")
    with pytest.raises(incassi.PagamentoFallito, match="Nulla e' stato registrato"):
        incassi.esegui_pagamento(SETTINGS, p, "giulia@towerpower", runner=runner)


def test_execute_refuses_a_delivery_not_made(db):
    p = incassi.PropostaPagamento(
        consegne=[{"codice": "CON-999999", "data": "", "voci": []}], cliente_nome="x", metodo="CONTANTI",
        data_pagamento="2099-01-11", importo=None)
    runner = Runner()
    with pytest.raises(incassi.PagamentoFallito, match="non e' una consegna effettuata"):
        incassi.esegui_pagamento(SETTINGS, p, "giulia@towerpower", runner=runner)
    assert runner.calls == []
