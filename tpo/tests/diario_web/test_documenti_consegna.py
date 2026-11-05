"""Bolla ed etichette scaricabili dal diario (5/11/2026): sola lettura, senza database. Si verifica che le rotte
chiedano la password, che i PDF arrivino con nome e tipo giusti, che 'senza prezzi' tolga prezzi e totale solo da
quel PDF, che l'intestazione venga dalla variabile segreta (o dal file, o da nessuno) e che gli errori siano leggibili."""
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.tpo_core.application.bolla_lettura import Bolla, OrigineLotto, RigaBolla
from src.tpo_core.diario_web import app as app_module, documenti_consegna as doc
from src.tpo_core.domain.identifiers import ConsegnaId

pytest.importorskip("reportlab")

AUTH = ("matteo", "segreta")
NOW = datetime(2099, 1, 1, 10, tzinfo=timezone.utc)


def _bolla(con_prezzi: bool = False) -> Bolla:
    riga = RigaBolla(1, "ORD-000001", "VAR-000001", "Rábano", Decimal("2"), "SET", False,
                     (OrigineLotto("RAB-0210-A", "RAC-000001", NOW, Decimal("2")),), Decimal("0"),
                     prezzo_unitario=Decimal("12.50") if con_prezzi else None)
    return Bolla(ConsegnaId("CON-000012"), "CONSEGNATA", "CLI-000003", "Azul y Sal Ñ",
                 date(2099, 1, 1), NOW, None, None, (riga,))


def _client(monkeypatch):
    monkeypatch.setenv("DIARIO_PASSWORD", "segreta")
    monkeypatch.setattr(app_module, "_settings", lambda: object())
    return TestClient(app_module.app)


def test_le_rotte_documenti_chiedono_la_password(monkeypatch):
    client = _client(monkeypatch)
    assert client.get("/api/consegne-recenti").status_code == 401
    assert client.get("/api/consegna/CON-000012/bolla.pdf").status_code == 401
    assert client.get("/api/consegna/CON-000012/etichette.pdf").status_code == 401


def test_bolla_pdf_arriva_con_nome_e_tipo(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(doc, "_leggi_bolla", lambda settings, codice: _bolla())
    monkeypatch.setattr(doc, "emittente", lambda: ("Tower Power (prova)",))
    r = client.get("/api/consegna/CON-000012/bolla.pdf", auth=AUTH)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")
    assert "bolla_CON-000012_azul-y-sal-n_2099-01-01.pdf" in r.headers["content-disposition"]


def test_senza_prezzi_toglie_prezzi_e_totale_solo_da_quel_pdf(monkeypatch):
    import src.tpo_core.infrastructure.pdf.bolla_pdf as pdf_module
    visti = []
    originale = pdf_module.render_bolla_pdf
    monkeypatch.setattr(pdf_module, "render_bolla_pdf", lambda bolla, **kw: (visti.append(bolla), originale(bolla, **kw))[1])
    monkeypatch.setattr(doc, "_leggi_bolla", lambda settings, codice: _bolla(con_prezzi=True))
    monkeypatch.setattr(doc, "emittente", lambda: ())
    doc.bolla_pdf(object(), "CON-000012")
    doc.bolla_pdf(object(), "CON-000012", senza_prezzi=True)
    assert visti[0].ha_prezzi and visti[0].totale == Decimal("25.00")
    assert not visti[1].ha_prezzi and visti[1].totale is None


def test_etichette_pdf_foglio_e_pagina_singola(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(doc, "_leggi_bolla", lambda settings, codice: _bolla())
    foglio = client.get("/api/consegna/CON-000012/etichette.pdf", auth=AUTH)
    assert foglio.status_code == 200 and foglio.content.startswith(b"%PDF-")
    assert "etichette_CON-000012_azul-y-sal-n_2099-01-01_foglio.pdf" in foglio.headers["content-disposition"]
    singole = client.get("/api/consegna/CON-000012/etichette.pdf?foglio=false", auth=AUTH)
    assert singole.status_code == 200
    assert "_foglio" not in singole.headers["content-disposition"]


def test_errori_leggibili(monkeypatch):
    client = _client(monkeypatch)

    def non_possibile(settings, codice):
        raise doc.DocumentoNonPossibile("La CONSEGNA CON-000099 non esiste.")

    monkeypatch.setattr(doc, "_leggi_bolla", non_possibile)
    r = client.get("/api/consegna/CON-000099/bolla.pdf", auth=AUTH)
    assert r.status_code == 404 and "non esiste" in r.json()["errore"]
    r = client.get("/api/consegna/CON-000099/etichette.pdf", auth=AUTH)
    assert r.status_code == 404 and "non esiste" in r.json()["errore"]


def test_etichette_senza_origine_tracciata_e_un_errore_leggibile(monkeypatch):
    base = _bolla()
    senza_lotto = replace(base, righe=tuple(replace(r, origini=(), quantita_senza_origine=r.quantita) for r in base.righe))
    monkeypatch.setattr(doc, "_leggi_bolla", lambda settings, codice: senza_lotto)
    with pytest.raises(doc.DocumentoNonPossibile):
        doc.etichette_pdf(object(), "CON-000012")


def test_consegne_recenti_rotta(monkeypatch):
    client = _client(monkeypatch)
    elenco = [doc.ConsegnaRecente("CON-000012", "Azul y Sal", "2026-11-05", ["Rábano 2 SET"], False)]
    monkeypatch.setattr(doc, "consegne_recenti", lambda settings, giorni=14: elenco)
    dati = client.get("/api/consegne-recenti", auth=AUTH).json()
    assert dati["consegne"] == [{"codice": "CON-000012", "cliente": "Azul y Sal", "data": "2026-11-05",
                                 "voci": ["Rábano 2 SET"], "pagata": False}]


def test_intestazione_da_variabile_segreta_yaml_o_righe(monkeypatch):
    monkeypatch.setenv(doc.ENV_EMITTENTE, "righe:\n  - Tower Power\n  - Calle Prova 1\n")
    assert doc.emittente() == ("Tower Power", "Calle Prova 1")
    monkeypatch.setenv(doc.ENV_EMITTENTE, "Tower Power\nNIF: X1234\n\nCalle Prova 1")
    assert doc.emittente() == ("Tower Power", "NIF: X1234", "Calle Prova 1")


def test_intestazione_dal_file_o_nessuna(monkeypatch, tmp_path):
    monkeypatch.delenv(doc.ENV_EMITTENTE, raising=False)
    file = tmp_path / "bolla_emittente.yaml"
    file.write_text("righe:\n  - Tower Power (file)\n", encoding="utf-8")
    monkeypatch.setattr(doc, "DEFAULT_EMITTENTE_FILE", file)
    assert doc.emittente() == ("Tower Power (file)",)
    monkeypatch.setattr(doc, "DEFAULT_EMITTENTE_FILE", tmp_path / "manca.yaml")
    assert doc.emittente() == ()
