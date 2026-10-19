"""Promemoria degli stadi e controllo anomalie del diario (19/10/2026): funzioni pure + pagina, tutto in sola lettura."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from src.tpo_core.diario_web import app as app_module, controlli

AUTH = ("matteo", "segreta")
# 19/10/2026 11:00 Canarie (UTC+1)
ADESSO = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)


def _d(giorno: int, ora: int = 9) -> datetime:
    return datetime(2026, 10, giorno, ora, tzinfo=timezone.utc)


def _s(pid, varieta, stato, avvio, germ, luce, atteso="1", luce_at=None, codice=None):
    return (pid, codice or f"C-{pid[-2:]}", varieta, stato, avvio, Decimal(atteso) if atteso else None,
            "SET" if atteso else None, germ, luce, 0, luce_at)


def _comp(semine=(), clienti=(), lotti=()):
    return controlli.componi(list(semine), list(clienti), list(lotti), ADESSO)


def test_germinazione_passa_a_luce_oggi_domani_e_in_ritardo() -> None:
    semine = [
        _s("SEM-01", "Hinojo", "GERMINAZIONE", _d(15), 4, 20, "1"),      # 15+4 = 19  -> oggi
        _s("SEM-02", "Mizuna", "AVVIATA", _d(16), 4, 15, "2"),           # 20 -> domani
        _s("SEM-03", "Basilico", "GERMINAZIONE", _d(14), 4, 13, "1.5"),  # 18 -> in ritardo di 1
        _s("SEM-04", "Afila", "GERMINAZIONE", _d(18), 4, 10, "4"),       # 22 -> niente
    ]
    p = _comp(semine)["promemoria"]
    assert [(v["varieta"], v["set"], v["azione"]) for v in p["oggi"]] == [("Hinojo", "1", "luce")]
    assert [v["varieta"] for v in p["domani"]] == ["Mizuna"]
    assert [(v["varieta"], v["giorni"]) for v in p["in_ritardo"]] == [("Basilico", 1)]
    assert _comp(semine)["anomalie"] == []


def test_luce_diventa_pronta_dalla_data_del_passaggio_a_luce() -> None:
    semine = [
        _s("SEM-01", "Afila", "LUCE", _d(5), 4, 10, "6", luce_at=_d(9)),     # 9+10 = 19 -> oggi
        _s("SEM-02", "Rucola", "CRESCITA", _d(5), 4, 10, "2", luce_at=_d(10)),  # 20 -> domani
        _s("SEM-03", "Cilantro", "LUCE", _d(5), 4, 8, "1", luce_at=None),    # senza evento: avvio+germ = 9, +8 = 17 -> in ritardo 2
    ]
    p = _comp(semine)["promemoria"]
    assert [(v["varieta"], v["azione"]) for v in p["oggi"]] == [("Afila", "pronta")]
    assert [v["varieta"] for v in p["domani"]] == ["Rucola"]
    assert [(v["varieta"], v["giorni"]) for v in p["in_ritardo"]] == [("Cilantro", 2)]


def test_semina_ferma_oltre_il_limite_diventa_anomalia_e_non_promemoria() -> None:
    semine = [
        _s("SEM-01", "Pak Choi", "GERMINAZIONE", _d(1), 4, 12, "1"),        # prevista 5, 14 giorni fa
        _s("SEM-02", "Rucola", "LUCE", _d(1), 4, 7, "1", luce_at=_d(2)),     # pronta il 9, 10 giorni fa
        _s("SEM-03", "Mizuna", "GERMINAZIONE", _d(12), 4, 15, "1"),         # prevista 16, 3 giorni fa: ancora ritardo normale
    ]
    r = _comp(semine)
    assert [a["semina"] for a in r["anomalie"]] == ["SEM-01", "SEM-02"]
    assert all(a["tipo"] == "semina_ferma" for a in r["anomalie"])
    assert "Stato non aggiornato?" in r["anomalie"][0]["testo"] and "14 giorni fa" in r["anomalie"][0]["testo"]
    assert [v["semina"] for v in r["promemoria"]["in_ritardo"]] == ["SEM-03"]


def test_semine_senza_protocollo_o_senza_set_non_rompono_nulla() -> None:
    semine = [
        _s("SEM-01", "Lattuga", "GERMINAZIONE", _d(15), None, None, "1"),
        _s("SEM-02", "Basilico", "GERMINAZIONE", _d(15), 4, 13, None),     # senza SET: il promemoria c'e', senza quantita
        ("SEM-03", "C", "Altro", "PRONTA_ALLA_RACCOLTA", _d(10), Decimal(1), "SET", 4, 10, 0, None),
    ]
    p = _comp(semine)["promemoria"]
    assert [(v["semina"], v["set"]) for v in p["oggi"]] == [("SEM-02", None)]
    assert p["domani"] == [] and p["in_ritardo"] == []


def test_clienti_con_nome_simile_e_programmi_attivi() -> None:
    clienti = [("CLI-1", "Restaurante Salvaje", True), ("CLI-2", "Restaurante Selvaje", True),
               ("CLI-3", "Okra", True), ("CLI-4", "Splash", False), ("CLI-5", "Restaurante Selvage", False)]
    simili = [a for a in _comp(clienti=clienti)["anomalie"] if a["tipo"] == "clienti_simili"]
    per_coppia = {tuple(a["clienti"]): a for a in simili}
    assert ("CLI-1", "CLI-2") in per_coppia and per_coppia[("CLI-1", "CLI-2")]["doppio_programma"] is True
    assert "ordini doppi" in per_coppia[("CLI-1", "CLI-2")]["testo"]
    assert per_coppia[("CLI-2", "CLI-5")]["doppio_programma"] is False
    assert not any("CLI-3" in a["clienti"] or "CLI-4" in a["clienti"] for a in simili)


def test_accenti_e_maiuscole_non_nascondono_un_nome_quasi_uguale() -> None:
    simili = controlli._clienti_simili([("CLI-1", "Cafe Ñandú", False), ("CLI-2", "cafe nandu ", False)])
    assert len(simili) == 1


def test_lotto_di_seme_che_basta_per_pochi_set() -> None:
    lotti = [
        ("LSE-1", "Cilantro", Decimal("60"), Decimal("12"), _d(18)),    # 5 SET -> segnalato
        ("LSE-2", "Afila", Decimal("500"), Decimal("12"), _d(18)),      # 41 SET -> no
        ("LSE-3", "Rucola", Decimal("10"), Decimal("12"), _d(18)),      # 0 SET, lotto attivo -> segnalato
        ("LSE-4", "Vecchio", Decimal("10"), Decimal("12"), _d(1, 9)),   # usato 18 giorni fa: ancora attivo -> segnalato
        ("LSE-5", "Fermo", Decimal("10"), Decimal("12"), datetime(2026, 8, 1, tzinfo=timezone.utc)),   # fermo da mesi: no
        ("LSE-6", "Senza", Decimal("10"), None, None),                  # mai usato: no
    ]
    voci = [a for a in _comp(lotti=lotti)["anomalie"] if a["tipo"] == "seme_poco"]
    assert [v["lotto"] for v in voci] == ["LSE-1", "LSE-3", "LSE-4"]
    assert voci[0]["set_possibili"] == "5" and "60 g" in voci[0]["testo"]


def test_righe_avviso_senza_nomi_di_clienti() -> None:
    semine = [
        _s("SEM-01", "Hinojo", "GERMINAZIONE", _d(15), 4, 20, "1"),
        _s("SEM-02", "Hinojo", "GERMINAZIONE", _d(15), 4, 20, "0.5"),
        _s("SEM-03", "Mizuna", "GERMINAZIONE", _d(14), 4, 15, "2"),          # in ritardo 1 -> compare
        _s("SEM-04", "Afila", "LUCE", _d(5), 4, 10, "6", luce_at=_d(9)),
        _s("SEM-05", "Basilico", "GERMINAZIONE", _d(15), 4, 13, None),
    ]
    clienti = [("CLI-1", "Restaurante Salvaje", True), ("CLI-2", "Restaurante Selvaje", True)]
    righe = controlli.righe_avviso(_comp(semine, clienti))
    testo = "\n".join(righe)
    assert "Passano a luce: Hinojo 1,5, Mizuna 2, Basilico ?." in testo
    assert "Pronte da raccogliere: Afila 6." in testo
    assert righe[-1] == "Da controllare: 1 (vedi Oggi)."
    assert "Salvaje" not in testo and "Selvaje" not in testo


def test_righe_avviso_vuote_se_non_c_e_nulla() -> None:
    assert controlli.righe_avviso(_comp()) == []
    # il domani non entra nell'avviso del mattino
    assert controlli.righe_avviso(_comp([_s("SEM-01", "Mizuna", "GERMINAZIONE", _d(16), 4, 15)])) == []


def test_pagina_api_controlli_e_errore_leggibile(monkeypatch) -> None:
    monkeypatch.setenv("DIARIO_PASSWORD", "segreta")
    monkeypatch.setattr(app_module, "_settings", lambda: object())
    client = TestClient(app_module.app)
    assert client.get("/api/controlli").status_code == 401
    monkeypatch.setattr(controlli, "leggi", lambda settings, adesso=None: _comp())
    r = client.get("/api/controlli", auth=AUTH)
    assert r.status_code == 200 and set(r.json()) >= {"promemoria", "anomalie", "nota"}

    def rotto(settings, adesso=None):
        raise RuntimeError("db spento")

    monkeypatch.setattr(controlli, "leggi", rotto)
    r = client.get("/api/controlli", auth=AUTH)
    assert r.status_code == 503 and "Controlli non disponibili" in r.json()["errore"]


def test_la_pagina_oggi_mostra_i_controlli(monkeypatch) -> None:
    monkeypatch.setenv("DIARIO_PASSWORD", "segreta")
    monkeypatch.setattr(app_module, "_settings", lambda: object())
    html = TestClient(app_module.app).get("/", auth=AUTH).text
    assert html.count('id="controlli"') == 1 and "/api/controlli" in html and "caricaControlli()" in html


def test_il_modulo_non_scrive_niente() -> None:
    sorgente = open(controlli.__file__, encoding="utf-8").read().upper()
    for vietato in ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "DROP ", "ALTER ", "COMMIT"):
        assert vietato not in sorgente
    assert "READ_ONLY = TRUE" in sorgente
