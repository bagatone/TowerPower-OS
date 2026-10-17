"""Schermata Magazzino del diario (17/10/2026) su PostgreSQL usa-e-getta: le stesse query degli script inventario e
semine in corso, in sola lettura, con gli stessi numeri."""
from __future__ import annotations

from tests.infrastructure.postgresql.test_chiusura_guidata_script import _semina
from tests.infrastructure.postgresql.test_delivery_fulfilment_writer import (  # noqa: F401
    migration_postgresql, writer_postgresql_cluster_engine, writer_postgresql_engine,
)
from tests.infrastructure.postgresql.test_inventario_script import _connect, _seed

from src.tpo_core.diario_web import db_context, magazzino


def test_legge_semi_materiali_e_semine_in_sola_lettura(writer_postgresql_engine, monkeypatch):
    engine = writer_postgresql_engine
    _seed(engine)
    _semina(engine, 975001, "TST-1710-A", raccolto="0.5", atteso="2", stato="GERMINAZIONE")
    _semina(engine, 975002, "TST-1710-B", raccolto="0.5", atteso="3", stato="CRESCITA")
    _semina(engine, 975003, "TST-1710-C", raccolto="2", atteso="4", stato="PRONTA_ALLA_RACCOLTA")
    aperte = []

    def connessione(settings):
        aperte.append(_connect(engine))
        return aperte[-1]

    monkeypatch.setattr(db_context, "_connect", connessione)
    dati = magazzino.leggi(object())

    assert dati["semi"]["totale_g"] == "40.5" and dati["semi"]["referenze"][0]["referenza"] == "Rucola coltivata"
    lotto = dati["semi"]["referenze"][0]["lotti"][0]
    assert lotto["lotto"] == "LSE-990001" and lotto["iniziale"] == "100" and lotto["anomalia"] == "umido"
    per_nome = {a["nome"]: a for a in dati["materiali"]["articoli"]}
    assert per_nome["Vaschette"]["set_possibili"] == "686" and per_nome["Guanti"]["set_possibili"] is None
    assert dati["materiali"]["set_possibili"] == "685"
    c = dati["coltivazione"]
    assert c["in_semina"] == {"set": "5", "semine": 2}
    assert {s["stadio"]: s["set"] for s in c["stadi"]}["PRONTA_ALLA_RACCOLTA"] == "4"
    assert aperte[0].read_only is True        # la connessione del diario non puo' scrivere
