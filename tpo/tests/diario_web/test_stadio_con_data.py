"""Cambio di stadio da bottone con giorno/ora dichiarati (19/10/2026): calcolo degli istanti, proposta, rotte, esecuzione.
Nessun database: le letture sono finte, il comando governato e' finto."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from src.tpo_core.diario_web import actions, app as app_module, db_context

AUTH = ("matteo", "segreta")
TZ = ZoneInfo("Atlantic/Canary")
ADESSO = datetime(2026, 10, 19, 11, 30, 40, tzinfo=TZ)
AVVIO = datetime(2026, 10, 15, 9, 0, tzinfo=TZ)


def _dett(stato="GERMINAZIONE", ultimo=None, avvio=AVVIO, pid="SEM-000032"):
    return db_context.SeminaDettaglio(pid, stato, 1, "HIN-1510", avvio, "VAR-000007", "Hinojo", ultimo)


# ---- istanti_passi (pura) ----

def test_oggi_senza_ora_vale_adesso_al_minuto() -> None:
    istanti, note = actions.istanti_passi(["LUCE"], AVVIO, None, None, None, ADESSO)
    assert istanti == [datetime(2026, 10, 19, 11, 30, tzinfo=TZ)] and note == []


def test_giorno_passato_senza_ora_vale_mezzogiorno_e_lo_dice() -> None:
    istanti, note = actions.istanti_passi(["LUCE"], AVVIO, None, date(2026, 10, 17), None, ADESSO)
    assert istanti == [datetime(2026, 10, 17, 12, 0, tzinfo=TZ)]
    assert note and "12:00" in note[0]


def test_giorno_e_ora_dichiarati() -> None:
    istanti, note = actions.istanti_passi(["LUCE"], AVVIO, None, date(2026, 10, 18), time(7, 45), ADESSO)
    assert istanti == [datetime(2026, 10, 18, 7, 45, tzinfo=TZ)] and note == []


def test_dalla_avviata_la_germinazione_e_amministrativa_alla_data_di_avvio() -> None:
    istanti, _ = actions.istanti_passi(["GERMINAZIONE", "LUCE"], AVVIO, None, date(2026, 10, 18), time(9, 0), ADESSO)
    assert istanti == [AVVIO, datetime(2026, 10, 18, 9, 0, tzinfo=TZ)]


def test_passi_multipli_finiscono_all_istante_dichiarato_a_un_minuto_l_uno_dall_altro() -> None:
    istanti, _ = actions.istanti_passi(["CRESCITA", "PRONTA_ALLA_RACCOLTA"], AVVIO, datetime(2026, 10, 17, 10, tzinfo=TZ),
                                       date(2026, 10, 19), time(8, 0), ADESSO)
    assert istanti == [datetime(2026, 10, 19, 7, 59, tzinfo=TZ), datetime(2026, 10, 19, 8, 0, tzinfo=TZ)]


@pytest.mark.parametrize("giorno,ora", [(date(2026, 10, 20), None), (date(2026, 10, 19), time(23, 0))])
def test_il_futuro_e_rifiutato(giorno, ora) -> None:
    with pytest.raises(actions.PropostaAmbigua, match="futuro"):
        actions.istanti_passi(["LUCE"], AVVIO, None, giorno, ora, ADESSO)


def test_prima_dell_avvio_o_dell_ultimo_passaggio_e_rifiutato_con_il_limite() -> None:
    with pytest.raises(actions.PropostaAmbigua, match="15/10/2026 09:00"):
        actions.istanti_passi(["LUCE"], AVVIO, None, date(2026, 10, 14), None, ADESSO)
    with pytest.raises(actions.PropostaAmbigua, match="17/10/2026 10:00"):
        actions.istanti_passi(["CRESCITA"], AVVIO, datetime(2026, 10, 17, 10, tzinfo=TZ), date(2026, 10, 17), time(10, 0), ADESSO)


def test_l_ora_legale_e_rispettata() -> None:
    istanti, _ = actions.istanti_passi(["LUCE"], AVVIO, None, date(2026, 10, 18), time(12, 0), ADESSO)
    assert istanti[0].utcoffset() == timedelta(hours=1)           # 18/10: ancora ora legale (fino al 25/10)
    inverno = datetime(2026, 11, 10, 11, 0, tzinfo=TZ)
    istanti, _ = actions.istanti_passi(["LUCE"], AVVIO, None, date(2026, 11, 9), time(12, 0), inverno)
    assert istanti[0].utcoffset() == timedelta(0)


# ---- prepara_transition_semina ----

def test_proposta_da_bottone_luce_dalla_germinazione(monkeypatch) -> None:
    monkeypatch.setattr(db_context, "semina_per_public_id", lambda s, pid: _dett("GERMINAZIONE"))
    p = actions.prepara_transition_semina(object(), "SEM-000032", "LUCE", date(2026, 10, 18), None, ADESSO)
    assert [x.stato for x in p.passi] == ["LUCE"] and p.passi[0].istante == "2026-10-18T12:00:00+01:00"
    assert p.varieta_nome == "Hinojo" and p.note


def test_proposta_da_bottone_dalla_avviata_passa_per_la_germinazione(monkeypatch) -> None:
    monkeypatch.setattr(db_context, "semina_per_public_id", lambda s, pid: _dett("AVVIATA"))
    p = actions.prepara_transition_semina(object(), "SEM-000032", "LUCE", None, None, ADESSO)
    assert [x.stato for x in p.passi] == ["GERMINAZIONE", "LUCE"]
    assert p.passi[0].istante == "2026-10-15T09:00:00+01:00"


def test_proposta_pronta_dalla_luce_passa_per_la_crescita(monkeypatch) -> None:
    monkeypatch.setattr(db_context, "semina_per_public_id", lambda s, pid: _dett("LUCE", ultimo=AVVIO + timedelta(days=3)))
    p = actions.prepara_transition_semina(object(), "SEM-000032", "PRONTA_ALLA_RACCOLTA", None, None, ADESSO)
    assert [x.stato for x in p.passi] == ["CRESCITA", "PRONTA_ALLA_RACCOLTA"]


@pytest.mark.parametrize("stato,target,testo", [
    ("LUCE", "LUCE", "gia' a LUCE"), ("CRESCITA", "LUCE", "gia' a CRESCITA"), ("CHIUSA", "LUCE", "CHIUSA"),
    ("GERMINAZIONE", "CRESCITA", "solo i passaggi"), ("GERMINAZIONE", "CHIUSA", "solo i passaggi")])
def test_proposte_non_valide(monkeypatch, stato, target, testo) -> None:
    monkeypatch.setattr(db_context, "semina_per_public_id", lambda s, pid: _dett(stato))
    with pytest.raises(actions.PropostaAmbigua, match=testo):
        actions.prepara_transition_semina(object(), "SEM-000032", target, None, None, ADESSO)


def test_semina_inesistente(monkeypatch) -> None:
    monkeypatch.setattr(db_context, "semina_per_public_id", lambda s, pid: None)
    with pytest.raises(actions.SeminaNonTrovata):
        actions.prepara_transition_semina(object(), "SEM-999999", "LUCE", None, None, ADESSO)


# ---- esecuzione ----

def _prop(istanti):
    return actions.PropostaTransition(
        varieta_public_id="VAR-000007", semina_public_id="SEM-000032", varieta_nome="Hinojo", stato_attuale="AVVIATA",
        passi=[actions.PassoTransizione(stato=s, istante=i) for s, i in istanti])


def _attiva():
    return db_context.SeminaAttiva("SEM-000032", "GERMINAZIONE", 3, "HIN-1510", "2026-10-15 09:00:00+01")


def test_esegue_con_l_istante_dichiarato_e_lo_scrive_nel_motivo(monkeypatch) -> None:
    visti = []
    monkeypatch.setattr(actions, "run_semina_command", lambda args, *, stdout, stderr: (visti.append(args), stdout.write("OK") and 0)[1] or 0)
    monkeypatch.setattr(db_context, "semine_attive_per_varieta", lambda s, v: [_attiva()])
    ieri = (datetime.now(TZ) - timedelta(days=1)).replace(microsecond=0)
    actions.esegui_transition(object(), _prop([("LUCE", ieri.isoformat())]), "matteo")
    assert visti[0].effective_at == ieri.isoformat() and visti[0].target_state == "LUCE"
    assert "Data/ora dichiarata" in visti[0].reason


def test_un_istante_nel_futuro_blocca_tutto_prima_di_scrivere(monkeypatch) -> None:
    visti = []
    monkeypatch.setattr(actions, "run_semina_command", lambda args, *, stdout, stderr: visti.append(args) or 0)
    monkeypatch.setattr(db_context, "semine_attive_per_varieta", lambda s, v: [_attiva()])
    ora = datetime.now(timezone.utc).replace(microsecond=0)
    proposta = _prop([("GERMINAZIONE", (ora - timedelta(days=3)).isoformat()), ("LUCE", (ora + timedelta(days=2)).isoformat())])
    with pytest.raises(actions.SeminaOperazioneFallita, match="futuro"):
        actions.esegui_transition(object(), proposta, "matteo")
    assert visti == []                                         # neanche il primo passo e' stato eseguito
    with pytest.raises(actions.SeminaOperazioneFallita):
        actions.esegui_transition(object(), _prop([("LUCE", "2026-10-18T12:00:00")]), "matteo")   # senza fuso


def test_senza_istanti_resta_il_comportamento_di_sempre(monkeypatch) -> None:
    visti = []
    monkeypatch.setattr(actions, "run_semina_command", lambda args, *, stdout, stderr: visti.append(args) or 0)
    monkeypatch.setattr(db_context, "semine_attive_per_varieta", lambda s, v: [_attiva()])
    actions.esegui_transition(object(), _prop([("LUCE", None)]), "matteo")
    assert visti[0].effective_at and "Data/ora dichiarata" not in visti[0].reason


# ---- rotte ----

def _client(monkeypatch):
    monkeypatch.setenv("DIARIO_PASSWORD", "segreta")
    monkeypatch.setattr(app_module, "_settings", lambda: object())
    return TestClient(app_module.app)


def test_rotta_prepara_restituisce_la_proposta_con_gli_istanti(monkeypatch) -> None:
    c = _client(monkeypatch)
    assert c.post("/api/stadio/prepara", json={}).status_code == 401
    monkeypatch.setattr(db_context, "semina_per_public_id", lambda s, pid: _dett("AVVIATA"))
    r = c.post("/api/stadio/prepara", auth=AUTH, json={"semina": "SEM-000032", "stadio": "LUCE", "giorno": "2026-10-18", "ora": "08:30"})
    p = r.json()["proposte"][0]
    assert r.json()["errori"] == [] and p["tipo"] == "semina_transition" and p["passi"] == ["GERMINAZIONE", "LUCE"]
    assert p["istanti"] == ["2026-10-15T09:00:00+01:00", "2026-10-18T08:30:00+01:00"]


def test_rotta_prepara_errori_leggibili(monkeypatch) -> None:
    c = _client(monkeypatch)
    monkeypatch.setattr(db_context, "semina_per_public_id", lambda s, pid: _dett("LUCE"))
    r = c.post("/api/stadio/prepara", auth=AUTH, json={"semina": "SEM-000032", "stadio": "LUCE"})
    assert r.status_code == 200 and r.json()["proposte"] == [] and "gia' a LUCE" in r.json()["errori"][0]
    r = c.post("/api/stadio/prepara", auth=AUTH, json={"semina": "SEM-000032", "stadio": "LUCE", "giorno": "domani"})
    assert r.json()["errori"] == ["Giorno o ora non validi."]

    def giu(settings, pid):
        raise RuntimeError("db spento")

    monkeypatch.setattr(db_context, "semina_per_public_id", giu)
    r = c.post("/api/stadio/prepara", auth=AUTH, json={"semina": "SEM-000032", "stadio": "LUCE"})
    assert "Proposta non preparata" in r.json()["errori"][0]


def test_rotta_conferma_passa_gli_istanti_all_esecuzione(monkeypatch) -> None:
    c = _client(monkeypatch)
    visti = []
    monkeypatch.setattr(actions, "esegui_transition", lambda s, p, actor: visti.append(p) or "FATTO")
    proposta = {"tipo": "semina_transition", "varieta_public_id": "VAR-000007", "semina_public_id": "SEM-000032",
                "varieta_nome": "Hinojo", "stato_attuale": "GERMINAZIONE", "passi": ["LUCE"],
                "istanti": ["2026-10-18T12:00:00+01:00"]}
    assert c.post("/api/conferma", auth=AUTH, json={"proposta": proposta}).json() == {"ok": True, "messaggio": "FATTO"}
    assert visti[0].passi[0].istante == "2026-10-18T12:00:00+01:00"
    proposta["istanti"] = ["a", "b"]                            # numero diverso dai passi: rifiutata
    assert c.post("/api/conferma", auth=AUTH, json={"proposta": proposta}).status_code == 400
    proposta.pop("istanti")                                     # proposte del campo di testo: nessun istante
    c.post("/api/conferma", auth=AUTH, json={"proposta": proposta})
    assert visti[1].passi[0].istante is None


def test_la_pagina_ha_il_bottone_registra(monkeypatch) -> None:
    html = _client(monkeypatch).get("/", auth=AUTH).text
    assert "/api/stadio/prepara" in html and "data-registra" in html and html.count('id="registraStadio"') == 1
