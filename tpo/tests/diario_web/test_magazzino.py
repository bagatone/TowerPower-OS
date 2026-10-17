"""Schermata Magazzino del diario (17/10/2026): dati di sola lettura per la pagina + navigazione a 4 schermate.
I numeri devono coincidere con quelli degli script inventario e semine_in_corso."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from src.tpo_core.diario_web import app as app_module, magazzino

AUTH = ("matteo", "segreta")
ADESSO = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)

LOTTI = [
    ("LSE-000002", "Intersemillas", "Rucola coltivata", "L-2", date(2026, 9, 20), None,
     Decimal("100.000"), Decimal("40.500"), "GRAM", None, "Rucola"),
    ("LSE-000001", "Intersemillas", "Rucola coltivata", "L-1", date(2026, 9, 1), date(2026, 12, 31),
     Decimal("200"), Decimal("159.5"), "GRAM", "umido", "Rucola, Senape"),
    ("LSE-000003", "Semillas Ya", "Afila", "A-1", date(2026, 9, 5), None, Decimal("50"), Decimal("50"), "GRAM", None, ""),
]
ARTICOLI = [
    ("ART-000001", "Substrato fibra di cocco", "UNIT", Decimal("2740"), datetime(2026, 10, 10, 8, tzinfo=timezone.utc)),
    ("ART-000002", "Vaschette", "UNIT", Decimal("2746"), datetime(2026, 10, 12, 8, tzinfo=timezone.utc)),
    ("ART-000003", "Guanti", "UNIT", Decimal("10"), None),
]
D = datetime(2026, 10, 14, 10, tzinfo=timezone.utc)
SEMINE = [  # id, codice, varieta, stato, avvio, atteso, uom, raccolto
    ("SEM-000001", "AFI-1", "Afila", "GERMINAZIONE", D, Decimal("2"), "SET", Decimal(0)),
    ("SEM-000002", "RUC-1", "Rucola", "LUCE", D, Decimal("3"), "SET", Decimal(0)),
    ("SEM-000003", "RUC-2", "Rucola", "CRESCITA", D, Decimal("1.5"), "SET", Decimal("0.5")),
    ("SEM-000004", "MIZ-1", "Mizuna", "PRONTA_ALLA_RACCOLTA", D, Decimal("4"), "SET", Decimal("2")),
    ("SEM-000005", "CIL-1", "Cilantro", "AVVIATA", D, Decimal("1"), "SET", Decimal(0)),
    ("SEM-000006", None, "Basilico", "CRESCITA", D, None, None, Decimal(0)),
    ("SEM-000007", "TF-1", "Lattuga", "LUCE", D, Decimal("10"), "GRAM", Decimal(0)),  # non e' in SET: non si conta
]


def _dati():
    return magazzino.componi(LOTTI, ARTICOLI, SEMINE, ADESSO)


def test_coltivazione_conta_i_set_come_lo_script_semine_in_corso() -> None:
    c = _dati()["coltivazione"]
    assert c["in_semina"] == {"set": "6.5", "semine": 5}   # 2 + 3 + 1.5, due senza SET non contate
    per_stadio = {s["stadio"]: (s["set"], s["semine"]) for s in c["stadi"]}
    assert per_stadio == {"AVVIATA": ("1", 1), "GERMINAZIONE": ("2", 1), "LUCE": ("3", 2),
                          "CRESCITA": ("1.5", 2), "PRONTA_ALLA_RACCOLTA": ("4", 1)}
    assert c["senza_set"] == ["SEM-000006", "SEM-000007"]
    assert c["per_varieta"] == [{"varieta": "Afila", "set": "2"}, {"varieta": "Rucola", "set": "4.5"}]
    pronta = c["stadi"][4]["elenco"][0]
    assert pronta["raccolto"] == "2" and pronta["codice"] == "MIZ-1" and pronta["avvio"] == "2026-10-14"
    assert c["stadi"][5 - 5]["elenco"][0]["raccolto"] is None
    assert [x["codice"] for x in c["stadi"][3]["elenco"]] == ["RUC-2", "senza codice"]


def test_semi_raggruppati_per_referenza_con_residuo_totale() -> None:
    s = _dati()["semi"]
    assert s["totale_g"] == "250" and s["lotti"] == 3
    assert [g["referenza"] for g in s["referenze"]] == ["Afila", "Rucola coltivata"]
    rucola = s["referenze"][1]
    assert rucola["residuo"] == "200" and len(rucola["lotti"]) == 2
    primo = rucola["lotti"][0]
    assert primo["iniziale"] == "100" and primo["residuo"] == "40.5" and primo["scadenza"] is None
    assert primo["seminato_per"] == ["Rucola"] and primo["anomalia"] is None
    assert rucola["lotti"][1]["anomalia"] == "umido" and rucola["lotti"][1]["scadenza"] == "2026-12-31"
    assert rucola["lotti"][1]["seminato_per"] == ["Rucola", "Senape"]
    assert s["referenze"][0]["lotti"][0]["seminato_per"] == []


def test_materiali_bastano_per_quanti_set() -> None:
    m = _dati()["materiali"]
    per_nome = {a["nome"]: a for a in m["articoli"]}
    assert m["pezzi_per_set"] == 4
    assert per_nome["Vaschette"]["set_possibili"] == "686"            # 2746 // 4
    assert per_nome["Substrato fibra di cocco"]["set_possibili"] == "685"
    assert per_nome["Guanti"]["set_possibili"] is None
    assert m["set_possibili"] == "685"                                  # il minimo: limita il piu' scarso
    assert per_nome["Guanti"]["ultimo_movimento"] is None and per_nome["Vaschette"]["ultimo_movimento"] == "2026-10-12"


def test_senza_dati_la_pagina_riceve_elenchi_vuoti_non_errori() -> None:
    d = magazzino.componi([], [], [], ADESSO)
    assert d["semi"] == {"totale_g": "0", "lotti": 0, "referenze": []}
    assert d["materiali"]["articoli"] == [] and d["materiali"]["set_possibili"] is None
    assert d["coltivazione"]["in_semina"] == {"set": "0", "semine": 0}
    assert [s["semine"] for s in d["coltivazione"]["stadi"]] == [0, 0, 0, 0, 0]


def _client(monkeypatch):
    monkeypatch.setenv("DIARIO_PASSWORD", "segreta")
    monkeypatch.setattr(app_module, "_settings", lambda: object())
    return TestClient(app_module.app)


def test_route_magazzino_richiede_la_password_e_restituisce_i_dati(monkeypatch) -> None:
    client = _client(monkeypatch)
    assert client.get("/api/magazzino").status_code == 401
    monkeypatch.setattr(magazzino, "leggi", lambda settings: _dati())
    dati = client.get("/api/magazzino", auth=AUTH).json()
    assert dati["coltivazione"]["in_semina"]["set"] == "6.5" and dati["semi"]["totale_g"] == "250"


def test_route_magazzino_errore_leggibile_se_il_database_non_risponde(monkeypatch) -> None:
    client = _client(monkeypatch)

    def giu(settings):
        raise RuntimeError("database spento")

    monkeypatch.setattr(magazzino, "leggi", giu)
    r = client.get("/api/magazzino", auth=AUTH)
    assert r.status_code == 503 and "database spento" in r.json()["errore"]


def test_la_pagina_ha_le_quattro_schermate_e_mantiene_le_sezioni_di_prima(monkeypatch) -> None:
    html = _client(monkeypatch).get("/", auth=AUTH).text
    for vista in ("oggi", "incassi", "semine", "magazzino"):
        assert f'id="vista-{vista}"' in html and f'href="#{vista}"' in html
    for vecchio in ('id="rendiconto"', 'id="incassi"', 'id="semine"', 'id="testo"', 'id="btnInterpreta"', 'id="risultati"'):
        assert html.count(vecchio) == 1
    assert "/api/magazzino" in html


def test_il_modulo_non_scrive_niente() -> None:
    sorgente = open(magazzino.__file__, encoding="utf-8").read().upper()
    for vietato in ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "DROP ", "ALTER "):
        assert vietato not in sorgente.replace("DATA_MOVIMENTO", "")
